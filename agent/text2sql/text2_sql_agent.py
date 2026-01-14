import asyncio
import json
import logging
import os
from typing import Dict, Any, Optional, Union

from langgraph.graph.state import CompiledStateGraph

from agent.text2sql.analysis.graph import create_graph
from agent.text2sql.state.agent_state import AgentState
from constants.code_enum import DataTypeEnum, IntentEnum
from services.user_service import add_user_record, decode_jwt_token
from langfuse import get_client
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)


class Text2SqlAgent:
    """
    文本语言转SQL代理
    """

    def __init__(self):
        # 存储运行中的任务
        self.running_tasks = {}
        # 获取环境变量控制是否显示思考过程，默认为开启
        self.show_thinking_process = os.getenv("SHOW_THINKING_PROCESS", "true").lower() == "true"
        # 是否启用链路追踪
        self.ENABLE_TRACING = os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "true"

    async def run_agent(
        self,
        query: str,
        response=None,
        chat_id: str = None,
        uuid_str: str = None,
        user_token=None,
        datasource_id: int = None,
    ) -> None:
        """
        运行智能体
        :param query: 用户输入
        :param response: 响应对象
        :param chat_id: 会话ID，用于区分同一轮对话
        :param uuid_str: 自定义ID，用于唯一标识一次问答
        :param user_token: 用户登录的token
        :param datasource_id: 数据源ID
        :return: None
        """
        t02_answer_data = []
        t04_answer_data = {}
        current_step = None

        try:
            # 获取用户信息（只调用一次）
            user_dict = await decode_jwt_token(user_token)
            user_id = user_dict.get("id", 1)  # 默认为管理员
            task_id = user_dict["id"]
            
            initial_state = AgentState(
                user_query=query,
                attempts=0,
                correct_attempts=0,
                datasource_id=datasource_id,
                user_id=user_id
            )
            
            # 检查数据源权限（如果指定了 datasource_id）
            # 权限检查结果会通过 datasource_selector 节点处理，统一通过 error_handler 节点流式输出
            if datasource_id:
                from model.db_connection_pool import get_db_pool
                from model.datasource_models import DatasourceAuth
                from common.permission_util import is_admin
                from sqlalchemy import and_
                
                db_pool = get_db_pool()
                with db_pool.get_session() as session:
                    # 管理员跳过权限检查
                    if not is_admin(user_id):
                        # 检查用户是否有该数据源的权限
                        auth = session.query(DatasourceAuth).filter(
                            and_(
                                DatasourceAuth.datasource_id == datasource_id,
                                DatasourceAuth.user_id == user_id,
                                DatasourceAuth.enable == True
                            )
                        ).first()
                        
                        if not auth:
                            # 无权限，设置错误消息，让 error_handler 节点统一处理
                            error_msg = "您没有访问该数据源的权限，请联系管理员授权。"
                            logger.warning(f"用户 {user_id} 尝试访问未授权的数据源 {datasource_id}")
                            initial_state["error_message"] = error_msg
                            initial_state["datasource_id"] = None  # 清空 datasource_id，让流程进入 error_handler
            graph: CompiledStateGraph = create_graph(datasource_id)

            # 标识对话状态
            task_context = {"cancelled": False}
            self.running_tasks[task_id] = task_context

            # 准备 tracing 配置
            config = {}
            if self.ENABLE_TRACING:
                langfuse_handler = CallbackHandler()
                callbacks = [langfuse_handler]
                config = {
                    "callbacks": callbacks,
                    "metadata": {
                        "langfuse_session_id": chat_id,
                    },
                }

            # 异步流式执行
            stream_kwargs = {
                "input": initial_state,
                "stream_mode": "updates",
                "config": config,
            }

            # 如果启用 tracing，包裹在 trace 上下文中
            if self.ENABLE_TRACING:
                langfuse = get_client()
                with langfuse.start_as_current_observation(
                    input=query,
                    as_type="agent",
                    name="数据问答",
                ) as rootspan:
                    # 使用之前获取的 user_id，避免重复调用
                    rootspan.update_trace(session_id=chat_id, user_id=user_id)

                    async for chunk_dict in graph.astream(**stream_kwargs):
                        current_step, t02_answer_data = await self._process_chunk(
                            chunk_dict, response, task_id, current_step, t02_answer_data, t04_answer_data
                        )
            else:
                async for chunk_dict in graph.astream(**stream_kwargs):
                    current_step, t02_answer_data = await self._process_chunk(
                        chunk_dict, response, task_id, current_step, t02_answer_data, t04_answer_data
                    )

            # 流结束时关闭最后的details标签
            if self.show_thinking_process:
                if current_step is not None and current_step not in ["summarize", "data_render", "error_handler"]:
                    await self._close_current_step(response, t02_answer_data)

            # 只有在未取消的情况下才保存记录
            if not self.running_tasks[task_id]["cancelled"]:
                await add_user_record(
                    uuid_str,
                    chat_id,
                    query,
                    t02_answer_data,
                    t04_answer_data,
                    IntentEnum.DATABASE_QA.value[0],
                    user_token,
                    {},
                    datasource_id,
                )

        except asyncio.CancelledError:
            await response.write(self._create_response("\n> 这条消息已停止", "info", DataTypeEnum.ANSWER.value[0]))
            await response.write(self._create_response("", "end", DataTypeEnum.STREAM_END.value[0]))
        except Exception as e:
            logger.error(f"Error in run_agent: {str(e)}", exc_info=True)
            error_msg = f"处理过程中发生错误: {str(e)}"
            await self._send_response(response, error_msg, "error")

    async def _process_chunk(
        self,
        chunk_dict,
        response,
        task_id,
        current_step,
        t02_answer_data,
        t04_answer_data,
    ):
        """
        处理单个流式块数据
        """
        # 检查是否已取消
        if task_id in self.running_tasks and self.running_tasks[task_id]["cancelled"]:
            if self.show_thinking_process:
                await self._send_response(response, "</details>\n\n", "continue", DataTypeEnum.ANSWER.value[0])
            await response.write(self._create_response("\n> 这条消息已停止", "info", DataTypeEnum.ANSWER.value[0]))
            # 发送最终停止确认消息
            await response.write(self._create_response("", "end", DataTypeEnum.STREAM_END.value[0]))
            raise asyncio.CancelledError()

        langgraph_step, step_value = next(iter(chunk_dict.items()))

        # 处理步骤变更
        current_step, t02_answer_data = await self._handle_step_change(
            response, current_step, langgraph_step, t02_answer_data
        )

        # 处理具体步骤内容
        if step_value:
            await self._process_step_content(response, langgraph_step, step_value, t02_answer_data, t04_answer_data)

        return current_step, t02_answer_data

    async def _handle_step_change(
        self,
        response,
        current_step: Optional[str],
        new_step: str,
        t02_answer_data: list,
    ) -> tuple:
        """
        处理步骤变更
        """
        if self.show_thinking_process:
            if new_step != current_step:
                # 如果之前有打开的步骤，先关闭它
                if current_step is not None and current_step not in ["summarize", "data_render", "error_handler"]:
                    await self._close_current_step(response, t02_answer_data)

                # 打开新的步骤 (除了 summarize、data_render 和 error_handler) think_html 标签里面添加open属性控制思考过程是否默认展开显示
                # error_handler 是异常节点，直接显示错误信息，不需要显示思考过程标签
                # datasource_selector 和 question_recommender 也不展示思考过程
                if new_step not in [
                    "summarize",
                    "data_render",
                    "error_handler",
                    "datasource_selector",
                    "question_recommender",
                ]:
                    think_html = f"""<details style="color:gray;background-color: #f8f8f8;padding: 2px;border-radius: 
                    6px;margin-top:5px;">
                                 <summary>{new_step}...</summary>"""
                    await self._send_response(response, think_html, "continue", "t02")
                    t02_answer_data.append(think_html)
        else:
            # 如果不显示思考过程，则只处理特定的步骤
            if new_step in ["summarize", "data_render", "error_handler"]:
                # 对于需要显示的步骤，确保之前的步骤已关闭
                if current_step is not None and current_step not in ["summarize", "data_render", "error_handler"]:
                    pass  # 不需要关闭details标签，因为我们根本没有打开它

        return new_step, t02_answer_data

    async def _close_current_step(self, response, t02_answer_data: list) -> None:
        """
        关闭当前步骤的details标签
        """
        if self.show_thinking_process:
            close_tag = "</details>\n\n"
            await self._send_response(response, close_tag, "continue", "t02")
            t02_answer_data.append(close_tag)

    async def _process_step_content(
        self,
        response,
        step_name: str,
        step_value: Dict[str, Any],
        t02_answer_data: list,
        t04_answer_data: Dict[str, Any],
    ) -> None:
        """
        处理各个步骤的内容
        """
        content_map = {
            # 数据源异常节点：仅输出友好的错误提示，不再继续后续步骤
            "error_handler": lambda: step_value.get(
                "error_message",
                "当前没有可用的数据源，请联系管理员。",
            ),
            "schema_inspector": lambda: self._format_db_info_with_bm25(step_value),
            "table_relationship": lambda: json.dumps(step_value["table_relationship"], ensure_ascii=False),
            "sql_generator": lambda: step_value["generated_sql"],
            # 权限过滤节点：输出注入权限后的 SQL，如果没有则回退到原始 SQL
            "permission_filter": lambda: step_value.get("filtered_sql")
            or step_value.get("generated_sql", "No SQL query generated"),
            # SQL 执行节点：成功/失败分别返回不同信息，失败时截取一段错误详情
            "sql_executor": lambda: self._format_sql_execution_message(step_value.get("execution_result")),
            # 图表生成节点：输出最终选定的图表类型
            "chart_generator": lambda: self._format_chart_type_message(step_value),
            "summarize": lambda: step_value["report_summary"],
            "data_render": lambda: step_value.get("render_data", {}) if step_value.get("render_data") else {},  # 返回对象，不是 JSON 字符串
        }

        if step_name in content_map:
            content = content_map[step_name]()
            # 对于 data_render，content 已经是对象，不需要添加前缀

            # 数据渲染节点返回业务数据
            data_type = (
                DataTypeEnum.BUS_DATA.value[0] if step_name == "data_render" else DataTypeEnum.ANSWER.value[0]
            )

            # 根据环境变量决定是否发送非关键步骤的内容
            # error_handler 是异常节点，必须发送错误信息给用户
            # schema_inspector 需要向用户解释 BM25 分词和表筛选结果，也应在不展示思考过程时输出
            # chart_generator 需要向用户展示最终选定的图表类型，也应在不展示思考过程时输出
            should_send = self.show_thinking_process or step_name in [
                "summarize",
                "data_render",
                "error_handler",
                "schema_inspector",
                "chart_generator",
            ]

            if should_send:
                await self._send_response(response=response, content=content, data_type=data_type)

                if data_type == DataTypeEnum.ANSWER.value[0]:
                    t02_answer_data.append(content)

            # 这里设置渲染数据
            if step_name == "data_render" and data_type == DataTypeEnum.BUS_DATA.value[0]:
                render_data = step_value.get("render_data", {})
                t04_answer_data.clear()
                t04_answer_data.update({"data": render_data, "dataType": data_type})

            # 对于非渲染步骤，刷新响应
            if step_name != "data_render":
                if hasattr(response, "flush"):
                    await response.flush()
                await asyncio.sleep(0)

        # 处理推荐问题：将推荐问题合并到已有的图表数据中发送到前端（在 content_map 之外处理）
        if step_name == "question_recommender":
            recommended_questions = step_value.get("recommended_questions", [])
            logger.info(f"question_recommender 步骤: 获取到推荐问题数量: {len(recommended_questions) if recommended_questions else 0}, t04_answer_data: {t04_answer_data}")
            if recommended_questions and isinstance(recommended_questions, list) and len(recommended_questions) > 0:
                # 获取已有的图表数据，如果没有则创建新的数据结构
                if t04_answer_data and "data" in t04_answer_data and isinstance(t04_answer_data["data"], dict) and t04_answer_data["data"]:
                    # 将推荐问题添加到已有的图表数据中
                    t04_answer_data["data"]["recommended_questions"] = recommended_questions
                    # 重新发送包含推荐问题的完整数据
                    await self._send_response(
                        response=response,
                        content=t04_answer_data["data"],
                        data_type=t04_answer_data.get("dataType", DataTypeEnum.BUS_DATA.value[0])
                    )
                    logger.info(f"已添加 {len(recommended_questions)} 个推荐问题到图表数据并发送到前端，完整数据: {t04_answer_data}")
                else:
                    # 如果没有图表数据，单独发送推荐问题（这种情况不应该发生，因为 data_render 应该在 question_recommender 之前执行）
                    logger.warning(f"question_recommender 步骤: t04_answer_data 为空或无效，t04_answer_data: {t04_answer_data}")
                    recommended_questions_data = {
                        "recommended_questions": recommended_questions
                    }
                    await self._send_response(
                        response=response,
                        content=recommended_questions_data,
                        data_type=DataTypeEnum.BUS_DATA.value[0]
                    )
                    logger.info(f"已发送 {len(recommended_questions)} 个推荐问题到前端（无图表数据）: {recommended_questions[:2] if len(recommended_questions) > 2 else recommended_questions}")
            else:
                logger.warning(f"question_recommender 步骤: 推荐问题为空或格式错误，recommended_questions: {recommended_questions}")

    @staticmethod
    def _format_sql_execution_message(execution_result: Any) -> str:
        """
        格式化 SQL 执行结果信息：
        - 成功：返回固定成功提示
        - 失败：返回带有部分错误信息的提示，避免错误信息过长
        """
        try:
            if not execution_result:
                return "执行sql语句失败"

            # ExecutionResult 为 pydantic BaseModel，直接访问属性
            success = getattr(execution_result, "success", False)
            if success:
                return "执行sql语句成功"

            raw_error = getattr(execution_result, "error", "") or ""
            # 截取前 200 个字符，避免返回过长
            snippet = raw_error.strip().replace("\n", " ").replace("\r", " ")
            max_len = 200
            if len(snippet) > max_len:
                snippet = snippet[:max_len] + "..."

            # 最终返回给前端的提示
            return f"执行sql语句失败: {snippet}" if snippet else "执行sql语句失败"
        except Exception:
            # 兜底，绝不因为格式化错误影响主流程
            return "执行sql语句失败"

    def _format_db_info_with_bm25(self, step_value: Dict[str, Any]) -> str:
        """
        格式化数据库信息，并追加 BM25 分词说明（如果有）。
        格式：先显示关键词，再显示检索到的表信息。
        """
        db_info: Dict[str, Any] = step_value.get("db_info") or {}
        
        # 从 step_value 中获取 BM25 分词信息
        bm25_tokens = step_value.get("bm25_tokens") or []
        user_query = step_value.get("user_query", "")
        
        # 调试日志：检查 step_value 中的字段
        logger.debug(f"schema_inspector step_value keys: {list(step_value.keys())}")
        logger.debug(f"bm25_tokens in step_value: {bm25_tokens}, type: {type(bm25_tokens)}")
        logger.debug(f"user_query in step_value: {user_query}")

        # 构建输出内容：先关键词，后表信息
        parts = []
        
        # 1. 关键词部分
        if user_query:
            if isinstance(bm25_tokens, list) and bm25_tokens:
                # 过滤掉无意义的单字符词（如"的"、"各"等），保留有意义的词
                meaningful_tokens = [token for token in bm25_tokens if len(token) > 1 or token.isalnum()]
                # 如果过滤后还有词，使用过滤后的；否则使用原始的
                display_tokens = meaningful_tokens if meaningful_tokens else bm25_tokens
                
                # 只展示前若干个分词，避免过长
                max_tokens = 10
                shown_tokens = display_tokens[:max_tokens]
                tokens_str = "、".join(shown_tokens)
                if len(display_tokens) > max_tokens:
                    tokens_str += " 等"
                
                # 简洁格式：直接显示关键词
                parts.append(f"关键词：{tokens_str}")
                logger.info(f"BM25 分词说明已添加到输出: {tokens_str}")
            else:
                # 分词结果为空时，使用原始查询作为关键词
                parts.append(f"关键词：{user_query}")
                logger.info(f"BM25 分词结果为空，使用原始查询作为关键词: {user_query}")
        
        # 2. 表信息部分（放在关键词下面）
        table_text = self._format_db_info_compact(db_info)
        if table_text:
            parts.append(table_text)
        
        # 组合输出
        return "\n\n".join(parts) if parts else table_text

    @staticmethod
    def _format_chart_type_message(step_value: Dict[str, Any]) -> str:
        """
        格式化图表类型说明，优先从 chart_config 中读取 type，其次从 chart_type 字段读取。
        """
        chart_config = step_value.get("chart_config") or {}
        chart_type = (
            (chart_config.get("type") if isinstance(chart_config, dict) else None)
            or step_value.get("chart_type")
            or "table"
        )
        # 简单直观的提示语
        return f"图表类型：{chart_type}"

    @staticmethod
    def _format_db_info(db_info: Dict[str, Any]) -> str:
        """
        格式化数据库信息，包含表名和注释（旧格式，保持向后兼容）
        :param db_info: 数据库信息
        :return: 格式化后的字符串
        """
        if not db_info:
            return "共检索0张表."

        table_descriptions = []
        for table_name, table_info in db_info.items():
            # 获取表注释
            table_comment = table_info.get("table_comment", "")
            if table_comment:
                table_descriptions.append(f"{table_name}({table_comment})")
            else:
                table_descriptions.append(table_name)

        tables_str = "、".join(table_descriptions)
        return f"共检索{len(db_info)}张表: {tables_str}."

    @staticmethod
    def _format_db_info_compact(db_info: Dict[str, Any]) -> str:
        """
        格式化数据库信息，简洁格式：每行一个表，表名和注释分开显示
        :param db_info: 数据库信息
        :return: 格式化后的字符串
        """
        if not db_info:
            return "检索到 0 张表"

        table_count = len(db_info)
        table_lines = []
        
        for table_name, table_info in db_info.items():
            # 获取表注释
            table_comment = table_info.get("table_comment", "")
            if table_comment:
                table_lines.append(f"  • {table_name} - {table_comment}")
            else:
                table_lines.append(f"  • {table_name}")
        
        tables_text = "\n".join(table_lines)
        return f"检索到 {table_count} 张表：\n{tables_text}"

    @staticmethod
    async def _send_response(
        response, content: Union[str, Dict[str, Any]], message_type: str = "continue", data_type: str = DataTypeEnum.ANSWER.value[0]
    ) -> None:
        """
        发送响应数据
        :param response: 响应对象
        :param content: 响应内容，可以是字符串或字典
        :param message_type: 消息类型
        :param data_type: 数据类型
        """
        if response:
            if data_type == DataTypeEnum.ANSWER.value[0]:
                formatted_message = {
                    "data": {
                        "messageType": message_type,
                        "content": content,
                    },
                    "dataType": data_type,
                }
            else:
                # 适配EChart表格
                formatted_message = {"data": content, "dataType": data_type}

            await response.write("data:" + json.dumps(formatted_message, ensure_ascii=False) + "\n\n")

    @staticmethod
    def _create_response(
        content: str, message_type: str = "continue", data_type: str = DataTypeEnum.ANSWER.value[0]
    ) -> str:
        """
        封装响应结构（保持向后兼容）
        """
        res = {
            "data": {"messageType": message_type, "content": content},
            "dataType": data_type,
        }
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消指定的任务
        :param task_id: 任务ID
        :return: 是否成功取消
        """
        if task_id in self.running_tasks:
            self.running_tasks[task_id]["cancelled"] = True
            return True
        return False
