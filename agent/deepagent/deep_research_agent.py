"""
Deep Research Agent - 基于 DeepAgents 的 Text-to-SQL 智能体

重构说明：
1. 使用会话级工具调用管理器，解决死循环问题
2. 降低 recursion_limit，添加早期终止机制
3. 添加分步超时控制，解决任务超时问题
4. 增强进度追踪和状态监控
"""

import asyncio
import json
import logging
import os
import time
import traceback
import uuid
from typing import Optional

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent.deepagent.tools.native_sql_tools import (
    set_native_datasource_info,
    sql_db_list_tables,
    sql_db_query,
    sql_db_query_checker,
    sql_db_schema,
    sql_db_table_relationship,
)
from agent.deepagent.tools.tool_call_manager import (
    get_tool_call_manager,
    set_current_session,
)
from common.datasource_util import (
    DB,
    ConnectType,
    DatasourceConfigUtil,
    DatasourceConnectionUtil,
)
from common.llm_util import get_llm
from constants.code_enum import DataTypeEnum, IntentEnum
from model.db_connection_pool import get_db_pool
from services.datasource_service import DatasourceService
from services.user_service import add_user_record, decode_jwt_token

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))


class DeepAgent:
    """
    基于 DeepAgents 的 Text-to-SQL 智能体，支持多轮对话记忆

    优化特性：
    - 会话级工具调用管理，防止死循环
    - 分步超时控制，避免长时间阻塞
    - 智能循环检测和早期终止
    - 进度追踪和状态监控
    """

    # ==================== 配置参数 ====================
    # 递归限制说明：
    # - 子代理（subagent/task）也会消耗递归次数
    # - 报告生成等复杂任务可能需要较多步骤
    # - 设置为 150 是一个平衡点：足够完成复杂任务，同时防止无限循环
    DEFAULT_RECURSION_LIMIT = 150

    # LLM 超时配置（秒）- 与 llm_util.py 的 DEFAULT_LLM_TIMEOUT 保持一致
    # 公网大模型（如 DeepSeek、Qwen）在高峰期可能需要较长时间
    DEFAULT_LLM_TIMEOUT = 10 * 60  # 10 分钟，单次 LLM 调用超时

    # 流式响应超时（秒）- 如果长时间没有新消息，则认为可能卡住
    # 注意：reasoning/thinking 模型在思考阶段不输出 token，需要更宽松的超时
    STREAM_IDLE_TIMEOUT = 5 * 60  # 5 分钟无新消息（兼容深度思考模型）

    # SSE 保活间隔（秒）：等待 LLM/工具期间每 N 秒发送一次注释，防止代理/浏览器约 2 分钟无数据断开
    STREAM_KEEPALIVE_INTERVAL = 25

    # 总任务超时（秒）- 与前端 fetch timeout (18分钟) 和 Nginx proxy_read_timeout (1080s) 对齐
    TASK_TIMEOUT = 15 * 60  # 15 分钟

    # 最大消息数量（防止上下文过长）
    MAX_MESSAGES = 80

    def __init__(self):
        # 全局 checkpointer 用于持久化所有用户的对话状态
        self.checkpointer = InMemorySaver()

        # 是否启用链路追踪
        self.ENABLE_TRACING = (
            os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() == "true"
        )

        # 存储运行中的任务
        self.running_tasks = {}

        # 从环境变量读取配置，允许动态调整
        self.RECURSION_LIMIT = int(
            os.getenv("RECURSION_LIMIT", self.DEFAULT_RECURSION_LIMIT)
        )
        self.LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", self.DEFAULT_LLM_TIMEOUT))

        # 工具调用管理器
        self.tool_manager = get_tool_call_manager()

        # 加载可用技能列表
        self.available_skills = self._load_available_skills()

    def _load_available_skills(self):
        """加载所有可用的技能"""
        skills_dir = os.path.join(current_dir, "skills")
        skills = []
        if os.path.exists(skills_dir):
            for skill_dir in os.listdir(skills_dir):
                skill_path = os.path.join(skills_dir, skill_dir)
                if os.path.isdir(skill_path):
                    skill_file = os.path.join(skill_path, "SKILL.md")
                    if os.path.exists(skill_file):
                        try:
                            with open(skill_file, "r", encoding="utf-8") as f:
                                content = f.read()
                                # 解析 frontmatter
                                if content.startswith("---"):
                                    parts = content.split("---", 2)
                                    if len(parts) >= 3:
                                        frontmatter = parts[1]
                                        skill_info = {}
                                        for line in frontmatter.strip().split("\n"):
                                            if ":" in line:
                                                key, value = line.split(":", 1)
                                                skill_info[key.strip()] = (
                                                    value.strip().strip('"')
                                                )
                                        skill_info["name"] = skill_info.get(
                                            "name", skill_dir
                                        )
                                        skill_info["description"] = skill_info.get(
                                            "description", ""
                                        )
                                        skills.append(skill_info)
                        except Exception as e:
                            logger.warning(f"加载技能 {skill_dir} 失败: {e}")
        return skills

    @staticmethod
    def _create_response(
        content: str,
        message_type: str = "continue",
        data_type: str = DataTypeEnum.ANSWER.value[0],
    ) -> str:
        """封装响应结构"""
        res = {
            "data": {"messageType": message_type, "content": content},
            "dataType": data_type,
        }
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    def _wrap_tools_with_tracking(self, tools: list, session_id: str) -> list:
        """
        包装工具列表，为每个工具添加调用统计功能

        Args:
            tools: 原始工具列表
            session_id: 会话ID

        Returns:
            包装后的工具列表
        """
        from functools import wraps

        from langchain_core.tools import StructuredTool

        wrapped_tools = []

        for tool in tools:
            original_func = tool.func if hasattr(tool, "func") else tool._run
            tool_name = tool.name

            @wraps(original_func)
            def create_wrapper(orig_func, t_name):
                def wrapper(*args, **kwargs):
                    # 调用前检查
                    query = kwargs.get("query") or (args[0] if args else None)
                    allowed, reason = self.tool_manager.check_before_call(
                        session_id, t_name, query
                    )

                    if not allowed:
                        logger.warning(f"工具调用被阻止: {t_name}, 原因: {reason}")
                        # 返回明确的停止指令，让 Agent 知道应该停止尝试
                        return (
                            f"⛔ 操作已被系统阻止: {reason}\n\n"
                            "【重要指令】请立即停止所有工具调用，不要再尝试任何 SQL 查询或工具操作。"
                            "请直接向用户总结已获得的信息，或告知用户需要简化查询需求。"
                        )

                    # 执行工具
                    try:
                        result = orig_func(*args, **kwargs)
                        self.tool_manager.record_call(session_id, t_name, True, query)
                        return result
                    except Exception as e:
                        self.tool_manager.record_call(session_id, t_name, False, query)
                        raise

                return wrapper

            # 创建包装后的工具
            wrapped_func = create_wrapper(original_func, tool_name)

            wrapped_tool = StructuredTool(
                name=tool.name,
                description=tool.description,
                func=wrapped_func,
                args_schema=tool.args_schema if hasattr(tool, "args_schema") else None,
            )
            wrapped_tools.append(wrapped_tool)

        logger.info(f"已包装 {len(wrapped_tools)} 个工具用于调用统计")
        return wrapped_tools

    def _create_sql_deep_agent(self, datasource_id: int = None, session_id: str = None):
        """
        创建并返回一个 text-to-SQL Deep Agent，支持所有数据源类型

        Args:
            datasource_id: 数据源 ID
            session_id: 会话 ID，用于工具调用管理
        """
        if not datasource_id:
            raise ValueError("必须提供数据源ID (datasource_id)")

        logger.info(f"创建 Deep Agent - 数据源: {datasource_id}, 会话: {session_id}")

        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            datasource = DatasourceService.get_datasource_by_id(session, datasource_id)
            if not datasource:
                raise ValueError(f"数据源 {datasource_id} 不存在")

            # 检查数据源连接类型
            db_enum = DB.get_db(datasource.type, default_if_none=True)

            # 获取 LLM 模型
            model = get_llm(timeout=self.LLM_TIMEOUT)
            logger.info(
                f"LLM 模型已创建，超时: {self.LLM_TIMEOUT}秒，"
                f"递归限制: {self.RECURSION_LIMIT}"
            )

            if db_enum.connect_type == ConnectType.sqlalchemy:
                # SQLAlchemy 驱动的数据库
                logger.info(
                    f"数据源 {datasource_id} ({datasource.type}) 使用 SQLAlchemy 连接"
                )

                config = DatasourceConfigUtil.decrypt_config(datasource.configuration)
                uri = DatasourceConnectionUtil.build_connection_uri(
                    datasource.type, config
                )

                db = SQLDatabase.from_uri(uri, sample_rows_in_table_info=3)
                toolkit = SQLDatabaseToolkit(db=db, llm=model)
                original_tools = toolkit.get_tools()

                # 包装 SQLAlchemy 工具以添加统计功能
                sql_tools = self._wrap_tools_with_tracking(original_tools, session_id)
            else:
                # 原生驱动的数据库
                logger.info(
                    f"数据源 {datasource_id} ({datasource.type}) 使用原生驱动连接"
                )

                # 设置原生数据源信息（包括会话ID，用于工具调用管理）
                set_native_datasource_info(
                    datasource_id, datasource.type, datasource.configuration, session_id
                )

                sql_tools = [
                    sql_db_list_tables,
                    sql_db_schema,
                    sql_db_query,
                    sql_db_query_checker,
                    sql_db_table_relationship,
                ]

        all_tools = sql_tools

        # 创建 Deep Agent
        agent = create_deep_agent(
            model=model,
            memory=[os.path.join(current_dir, "AGENTS.md")],
            skills=[os.path.join(current_dir, "skills/")],
            tools=all_tools,
            backend=FilesystemBackend(root_dir=current_dir),
        )

        return agent

    async def run_agent(
        self,
        query: str,
        response,
        session_id: Optional[str] = None,
        uuid_str: str = None,
        user_token=None,
        file_list: dict = None,
        datasource_id: int = None,
    ):
        """
        运行智能体，支持多轮对话记忆和实时思考过程输出

        Args:
            query: 用户输入
            response: 响应对象
            session_id: 会话ID
            uuid_str: 唯一标识
            user_token: 用户令牌
            file_list: 附件
            datasource_id: 数据源ID
        """
        # 检查数据源ID
        if not datasource_id:
            error_msg = "❌ **错误**: 必须提供数据源ID (datasource_id)"
            await response.write(
                self._create_response(error_msg, "error", DataTypeEnum.ANSWER.value[0])
            )
            return

        # 获取用户信息
        user_dict = await decode_jwt_token(user_token)
        task_id = user_dict["id"]

        # 生成唯一的会话标识
        effective_session_id = session_id or f"sql-agent-{datasource_id}-{task_id}"

        # 设置当前会话（供工具调用管理器使用）
        set_current_session(effective_session_id)

        # 重置会话的工具调用状态（新问题开始时）
        self.tool_manager.reset_session(effective_session_id)

        task_context = {
            "cancelled": False,
            "start_time": time.time(),
            "session_id": effective_session_id,
        }
        self.running_tasks[task_id] = task_context

        try:
            t02_answer_data = []

            config = {
                "configurable": {"thread_id": effective_session_id},
                "recursion_limit": self.RECURSION_LIMIT,
            }

            # 准备 tracing 配置
            if self.ENABLE_TRACING:
                from langfuse.langchain import CallbackHandler

                langfuse_handler = CallbackHandler()
                config["callbacks"] = [langfuse_handler]
                config["metadata"] = {"langfuse_session_id": session_id}

            # 创建 SQL Deep Agent
            agent = self._create_sql_deep_agent(datasource_id, effective_session_id)

            # 准备流式处理参数
            # 使用混合模式：messages 用于 token 级别流式输出，updates 用于工具调用结果
            stream_args = {
                "input": {"messages": [HumanMessage(content=query)]},
                "config": config,
                "stream_mode": ["messages", "updates"],
            }

            # 包装执行，添加总超时控制
            try:
                await asyncio.wait_for(
                    self._execute_agent_stream(
                        agent,
                        stream_args,
                        response,
                        task_id,
                        t02_answer_data,
                        uuid_str,
                        session_id,
                        query,
                        file_list,
                        user_token,
                        datasource_id,
                        effective_session_id,
                    ),
                    timeout=self.TASK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                elapsed = time.time() - task_context.get("start_time", 0)
                stats = self.tool_manager.get_stats(effective_session_id)
                logger.error(
                    f"任务 {task_id} 总超时 ({self.TASK_TIMEOUT}秒) - "
                    f"实际耗时: {elapsed:.0f}秒, "
                    f"工具调用: {stats.get('total_calls', 0)}次, "
                    f"失败: {stats.get('failed_calls', 0)}次"
                )
                await self._handle_timeout(
                    response,
                    f"任务执行时间超过上限（{self.TASK_TIMEOUT // 60} 分钟）",
                    elapsed_total=elapsed,
                    tool_stats=stats,
                )

        except asyncio.CancelledError:
            is_user_cancelled = self._is_task_cancelled(task_id)
            logger.info(
                f"任务 {task_id} 被取消 - "
                f"原因: {'用户主动取消' if is_user_cancelled else '连接断开'}"
            )
            try:
                await self._handle_task_cancellation(response, is_user_cancelled)
            except Exception as e:
                if not self._is_connection_error(e):
                    logger.error(f"处理取消异常时出错: {e}", exc_info=True)
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"客户端连接已断开: {type(e).__name__}")
            else:
                logger.error(f"Agent运行异常: {e}")
                traceback.print_exception(e)
                try:
                    error_msg = (
                        f"❌ **错误**: 智能体运行异常\n\n```\n{str(e)[:200]}\n```\n"
                    )
                    await self._safe_write(
                        response, error_msg, "error", DataTypeEnum.ANSWER.value[0]
                    )
                except Exception:
                    pass
        finally:
            # 清理任务记录
            if task_id in self.running_tasks:
                elapsed = time.time() - self.running_tasks[task_id].get("start_time", 0)
                logger.info(f"任务 {task_id} 结束，耗时: {elapsed:.2f}秒")
                del self.running_tasks[task_id]

            # 获取并记录工具调用统计
            stats = self.tool_manager.get_stats(effective_session_id)
            logger.info(f"工具调用统计: {stats}")

    async def _execute_agent_stream(
        self,
        agent,
        stream_args,
        response,
        task_id,
        t02_answer_data,
        uuid_str,
        session_id,
        query,
        file_list,
        user_token,
        datasource_id,
        effective_session_id,
    ):
        """执行 agent 流式处理（带 tracing 支持）"""
        if self.ENABLE_TRACING:
            from langfuse import get_client

            langfuse = get_client()
            with langfuse.start_as_current_observation(
                input=query,
                as_type="agent",
                name="Text-to-SQL",
            ) as rootspan:
                user_info = await decode_jwt_token(user_token)
                user_id = user_info.get("id")
                rootspan.update_trace(session_id=session_id, user_id=user_id)
                await self._stream_agent_response(
                    agent,
                    stream_args,
                    response,
                    task_id,
                    t02_answer_data,
                    uuid_str,
                    session_id,
                    query,
                    file_list,
                    user_token,
                    datasource_id,
                    effective_session_id,
                )
        else:
            await self._stream_agent_response(
                agent,
                stream_args,
                response,
                task_id,
                t02_answer_data,
                uuid_str,
                session_id,
                query,
                file_list,
                user_token,
                datasource_id,
                effective_session_id,
            )

    async def _stream_agent_response(
        self,
        agent,
        stream_args,
        response,
        task_id,
        t02_answer_data,
        uuid_str,
        session_id,
        query,
        file_list,
        user_token,
        datasource_id: int = None,
        effective_session_id: str = None,
    ):
        """
        处理 agent 流式响应的核心逻辑

        混合模式 stream_mode=["messages", "updates"] 返回格式：
        - (mode, chunk) 元组
        - mode="messages" 时，chunk 是 (message_chunk, metadata) 元组，用于 token 级别流式
        - mode="updates" 时，chunk 是状态更新字典，用于工具调用结果
        """
        start_time = time.time()
        message_count = 0
        token_count = 0
        connection_closed = False
        last_message_time = time.time()

        # 用于累积 token 流式输出的缓冲区
        current_content_buffer = ""
        current_node = None

        logger.info(
            f"开始流式响应处理（混合模式） - 任务ID: {task_id}, 查询: {query[:100]}"
        )

        stream_iter = agent.astream(**stream_args)
        stream_anext = stream_iter.__anext__

        try:
            while True:
                # 带超时等待下一 chunk，超时则发送 SSE 保活防止代理/浏览器约 2 分钟无数据断开
                try:
                    mode, chunk = await asyncio.wait_for(
                        stream_anext(), timeout=self.STREAM_KEEPALIVE_INTERVAL
                    )
                except asyncio.TimeoutError:
                    try:
                        # 发送标准 SSE 保活事件，前端解析后忽略（不追加内容）
                        await response.write(
                            'data: {"data":{"messageType": "info", "content": ""}, "dataType": "keepalive"}\n\n'
                        )
                        if hasattr(response, "flush"):
                            await response.flush()
                        last_message_time = time.time()
                    except Exception as e:
                        if self._is_connection_error(e):
                            connection_closed = True
                            break
                        raise
                    continue
                except StopAsyncIteration:
                    break

                current_time = time.time()

                # 检查是否已取消
                if self._is_task_cancelled(task_id):
                    await self._handle_task_cancellation(
                        response, is_user_cancelled=True
                    )
                    return

                # 检查工具调用管理器是否触发终止
                if effective_session_id:
                    ctx = self.tool_manager.get_session(effective_session_id)
                    if ctx.should_terminate:
                        logger.warning(
                            f"工具调用管理器触发终止: {ctx.termination_reason}"
                        )
                        await self._safe_write(
                            response,
                            f"\n> ⚠️ **执行中止**\n\n{ctx.termination_reason}",
                            "warning",
                            DataTypeEnum.ANSWER.value[0],
                        )
                        break

                # 检查空闲超时
                idle_duration = current_time - last_message_time
                if idle_duration > self.STREAM_IDLE_TIMEOUT:
                    elapsed_total = current_time - start_time
                    stats = (
                        self.tool_manager.get_stats(effective_session_id)
                        if effective_session_id
                        else {}
                    )
                    logger.warning(
                        f"流式响应空闲超时 ({self.STREAM_IDLE_TIMEOUT}秒) - "
                        f"空闲时长: {idle_duration:.0f}秒, 总运行: {elapsed_total:.0f}秒, "
                        f"消息数: {message_count}, token数: {token_count}, "
                        f"工具调用: {stats.get('total_calls', 0)}次"
                    )
                    await self._handle_timeout(
                        response,
                        f"长时间无响应（空闲 {idle_duration:.0f} 秒）",
                        elapsed_total=elapsed_total,
                        tool_stats=stats,
                    )
                    break

                # 处理 messages 模式 - token 级别流式输出
                if mode == "messages":
                    # 再次检查终止状态（工具调用可能在处理过程中触发终止）
                    if effective_session_id:
                        ctx = self.tool_manager.get_session(effective_session_id)
                        if ctx.should_terminate:
                            logger.warning(
                                f"messages 模式中检测到终止: {ctx.termination_reason}"
                            )
                            await self._safe_write(
                                response,
                                f"\n\n> ⚠️ **执行中止**\n\n{ctx.termination_reason}",
                                "warning",
                                DataTypeEnum.ANSWER.value[0],
                            )
                            connection_closed = True
                            break

                    message_chunk, metadata = chunk
                    node_name = metadata.get("langgraph_node", "")

                    # 跳过工具节点的消息（工具结果通过 updates 模式处理）
                    if node_name == "tools":
                        continue

                    # 处理 LLM 输出的 token
                    if hasattr(message_chunk, "content") and message_chunk.content:
                        content = message_chunk.content

                        # 处理内容（可能是字符串或列表）
                        if isinstance(content, str):
                            token_text = content
                        elif isinstance(content, list):
                            # 提取文本内容
                            text_parts = []
                            for part in content:
                                if (
                                    isinstance(part, dict)
                                    and part.get("type") == "text"
                                ):
                                    text_parts.append(part.get("text", ""))
                                elif isinstance(part, str):
                                    text_parts.append(part)
                            token_text = "".join(text_parts)
                        else:
                            token_text = str(content) if content else ""

                        if token_text:
                            token_count += 1
                            last_message_time = time.time()

                            # 直接输出 token（实时流式）
                            if not await self._safe_write(response, token_text):
                                connection_closed = True
                                break

                            # 累积到缓冲区用于记录
                            current_content_buffer += token_text

                            # 定期刷新；若内容含报告分隔符则每次刷新，便于前端尽早展示 HTML 报告
                            do_flush = (
                                token_count % 10 == 0
                                or "REPORT_HTML_START" in token_text
                                or "REPORT_HTML_END" in token_text
                            )
                            if do_flush and hasattr(response, "flush"):
                                try:
                                    await response.flush()
                                except Exception as e:
                                    if self._is_connection_error(e):
                                        connection_closed = True
                                        break
                                    raise

                            await asyncio.sleep(0)

                # 处理 updates 模式 - 状态更新（工具调用结果等）
                elif mode == "updates":
                    # 检查终止状态（工具调用可能触发终止）
                    if effective_session_id:
                        ctx = self.tool_manager.get_session(effective_session_id)
                        if ctx.should_terminate:
                            logger.warning(
                                f"updates 模式中检测到终止: {ctx.termination_reason}"
                            )
                            await self._safe_write(
                                response,
                                f"\n\n> ⚠️ **执行中止**\n\n{ctx.termination_reason}",
                                "warning",
                                DataTypeEnum.ANSWER.value[0],
                            )
                            connection_closed = True
                            break

                    # chunk 是一个字典，键是节点名称，值是该节点的输出
                    for node_name, node_output in chunk.items():
                        if self._is_task_cancelled(task_id):
                            await self._handle_task_cancellation(
                                response, is_user_cancelled=True
                            )
                            return

                        # 如果有累积的内容，先保存到记录中
                        if current_content_buffer:
                            t02_answer_data.append(current_content_buffer)
                            current_content_buffer = ""

                        # 处理消息更新（跳过空输出）
                        if node_output is None:
                            continue
                        if not isinstance(node_output, dict):
                            continue
                        if "messages" in node_output:
                            messages = node_output["messages"]
                            if not isinstance(messages, list):
                                messages = [messages]

                            for msg in messages:
                                message_count += 1
                                last_message_time = time.time()

                                # 检查消息数量限制
                                if message_count > self.MAX_MESSAGES:
                                    logger.warning(
                                        f"消息数量超过限制 ({self.MAX_MESSAGES})"
                                    )
                                    await self._safe_write(
                                        response,
                                        "\n> ⚠️ **对话过长**: 已达到消息数量上限，请开启新对话。",
                                        "warning",
                                        DataTypeEnum.ANSWER.value[0],
                                    )
                                    break

                                # 处理工具调用和结果
                                if not await self._process_update_message(
                                    msg, response, t02_answer_data, task_id, node_name
                                ):
                                    connection_closed = True
                                    break

                        if connection_closed:
                            break

                    if connection_closed:
                        break

                    if hasattr(response, "flush"):
                        try:
                            await response.flush()
                        except Exception as e:
                            if self._is_connection_error(e):
                                connection_closed = True
                                break
                            raise
                    await asyncio.sleep(0)

        except asyncio.CancelledError:
            is_user_cancelled = self._is_task_cancelled(task_id)
            logger.info(f"任务 {task_id} 流被取消")
            connection_closed = True  # 标记连接已关闭，避免 finally 中重复发送
            raise
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"客户端连接已断开: {type(e).__name__}")
                connection_closed = True
            else:
                await self._handle_stream_error(response, e)
        finally:
            # 保存最后的缓冲内容
            if current_content_buffer:
                t02_answer_data.append(current_content_buffer)

            elapsed_time = time.time() - start_time
            logger.info(
                f"流式响应处理完成（混合模式） - 任务ID: {task_id}, "
                f"耗时: {elapsed_time:.2f}秒 ({elapsed_time / 60:.2f}分钟), "
                f"消息数: {message_count}, token数: {token_count}, "
                f"连接状态: {'已断开' if connection_closed else '正常'}"
            )

            # 发送流结束标记（确保前端能正确结束等待状态）
            if not connection_closed and not self._is_task_cancelled(task_id):
                try:
                    await self._safe_write(
                        response, "", "end", DataTypeEnum.STREAM_END.value[0]
                    )
                except Exception as e:
                    logger.warning(f"发送 STREAM_END 失败: {e}")

            # 保存记录
            if not self._is_task_cancelled(task_id):
                try:
                    await add_user_record(
                        uuid_str,
                        session_id,
                        query,
                        t02_answer_data,
                        {},
                        IntentEnum.REPORT_QA.value[0],
                        user_token,
                        file_list,
                        datasource_id,
                    )
                except Exception as e:
                    logger.error(f"保存用户记录失败: {e}", exc_info=True)

    async def _process_update_message(
        self, msg, response, t02_answer_data, task_id: str, node_name: str
    ) -> bool:
        """
        处理 updates 模式下的消息

        Args:
            msg: 消息对象
            response: 响应对象
            t02_answer_data: 答案数据列表
            task_id: 任务ID
            node_name: 节点名称

        Returns:
            bool: 是否成功处理（False 表示连接断开）
        """
        if task_id and self._is_task_cancelled(task_id):
            return False

        try:
            # 处理工具调用（AIMessage with tool_calls）
            if isinstance(msg, AIMessage):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if task_id and self._is_task_cancelled(task_id):
                            return False

                        name = tc.get("name", "unknown")
                        args = tc.get("args", {})

                        tool_msg = self._format_tool_call(name, args)
                        if tool_msg:
                            # 输出换行以分隔 token 流和工具调用
                            if not await self._safe_write(response, "\n\n"):
                                return False
                            if not await self._safe_write(response, tool_msg, "info"):
                                return False
                            t02_answer_data.append(tool_msg)

            # 处理工具结果（ToolMessage）
            elif isinstance(msg, ToolMessage):
                if task_id and self._is_task_cancelled(task_id):
                    return False

                name = getattr(msg, "name", "")
                content_str = str(msg.content) if msg.content else ""
                tool_result_msg = self._format_tool_result(name, content_str)
                if tool_result_msg:
                    msg_type = "error" if "error" in content_str.lower() else "info"
                    if not await self._safe_write(response, tool_result_msg, msg_type):
                        return False
                    t02_answer_data.append(tool_result_msg)

            return True
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"处理更新消息时连接断开: {type(e).__name__}")
                return False
            raise

    async def _handle_timeout(
        self,
        response,
        reason: str,
        elapsed_total: float = 0,
        tool_stats: dict = None,
    ):
        """处理超时，提供详细的诊断信息"""
        # 构建诊断信息
        diag_parts = []
        if elapsed_total > 0:
            diag_parts.append(f"- 总运行时间: {elapsed_total:.0f} 秒")
        if tool_stats:
            total_calls = tool_stats.get("total_calls", 0)
            failed_calls = tool_stats.get("failed_calls", 0)
            diag_parts.append(f"- 工具调用: {total_calls} 次（失败 {failed_calls} 次）")
            if tool_stats.get("consecutive_failures", 0) > 3:
                diag_parts.append(
                    f"- ⚠ 连续失败: {tool_stats['consecutive_failures']} 次"
                )

        diag_section = ""
        if diag_parts:
            diag_section = "\n\n**诊断信息**：\n" + "\n".join(diag_parts)

        timeout_msg = (
            f"\n> ⚠️ **执行超时**: {reason}\n\n"
            "**可能的原因**：\n"
            "- 大模型 API 响应缓慢（公网模型高峰期延迟较大）\n"
            "- 查询过于复杂，智能体循环调用工具\n"
            "- 网络连接不稳定\n\n"
            "**建议**：\n"
            "- 简化查询条件，分步骤执行\n"
            "- 检查大模型 API 服务状态\n"
            "- 稍后重试"
            f"{diag_section}"
        )
        await self._safe_write(
            response, timeout_msg, "error", DataTypeEnum.ANSWER.value[0]
        )
        await self._safe_write(response, "", "end", DataTypeEnum.STREAM_END.value[0])

    async def _handle_stream_error(self, response, e: Exception):
        """处理流式响应错误，区分公网大模型超时和系统内部错误"""
        error_type = type(e).__name__
        error_msg_str = str(e).lower()

        is_timeout = (
            "timeout" in error_msg_str
            or "timed out" in error_msg_str
            or error_type in ["TimeoutError", "asyncio.TimeoutError"]
        )

        is_rate_limit = (
            "rate_limit" in error_msg_str
            or "rate limit" in error_msg_str
            or "429" in error_msg_str
            or "too many requests" in error_msg_str
        )

        is_api_error = (
            "api" in error_msg_str
            or "401" in error_msg_str
            or "403" in error_msg_str
            or "502" in error_msg_str
            or "503" in error_msg_str
            or "service unavailable" in error_msg_str
            or "internal server error" in error_msg_str
        )

        if is_timeout:
            logger.error(f"LLM 调用超时: {error_type}: {e}", exc_info=True)
            await self._handle_timeout(
                response, "大模型 API 响应超时，可能是公网模型服务繁忙"
            )
        elif is_rate_limit:
            logger.error(f"LLM 限流: {error_type}: {e}", exc_info=True)
            error_content = (
                "\n> ⚠️ **大模型 API 限流**\n\n"
                "当前模型服务请求量过大，请稍后重试。\n"
                "如频繁出现此问题，建议联系管理员调整 API 配额。"
            )
            await self._safe_write(
                response, error_content, "error", DataTypeEnum.ANSWER.value[0]
            )
            await self._safe_write(
                response, "", "end", DataTypeEnum.STREAM_END.value[0]
            )
        elif is_api_error:
            logger.error(f"LLM API 错误: {error_type}: {e}", exc_info=True)
            error_content = (
                f"\n> ❌ **大模型 API 错误**\n\n"
                f"错误信息: {str(e)[:200]}\n\n"
                "请检查模型服务配置是否正确（API Key、服务地址等），或稍后重试。"
            )
            await self._safe_write(
                response, error_content, "error", DataTypeEnum.ANSWER.value[0]
            )
            await self._safe_write(
                response, "", "end", DataTypeEnum.STREAM_END.value[0]
            )
        else:
            logger.error(f"Agent 流式响应异常: {error_type}: {e}", exc_info=True)
            try:
                error_content = (
                    f"\n> ❌ **处理异常**\n\n"
                    f"错误类型: {error_type}\n"
                    f"错误信息: {str(e)[:200]}\n\n"
                    "请稍后重试，如问题持续存在请联系管理员。"
                )
                await self._safe_write(
                    response, error_content, "error", DataTypeEnum.ANSWER.value[0]
                )
                await self._safe_write(
                    response, "", "end", DataTypeEnum.STREAM_END.value[0]
                )
            except Exception as write_error:
                logger.error(f"发送错误消息失败: {write_error}", exc_info=True)

    @staticmethod
    async def _send_step_progress(
        response,
        step: str,
        step_name: str,
        status: str,
        progress_id: str,
    ) -> None:
        """发送步骤进度信息"""
        if response:
            progress_data = {
                "type": "step_progress",
                "step": step,
                "stepName": step_name,
                "status": status,
                "progressId": progress_id,
            }
            formatted_message = {
                "data": progress_data,
                "dataType": DataTypeEnum.STEP_PROGRESS.value[0],
            }
            await response.write(
                "data:" + json.dumps(formatted_message, ensure_ascii=False) + "\n\n"
            )

    def _is_task_cancelled(self, task_id: str) -> bool:
        """检查任务是否已被取消"""
        return task_id in self.running_tasks and self.running_tasks[task_id].get(
            "cancelled", False
        )

    def _is_connection_error(self, exception: Exception) -> bool:
        """判断是否是连接断开相关的异常"""
        error_type = type(exception).__name__
        error_msg = str(exception).lower()

        connection_error_types = [
            "ConnectionClosed",
            "ConnectionResetError",
            "BrokenPipeError",
            "ConnectionError",
            "OSError",
        ]

        connection_error_keywords = [
            "connection closed",
            "connection reset",
            "broken pipe",
            "client disconnected",
            "connection aborted",
            "transport closed",
        ]

        if error_type in connection_error_types:
            return True

        for keyword in connection_error_keywords:
            if keyword in error_msg:
                return True

        return False

    async def _safe_write(
        self,
        response,
        content: str,
        message_type: str = "continue",
        data_type: str = None,
    ):
        """安全地写入响应"""
        try:
            if data_type is None:
                data_type = DataTypeEnum.ANSWER.value[0]
            await response.write(
                self._create_response(content, message_type, data_type)
            )
            if hasattr(response, "flush"):
                await response.flush()
            return True
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"客户端连接已断开: {type(e).__name__}")
                return False
            raise

    async def _handle_task_cancellation(self, response, is_user_cancelled: bool = True):
        """处理任务取消"""
        try:
            if is_user_cancelled:
                message = "\n> ⚠️ 任务已被用户取消"
            else:
                message = "\n> ⚠️ 连接已断开，任务已中断"

            await self._safe_write(
                response, message, "info", DataTypeEnum.ANSWER.value[0]
            )
            await self._safe_write(
                response, "", "end", DataTypeEnum.STREAM_END.value[0]
            )
        except Exception as e:
            logger.error(f"发送取消消息失败: {e}", exc_info=True)

    async def _print_message(
        self, msg, response, t02_answer_data, task_id: str = None
    ) -> bool:
        """格式化并输出消息"""
        if task_id and self._is_task_cancelled(task_id):
            return False

        try:
            if isinstance(msg, HumanMessage):
                content = msg.content if hasattr(msg, "content") else str(msg)
                if content and content.strip():
                    formatted_user_msg = self._format_user_message(content)
                    t02_answer_data.append(formatted_user_msg)
                    if not await self._safe_write(response, formatted_user_msg):
                        return False
            elif isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, list):
                    text_parts = [
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    content = "\n".join(text_parts)

                if content and content.strip():
                    if task_id and self._is_task_cancelled(task_id):
                        return False

                    formatted_content = self._format_agent_content(content)
                    t02_answer_data.append(formatted_content)
                    if not await self._safe_write(response, formatted_content):
                        return False

                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if task_id and self._is_task_cancelled(task_id):
                            return False

                        name = tc.get("name", "unknown")
                        args = tc.get("args", {})

                        tool_msg = self._format_tool_call(name, args)
                        if tool_msg:
                            if not await self._safe_write(response, tool_msg, "info"):
                                return False
                            t02_answer_data.append(tool_msg)
            elif isinstance(msg, ToolMessage):
                if task_id and self._is_task_cancelled(task_id):
                    return False

                name = getattr(msg, "name", "")
                content_str = str(msg.content) if msg.content else ""
                tool_result_msg = self._format_tool_result(name, content_str)
                if tool_result_msg:
                    msg_type = "error" if "error" in content_str.lower() else "info"
                    if not await self._safe_write(response, tool_result_msg, msg_type):
                        return False
                    t02_answer_data.append(tool_result_msg)
            return True
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"写入消息时连接断开: {type(e).__name__}")
                return False
            raise

    def _format_user_message(self, content: str) -> str:
        """格式化用户消息"""
        if not content or not content.strip():
            return content
        content = content.strip()
        return f"> 💬 **Question**\n> \n> {content}\n\n"

    def _format_agent_content(self, content: str) -> str:
        """格式化 Agent 思考内容"""
        if not content or not content.strip():
            return content
        content = content.strip()
        return f"🤖 {content}\n\n"

    def _format_tool_call(self, name: str, args: dict) -> str:
        """格式化工具调用信息"""
        if name == "sql_db_query":
            query = args.get("query", "")
            formatted_query = query.strip()
            return f"⚡ **Executing SQL**\n```sql\n{formatted_query}\n```\n\n"
        elif name == "sql_db_schema":
            table_names = args.get("table_names", "")
            if isinstance(table_names, list):
                table_names = ", ".join(table_names)
            if table_names:
                return f"🔍 **Checking Schema:** `{table_names}`\n\n"
            else:
                return f"🔍 **Checking Schema...**\n\n"
        elif name == "sql_db_list_tables":
            return f"📋 **Listing Tables...**\n\n"
        elif name == "sql_db_query_checker":
            return f"✅ **Validating Query...**\n\n"
        return None

    def _format_tool_result(self, name: str, content: str) -> str:
        """格式化工具执行结果"""
        if "sql" in name.lower():
            if "error" not in content.lower():
                return f"✓ Query executed successfully\n\n"
            else:
                error_content = content[:300].strip()
                return f"✗ **Query failed:** {error_content}\n\n"
        return None

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定的任务"""
        if task_id in self.running_tasks:
            self.running_tasks[task_id]["cancelled"] = True
            # 同时标记工具调用管理器中的会话
            session_id = self.running_tasks[task_id].get("session_id")
            if session_id:
                ctx = self.tool_manager.get_session(session_id)
                ctx.should_terminate = True
                ctx.termination_reason = "用户主动取消"
            return True
        return False

    def get_running_tasks(self):
        """获取当前运行中的任务列表"""
        return list(self.running_tasks.keys())

    def get_available_skills(self):
        """获取所有可用的技能列表"""
        return self.available_skills
