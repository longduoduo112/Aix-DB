"""
数据源选择节点
如果用户查询中没有明确指定数据源，使用 LLM 从多个数据源中选择合适的一个
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, List

from langchain_core.messages import SystemMessage, HumanMessage

from agent.text2sql.state.agent_state import AgentState
from agent.text2sql.template import PromptBuilder
from common.llm_util import get_llm
from model.db_connection_pool import get_db_pool
from services.datasource_service import DatasourceService

logger = logging.getLogger(__name__)


async def datasource_selector(state: AgentState) -> AgentState:
    """
    数据源选择节点
    1. 检查 datasource_id 是否已存在
    2. 如果不存在，获取所有数据源列表
    3. 使用 LLM 根据用户查询选择最合适的数据源
    4. 更新 state["datasource_id"]
    """
    logger.info("---进入数据源选择节点---")

    # 检查是否已有 datasource_id
    datasource_id = state.get("datasource_id")
    if datasource_id:
        logger.info(f"数据源已指定: {datasource_id}，跳过数据源选择")
        return state

    # 获取用户查询
    user_query = state.get("user_query", "")
    if not user_query:
        logger.warning("用户查询为空，无法选择数据源")
        return state

    # 获取所有数据源列表
    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            datasources = DatasourceService.get_datasource_list(session)

            if not datasources:
                # 典型场景：原对话绑定的数据源已被删除，或当前空间下无可用数据源
                msg = "当前对话关联的数据源已不存在或无可用的数据源，请重新选择数据源后再尝试。"
                logger.warning(f"没有可用的数据源: {msg}")
                # 将提示信息写入状态，由后续异常节点统一输出给用户
                state["error_message"] = msg
                return state

            # 构建数据源列表（包含 id、name、description）
            datasource_list: List[Dict[str, Any]] = []
            for ds in datasources:
                datasource_list.append({
                    "id": ds.id,
                    "name": ds.name or "",
                    "description": ds.description or "",
                })

            logger.info(f"获取到 {len(datasource_list)} 个数据源")

    except Exception as e:
        logger.error(f"获取数据源列表失败: {e}", exc_info=True)
        return state

    # 使用 PromptBuilder 构建数据源选择提示词
    prompt_builder = PromptBuilder()

    try:
        system_prompt, user_prompt = prompt_builder.build_datasource_prompt(
            question=user_query,
            datasource_list=datasource_list,
            lang="简体中文",
        )

        # 构建消息列表
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # 调用 LLM
        llm = get_llm(0)
        response = llm.invoke(messages)

        # 解析响应（JSON 格式）
        response_content = response.content.strip()

        # 清理 JSON 字符串（移除可能的 markdown 代码块标记）
        if "```json" in response_content:
            response_content = response_content.split("```json")[1]
        if "```" in response_content:
            response_content = response_content.split("```")[0]
        response_content = response_content.strip()

        # 解析 JSON
        try:
            result = json.loads(response_content)

            # 检查是否成功选择数据源
            if "id" in result:
                selected_id = int(result["id"])
                state["datasource_id"] = selected_id
                logger.info(f"LLM 选择的数据源 ID: {selected_id}")
            elif "fail" in result:
                fail_reason = result.get("fail", "没有找到匹配的数据源或数据源已删除")
                logger.warning(f"LLM 未能选择数据源: {fail_reason}")
                # 记录到状态，供异常节点返回给前端
                state["error_message"] = f"数据源选择失败：{fail_reason}"
            else:
                logger.warning(f"LLM 响应格式不正确: {result}")
                state["error_message"] = "数据源选择失败：LLM 响应格式不正确，无法识别可用的数据源。"

        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应 JSON 失败: {e}")
            logger.error(f"响应内容: {response_content[:500]}")
            state["error_message"] = "数据源选择失败：无法解析大模型返回结果。"
        except ValueError as e:
            logger.error(f"解析数据源 ID 失败: {e}")
            logger.error(f"响应内容: {response_content[:500]}")
            state["error_message"] = "数据源选择失败：解析数据源 ID 出错。"

    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"数据源选择过程中发生错误: {e}", exc_info=True)
        # 兜底异常提示
        if not state.get("error_message"):
            state["error_message"] = "数据源选择过程中发生未知错误，请稍后重试或联系管理员。"

    return state
