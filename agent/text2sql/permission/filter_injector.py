"""
权限过滤注入节点
使用 LLM 将权限条件注入到 SQL 语句中
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, List

from langchain_core.messages import SystemMessage, HumanMessage

from agent.text2sql.state.agent_state import AgentState
from agent.text2sql.permission.permission_retriever import (
    get_user_permission_filters,
    get_user_column_permissions,
)
from agent.text2sql.template.prompt_builder import PromptBuilder
from agent.text2sql.template.schema_formatter import get_database_engine_info
from agent.text2sql.analysis.data_render_antv import extract_table_names_sqlglot, extract_table_alias_mapping, DB_TYPE_TO_DIALECT
from common.llm_util import get_llm
from services.datasource_service import DatasourceService
from model.db_connection_pool import get_db_pool

import sqlglot
from sqlglot import parse

logger = logging.getLogger(__name__)
pool = get_db_pool()


def _apply_column_permissions_to_sql(
    sql: str,
    db_type: str,
    table_allowed_fields: Dict[str, set],
    alias_to_table: Dict[str, str],
) -> str:
    """
    基于列权限重写 SELECT 列：移除 enable=false 的字段。
    - 仅处理显式列选择（Column），不强行展开 SELECT *（遇到 * 仅 warning，返回原 SQL）。
    - 支持表别名：若列引用的是别名，使用 alias_to_table 映射回真实表名进行权限判断。
    """
    if not table_allowed_fields:
        return sql

    # 使用数据库类型到 sqlglot 方言的映射，确保所有数据源类型都能正确解析
    dialect = DB_TYPE_TO_DIALECT.get(db_type.lower() if db_type else "mysql", "mysql")
    try:
        expressions = parse(sql, read=dialect)
    except Exception as e:
        logger.warning(f"列权限：SQL 解析失败，跳过列过滤: {e}")
        return sql

    # 反向映射：table_name -> alias（可能为空）
    table_to_alias = {v: k for k, v in (alias_to_table or {}).items()}

    changed = False
    for exp in expressions:
        if not exp:
            continue
        select = exp.find(sqlglot.exp.Select)
        if not select:
            continue

        new_select_exprs = []
        for proj in list(select.expressions):
            # 处理 SELECT * 或 table.*
            if isinstance(proj, sqlglot.exp.Star):
                logger.warning("列权限：检测到 SELECT *，无法安全过滤列（请生成显式列），本次跳过列过滤")
                return sql
            if isinstance(proj, sqlglot.exp.Column) and proj.is_star:
                logger.warning("列权限：检测到 SELECT table.*，无法安全过滤列（请生成显式列），本次跳过列过滤")
                return sql

            # 可能是 Alias(Column AS xxx)
            col_exp = proj
            if isinstance(proj, sqlglot.exp.Alias):
                col_exp = proj.this

            if isinstance(col_exp, sqlglot.exp.Column):
                col_name = col_exp.name
                qualifier = col_exp.table  # 可能是别名 p 或真实表名

                # 解析出真实表名：若 qualifier 是别名，则映射回表名
                real_table = None
                if qualifier:
                    real_table = (alias_to_table or {}).get(qualifier) or qualifier

                # 若没有 qualifier 且只涉及一张受限表，可尝试按那张表判断
                if not real_table and len(table_allowed_fields) == 1:
                    real_table = next(iter(table_allowed_fields.keys()))

                if real_table and real_table in table_allowed_fields:
                    allowed = table_allowed_fields[real_table]
                    if col_name not in allowed:
                        changed = True
                        continue  # 丢弃该列

            new_select_exprs.append(proj)

        if changed:
            # 若全部列都被过滤掉，保底保留第一个列，避免 SQL 语法错误
            if not new_select_exprs and select.expressions:
                new_select_exprs = [select.expressions[0]]
            select.set("expressions", new_select_exprs)

    if not changed:
        return sql

    try:
        # 使用相同的方言映射进行序列化
        return "; ".join([e.sql(dialect=dialect) for e in expressions if e])
    except Exception:
        # 序列化失败，回退原 SQL
        return sql


def permission_filter_injector(state: AgentState) -> AgentState:
    """
    权限过滤注入节点
    1. 获取用户的权限过滤条件
    2. 使用 LLM 将权限条件注入 SQL
    3. 返回过滤后的 SQL
    
    Args:
        state: Agent 状态对象
        
    Returns:
        更新后的 state
    """
    try:
        # 获取生成的SQL
        generated_sql = state.get("generated_sql")
        if not generated_sql or generated_sql == "No SQL query generated":
            logger.warning("没有生成的SQL，跳过权限过滤")
            return state
        
        # 获取数据源ID和用户ID
        datasource_id = state.get("datasource_id")
        user_id_raw = state.get("user_id")
        
        # 确保 user_id 是整数类型
        if user_id_raw is None:
            user_id = 1  # 默认为管理员
            logger.warning("user_id 为空，默认设置为管理员")
        else:
            try:
                user_id = int(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw
            except (ValueError, TypeError):
                logger.warning(f"无法将 user_id 转换为整数: {user_id_raw}，默认设置为管理员")
                user_id = 1
        
        if not datasource_id:
            logger.warning("没有数据源ID，跳过权限过滤")
            return state
        
        logger.info(f"开始权限过滤：datasource_id={datasource_id}, user_id={user_id}, user_id类型={type(user_id)}")
        
        # 获取数据源信息
        with pool.get_session() as session:
            datasource = DatasourceService.get_datasource_by_id(session, datasource_id)
            if not datasource:
                logger.warning(f"数据源不存在: {datasource_id}")
                return state
            
            db_type = datasource.type or "mysql"
        
        # 获取数据库引擎信息
        engine = get_database_engine_info(db_type)
        
        # 获取表名列表：优先使用 state 中的 used_tables，如果为空则从 SQL 中提取
        table_names: Optional[List[str]] = state.get("used_tables")
        
        if not table_names:
            # 从 SQL 中提取表名
            logger.info("state 中没有 used_tables，尝试从 SQL 中提取表名")
            table_names = extract_table_names_sqlglot(generated_sql, db_type)
            if table_names:
                logger.info(f"从 SQL 中提取到表名: {table_names}")
            else:
                logger.warning("无法从 SQL 中提取表名，将获取所有表的权限")
                table_names = None  # 如果为None，则获取所有表的权限
        else:
            logger.info(f"使用 state 中的表名: {table_names}")

        # 提取 SQL 中的表别名映射，并构建 table_name -> alias 映射
        # data_render_antv.extract_table_alias_mapping 返回的是 {alias: table_name}
        alias_to_table = extract_table_alias_mapping(generated_sql, db_type)
        table_to_alias: Dict[str, str] = {v: k for k, v in (alias_to_table or {}).items() if v and k}
        if table_to_alias:
            logger.info(f"SQL 表别名映射(table->alias): {table_to_alias}")
        
        # 获取权限过滤条件
        filters = get_user_permission_filters(
            datasource_id=datasource_id,
            user_id=user_id,
            table_names=table_names,
            table_alias_map=table_to_alias,
        )
        
        logger.info(f"获取到权限过滤条件数量: {len(filters) if filters else 0}")
        if filters:
            for filter_item in filters:
                logger.info(f"  表: {filter_item.get('table')}, 过滤条件: {filter_item.get('filter')[:100]}...")
        
        # 获取列权限（用于 SELECT 列过滤）
        column_allowed = get_user_column_permissions(
            datasource_id=datasource_id,
            user_id=user_id,
            table_names=table_names,
        )
        if column_allowed:
            logger.info(
                f"列权限允许字段: { {k: sorted(list(v))[:10] for k, v in column_allowed.items()} }"
            )

        # 如果没有行权限过滤条件，先默认使用原始 SQL
        if not filters:
            logger.info(f"没有权限过滤条件（datasource_id={datasource_id}, user_id={user_id}, table_names={table_names}），直接返回原始SQL")
            # 仍然应用列权限（如果有）
            final_sql = _apply_column_permissions_to_sql(
                generated_sql, db_type, column_allowed, alias_to_table
            )
            state["filtered_sql"] = final_sql
            return state
        
        # 使用 PromptBuilder 构建权限过滤提示词
        prompt_builder = PromptBuilder()
        
        system_prompt, user_prompt = prompt_builder.build_permission_prompt(
            sql=generated_sql,
            filters=filters,
            engine=engine,
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
            
            if result.get("success", True):
                filtered_sql = result.get("sql", generated_sql)
                # 对注入后的 SQL 应用列权限过滤
                filtered_sql = _apply_column_permissions_to_sql(
                    filtered_sql, db_type, column_allowed, alias_to_table
                )
                state["filtered_sql"] = filtered_sql
                logger.info(f"权限过滤成功，原始SQL: {generated_sql[:100]}...")
                logger.info(f"过滤后SQL: {filtered_sql[:100]}...")
            else:
                error_message = result.get("message", "无法注入权限过滤条件")
                logger.warning(f"权限过滤失败: {error_message}")
                # 如果权限过滤失败，使用原始SQL
                final_sql = _apply_column_permissions_to_sql(
                    generated_sql, db_type, column_allowed, alias_to_table
                )
                state["filtered_sql"] = final_sql
                
        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应 JSON 失败: {e}")
            logger.error(f"响应内容: {response_content[:500]}")
            # 如果解析失败，使用原始SQL
            final_sql = _apply_column_permissions_to_sql(
                generated_sql, db_type, column_allowed, alias_to_table
            )
            state["filtered_sql"] = final_sql
        
    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"权限过滤注入过程中发生错误: {e}", exc_info=True)
        # 如果发生错误，使用原始SQL
        fallback_sql = state.get("generated_sql", "No SQL query generated")
        fallback_sql = _apply_column_permissions_to_sql(
            fallback_sql, db_type if "db_type" in locals() else "mysql", column_allowed if "column_allowed" in locals() else {}, alias_to_table if "alias_to_table" in locals() else {}
        )
        state["filtered_sql"] = fallback_sql
    
    return state

