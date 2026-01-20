"""
推荐问题生成节点
根据当前数据源和用户查询，生成相关的推荐问题
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, List

from langchain_core.messages import SystemMessage, HumanMessage

from agent.text2sql.state.agent_state import AgentState
from agent.text2sql.template import PromptBuilder, format_schema_to_m_schema
from common.llm_util import get_llm
from model.db_connection_pool import get_db_pool
from services.datasource_service import DatasourceService

logger = logging.getLogger(__name__)


def question_recommender(state: AgentState) -> AgentState:
    """
    推荐问题生成节点
    1. 获取当前数据源的 schema
    2. 使用 LLM 根据 schema 和用户查询生成推荐问题
    3. 保存推荐问题到 state["recommended_questions"]
    """
    logger.info("---进入推荐问题生成节点---")

    # 获取数据源 ID
    datasource_id = state.get("datasource_id")
    if not datasource_id:
        logger.warning("数据源 ID 为空，无法生成推荐问题")
        return state

    # 获取用户查询
    user_query = state.get("user_query", "")

    # 获取数据库信息（schema）
    db_info = state.get("db_info", {})
    if not db_info:
        logger.warning("数据库信息为空，无法生成推荐问题")
        return state

    # 获取数据库类型和名称
    db_type = "mysql"  # 默认类型
    db_name = "database"  # 默认数据库名

    try:
        db_pool = get_db_pool()
        with db_pool.get_session() as session:
            ds = DatasourceService.get_datasource_by_id(session, datasource_id)
            if ds:
                db_type = ds.type
                # 尝试从配置中获取数据库名 / Schema
                try:
                    from common.datasource_util import DatasourceConfigUtil
                    config = DatasourceConfigUtil.decrypt_config(ds.configuration)
                    database = config.get("database")
                    db_schema = config.get("dbSchema")
                    # 对于需要 Schema 的数据库（如 PostgreSQL），优先使用 dbSchema
                    if db_type in ["pg", "oracle", "sqlServer", "kingbase", "redshift", "dm"] and db_schema:
                        db_name = db_schema
                    else:
                        db_name = database or db_schema or "database"
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"获取数据源信息失败: {e}，使用默认值")

    # 格式化 schema 为 M-Schema 格式
    try:
        schema_str = format_schema_to_m_schema(
            db_info=db_info,
            db_name=db_name,
            db_type=db_type,
        )
    except Exception as e:
        logger.error(f"格式化 schema 失败: {e}", exc_info=True)
        return state

    # 获取历史问题列表（如果有的话，可以从 state 中获取或从数据库查询）
    # 目前暂时使用空列表
    old_questions: List[str] = []

    # 使用 PromptBuilder 构建推荐问题提示词
    prompt_builder = PromptBuilder()

    try:
        system_prompt, user_prompt = prompt_builder.build_guess_question_prompt(
            schema=schema_str,
            question=user_query,
            old_questions=old_questions,
            lang="简体中文",
            articles_number=4,  # 生成 4 个推荐问题
        )

        # 构建消息列表
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # 调用 LLM
        llm = get_llm(0)
        response = llm.invoke(messages)

        # 解析响应（JSON 数组格式）
        response_content = response.content.strip()

        # 清理 JSON 字符串（移除可能的 markdown 代码块标记）
        if "```json" in response_content:
            response_content = response_content.split("```json")[1]
        if "```" in response_content:
            response_content = response_content.split("```")[0]
        response_content = response_content.strip()

        # 解析 JSON
        try:
            recommended_questions = json.loads(response_content)

            # 验证响应格式
            if isinstance(recommended_questions, list):
                # 确保所有元素都是字符串
                recommended_questions = [str(q) for q in recommended_questions if q]
                state["recommended_questions"] = recommended_questions
                logger.info(f"生成 {len(recommended_questions)} 个推荐问题")
            else:
                logger.warning(f"推荐问题格式错误，期望列表，得到: {type(recommended_questions)}")
                state["recommended_questions"] = []

        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应 JSON 失败: {e}")
            logger.error(f"响应内容: {response_content[:500]}")
            state["recommended_questions"] = []

    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"推荐问题生成过程中发生错误: {e}", exc_info=True)
        state["recommended_questions"] = []

    return state
