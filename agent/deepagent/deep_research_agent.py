"""
Deep Research Agent - 基于 DeepAgents 的 Text-to-SQL 智能体

精简实时流推送架构：
1. 保留 create_deep_agent 核心架构
2. 实时 SSE 流推送，用户感知每一步执行过程
3. 不保存对话历史记录
"""

import asyncio
import json
import logging
import os
import time
import traceback
from typing import Optional

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.deepagent.tools.native_sql_tools import (
    set_native_datasource_info,
    sql_db_list_tables,
    sql_db_query,
    sql_db_query_checker,
    sql_db_schema,
    sql_db_table_relationship,
)
from agent.deepagent.tools.tool_call_manager import get_tool_call_manager
from common.datasource_util import (
    DB,
    ConnectType,
    DatasourceConfigUtil,
    DatasourceConnectionUtil,
)
from common.llm_util import get_llm
from constants.code_enum import DataTypeEnum
from model.db_connection_pool import get_db_pool
from services.datasource_service import DatasourceService
from services.user_service import decode_jwt_token

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))


class DeepAgent:
    """基于 DeepAgents 的 Text-to-SQL 智能体，实时流推送架构"""

    # 递归限制：子代理也消耗递归次数，150 足够完成复杂任务同时防止无限循环
    DEFAULT_RECURSION_LIMIT = 150

    # LLM 超时（秒）- 公网大模型高峰期可能需要较长时间
    DEFAULT_LLM_TIMEOUT = 10 * 60

    # SSE 保活间隔（秒）：防止代理/浏览器约 2 分钟无数据断开
    STREAM_KEEPALIVE_INTERVAL = 25

    # 总任务超时（秒）- 与前端 fetch timeout 和 Nginx proxy_read_timeout 对齐
    TASK_TIMEOUT = 15 * 60

    def __init__(self):
        self.tool_manager = get_tool_call_manager()
        self.available_skills = self._load_available_skills()

        # 从环境变量读取配置
        self.RECURSION_LIMIT = int(
            os.getenv("RECURSION_LIMIT", self.DEFAULT_RECURSION_LIMIT)
        )
        self.LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", self.DEFAULT_LLM_TIMEOUT))

    # ==================== 技能加载 ====================

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

    def get_available_skills(self):
        """获取所有可用的技能列表"""
        return self.available_skills

    # ==================== SSE 响应工具方法 ====================

    @staticmethod
    def _create_response(
        content: str,
        message_type: str = "continue",
        data_type: str = DataTypeEnum.ANSWER.value[0],
    ) -> str:
        """封装 SSE 响应结构"""
        res = {
            "data": {"messageType": message_type, "content": content},
            "dataType": data_type,
        }
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    async def _safe_write(
        self,
        response,
        content: str,
        message_type: str = "continue",
        data_type: str = None,
    ) -> bool:
        """安全地写入 SSE 响应，连接断开时返回 False"""
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

    @staticmethod
    def _is_connection_error(exception: Exception) -> bool:
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

    # ==================== 格式化方法 ====================

    @staticmethod
    def _format_tool_call(name: str, args: dict) -> Optional[str]:
        """格式化工具调用信息"""
        if name == "sql_db_query":
            query = args.get("query", "")
            return f"⚡ **Executing SQL**\n```sql\n{query.strip()}\n```\n\n"
        elif name == "sql_db_schema":
            table_names = args.get("table_names", "")
            if isinstance(table_names, list):
                table_names = ", ".join(table_names)
            if table_names:
                return f"🔍 **Checking Schema:** `{table_names}`\n\n"
            return "🔍 **Checking Schema...**\n\n"
        elif name == "sql_db_list_tables":
            return "📋 **Listing Tables...**\n\n"
        elif name == "sql_db_query_checker":
            return "✅ **Validating Query...**\n\n"
        return None

    @staticmethod
    def _format_tool_result(name: str, content: str) -> Optional[str]:
        """格式化工具执行结果"""
        if "sql" in name.lower():
            if "error" not in content.lower():
                return "✓ Query executed successfully\n\n"
            else:
                return f"✗ **Query failed:** {content[:300].strip()}\n\n"
        return None

    # ==================== Agent 创建 ====================

    def _create_sql_deep_agent(self, datasource_id: int, session_id: str):
        """
        创建 text-to-SQL Deep Agent，支持所有数据源类型

        Args:
            datasource_id: 数据源 ID
            session_id: 会话 ID，用于工具调用管理
        """
        logger.info(f"创建 Deep Agent - 数据源: {datasource_id}, 会话: {session_id}")

        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            datasource = DatasourceService.get_datasource_by_id(session, datasource_id)
            if not datasource:
                raise ValueError(f"数据源 {datasource_id} 不存在")

            db_enum = DB.get_db(datasource.type, default_if_none=True)

            model = get_llm(timeout=self.LLM_TIMEOUT)
            logger.info(
                f"LLM 模型已创建，超时: {self.LLM_TIMEOUT}秒，"
                f"递归限制: {self.RECURSION_LIMIT}"
            )

            if db_enum.connect_type == ConnectType.sqlalchemy:
                logger.info(
                    f"数据源 {datasource_id} ({datasource.type}) 使用 SQLAlchemy 连接"
                )
                config = DatasourceConfigUtil.decrypt_config(datasource.configuration)
                uri = DatasourceConnectionUtil.build_connection_uri(
                    datasource.type, config
                )
                db = SQLDatabase.from_uri(uri, sample_rows_in_table_info=3)
                toolkit = SQLDatabaseToolkit(db=db, llm=model)
                sql_tools = toolkit.get_tools()
            else:
                logger.info(
                    f"数据源 {datasource_id} ({datasource.type}) 使用原生驱动连接"
                )
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

        agent = create_deep_agent(
            model=model,
            memory=[os.path.join(current_dir, "AGENTS.md")],
            skills=[os.path.join(current_dir, "skills/")],
            tools=sql_tools,
            backend=FilesystemBackend(root_dir=current_dir),
        )
        return agent

    # ==================== 核心执行 ====================

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
        运行智能体，实时流推送执行过程

        Args:
            query: 用户输入
            response: SSE 响应对象
            session_id: 会话ID
            uuid_str: 唯一标识（兼容参数，不再使用）
            user_token: 用户令牌
            file_list: 附件（兼容参数，不再使用）
            datasource_id: 数据源ID
        """
        if not datasource_id:
            await self._safe_write(
                response,
                "❌ **错误**: 必须提供数据源ID (datasource_id)",
                "error",
                DataTypeEnum.ANSWER.value[0],
            )
            return

        # 获取用户信息，生成会话标识
        user_dict = await decode_jwt_token(user_token)
        task_id = user_dict["id"]
        effective_session_id = session_id or f"sql-agent-{datasource_id}-{task_id}"

        # 重置工具调用状态
        self.tool_manager.reset_session(effective_session_id)

        start_time = time.time()
        connection_closed = False

        try:
            agent = self._create_sql_deep_agent(datasource_id, effective_session_id)

            config = {
                "configurable": {"thread_id": effective_session_id},
                "recursion_limit": self.RECURSION_LIMIT,
            }

            try:
                connection_closed = await asyncio.wait_for(
                    self._stream_response(
                        agent, config, query, response, effective_session_id
                    ),
                    timeout=self.TASK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                logger.error(
                    f"任务总超时 ({self.TASK_TIMEOUT}秒) - 实际耗时: {elapsed:.0f}秒"
                )
                await self._safe_write(
                    response,
                    f"\n> ⚠️ **执行超时**: 任务执行时间超过上限"
                    f"（{self.TASK_TIMEOUT // 60} 分钟），请简化查询后重试。",
                    "error",
                    DataTypeEnum.ANSWER.value[0],
                )

        except asyncio.CancelledError:
            logger.info(f"任务被取消 - 会话: {effective_session_id}")
            connection_closed = True
            raise
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"客户端连接已断开: {type(e).__name__}")
                connection_closed = True
            else:
                logger.error(f"Agent运行异常: {e}")
                traceback.print_exception(e)
                try:
                    await self._safe_write(
                        response,
                        f"❌ **错误**: 智能体运行异常\n\n```\n{str(e)[:200]}\n```\n",
                        "error",
                        DataTypeEnum.ANSWER.value[0],
                    )
                except Exception:
                    pass
        finally:
            # 发送流结束标记
            if not connection_closed:
                try:
                    await self._safe_write(
                        response, "", "end", DataTypeEnum.STREAM_END.value[0]
                    )
                except Exception as e:
                    logger.warning(f"发送 STREAM_END 失败: {e}")

            elapsed = time.time() - start_time
            stats = self.tool_manager.get_stats(effective_session_id)
            logger.info(
                f"任务结束 - 会话: {effective_session_id}, "
                f"耗时: {elapsed:.2f}秒, 工具调用统计: {stats}"
            )

    async def _stream_response(
        self,
        agent,
        config: dict,
        query: str,
        response,
        session_id: str,
    ) -> bool:
        """
        处理 agent 流式响应，实时推送到前端

        Returns:
            bool: 连接是否已断开（True=断开）
        """
        token_count = 0
        connection_closed = False

        logger.info(f"开始流式响应 - 会话: {session_id}, 查询: {query[:100]}")

        stream_iter = agent.astream(
            input={"messages": [HumanMessage(content=query)]},
            config=config,
            stream_mode=["messages", "updates"],
        )
        stream_anext = stream_iter.__anext__

        try:
            while True:
                # 带超时等待下一 chunk，超时则发送 SSE 保活
                try:
                    mode, chunk = await asyncio.wait_for(
                        stream_anext(), timeout=self.STREAM_KEEPALIVE_INTERVAL
                    )
                except asyncio.TimeoutError:
                    try:
                        await response.write(
                            'data: {"data":{"messageType": "info", "content": ""}, "dataType": "keepalive"}\n\n'
                        )
                        if hasattr(response, "flush"):
                            await response.flush()
                    except Exception as e:
                        if self._is_connection_error(e):
                            connection_closed = True
                            break
                        raise
                    continue
                except StopAsyncIteration:
                    break

                # 检查工具调用管理器是否触发终止
                ctx = self.tool_manager.get_session(session_id)
                if ctx.should_terminate:
                    logger.warning(f"工具调用管理器触发终止: {ctx.termination_reason}")
                    await self._safe_write(
                        response,
                        f"\n> ⚠️ **执行中止**\n\n{ctx.termination_reason}",
                        "warning",
                        DataTypeEnum.ANSWER.value[0],
                    )
                    break

                # ---- messages 模式：token 级别实时流式输出 ----
                if mode == "messages":
                    message_chunk, metadata = chunk
                    node_name = metadata.get("langgraph_node", "")

                    # 跳过工具节点（工具结果通过 updates 模式处理）
                    if node_name == "tools":
                        continue

                    if hasattr(message_chunk, "content") and message_chunk.content:
                        token_text = self._extract_text(message_chunk.content)
                        if token_text:
                            token_count += 1
                            if not await self._safe_write(response, token_text):
                                connection_closed = True
                                break

                            # 含报告分隔符时立即刷新，便于前端尽早展示 HTML
                            if token_count % 10 == 0 or "REPORT_HTML_" in token_text:
                                if hasattr(response, "flush"):
                                    try:
                                        await response.flush()
                                    except Exception as e:
                                        if self._is_connection_error(e):
                                            connection_closed = True
                                            break
                                        raise

                            await asyncio.sleep(0)

                # ---- updates 模式：工具调用与结果 ----
                elif mode == "updates":
                    for node_name, node_output in chunk.items():
                        if connection_closed:
                            break
                        if not isinstance(node_output, dict) or "messages" not in node_output:
                            continue

                        messages = node_output["messages"]
                        if not isinstance(messages, list):
                            messages = [messages]

                        for msg in messages:
                            if not await self._process_update_message(
                                msg, response
                            ):
                                connection_closed = True
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
            logger.info(f"流被取消 - 会话: {session_id}")
            connection_closed = True
            raise
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"客户端连接已断开: {type(e).__name__}")
                connection_closed = True
            else:
                logger.error(f"流式响应异常: {type(e).__name__}: {e}", exc_info=True)
                try:
                    await self._safe_write(
                        response,
                        f"\n> ❌ **处理异常**: {str(e)[:200]}\n\n请稍后重试。",
                        "error",
                        DataTypeEnum.ANSWER.value[0],
                    )
                except Exception:
                    pass

        logger.info(f"流式响应结束 - 会话: {session_id}, token数: {token_count}")
        return connection_closed

    async def _process_update_message(self, msg, response) -> bool:
        """
        处理 updates 模式下的单条消息

        Returns:
            bool: True=成功, False=连接断开
        """
        try:
            if isinstance(msg, AIMessage):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        name = tc.get("name", "unknown")
                        args = tc.get("args", {})
                        tool_msg = self._format_tool_call(name, args)
                        if tool_msg:
                            if not await self._safe_write(response, "\n\n"):
                                return False
                            if not await self._safe_write(response, tool_msg, "info"):
                                return False

            elif isinstance(msg, ToolMessage):
                name = getattr(msg, "name", "")
                content_str = str(msg.content) if msg.content else ""
                tool_result_msg = self._format_tool_result(name, content_str)
                if tool_result_msg:
                    msg_type = "error" if "error" in content_str.lower() else "info"
                    if not await self._safe_write(response, tool_result_msg, msg_type):
                        return False

            return True
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"处理消息时连接断开: {type(e).__name__}")
                return False
            raise

    @staticmethod
    def _extract_text(content) -> str:
        """从消息内容中提取文本（兼容字符串和列表格式）"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
            return "".join(parts)
        return str(content) if content else ""

    # ==================== 兼容接口 ====================

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务（兼容接口，供 llm_service 调用）"""
        # 简化实现：通过工具管理器标记终止
        # task_id 在新架构中不再直接跟踪，但可通过工具管理器间接终止
        logger.info(f"收到取消请求: {task_id}")
        return False
