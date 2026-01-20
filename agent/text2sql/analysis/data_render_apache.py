import json
import logging
import traceback
from decimal import Decimal

from agent.text2sql.state.agent_state import AgentState, ExecutionResult
import sqlglot
from sqlglot import parse
from datetime import datetime, date
import pandas as pd

from services.db_qadata_process import process

"""
AntV MCP默认没有提供表格组件 这里使用
Apache EChart数据渲染节点来支撑表格的渲染
前期使用硬编码方式后面使用MCP方式
"""

logger = logging.getLogger(__name__)

# 数据库类型到 sqlglot 方言的映射（与 data_render_antv.py 保持一致）
DB_TYPE_TO_DIALECT = {
    "mysql": "mysql",
    "postgresql": "postgres",
    "pg": "postgres",
    "oracle": "oracle",
    "sqlserver": "tsql",
    "mssql": "tsql",
    "clickhouse": "clickhouse",
    "ck": "clickhouse",
    "redshift": "redshift",
    "elasticsearch": "mysql",
    "es": "mysql",
    "starrocks": "mysql",
    "doris": "mysql",
    "dm": "oracle",
    "kingbase": "postgres",
    "excel": "postgres",
}


def data_render_apache(state: AgentState) -> dict:
    """
    渲染Apache ECharts数据（支持表格数据结构）

    :param state: Agent状态对象
    :return: 包含图表数据的字典
    """
    table_schema_info = state.get("db_info", {})
    generated_sql = state.get("generated_sql", "")
    data_result: ExecutionResult = state.get("execution_result")

    # 构建基础表格数据结构
    table_data = {"llm": {"type": "response_table"}, "data": {"column": [], "result": []}}

    # 获取数据源类型（从state中获取，如果没有则默认为mysql）
    db_type = state.get("db_type", "mysql")
    if not db_type:
        # 尝试从datasource_id获取
        datasource_id = state.get("datasource_id")
        if datasource_id:
            try:
                from model.db_connection_pool import get_db_pool
                from services.datasource_service import DatasourceService
                db_pool = get_db_pool()
                with db_pool.get_session() as session:
                    ds = DatasourceService.get_datasource_by_id(session, datasource_id)
                    if ds:
                        db_type = ds.type or "mysql"
            except Exception:
                pass
        db_type = db_type or "mysql"
    
    # 获取生成的SQL中的表名
    generated_table_names = extract_table_names_sqlglot(generated_sql, db_type)
    if not generated_table_names:
        logger.info("未从SQL中提取到表名")
        return table_data

    target_table = generated_table_names[0]  # 默认使用第一个表获取 schema

    # 获取列中文名（字段注释）
    column_comments = get_column_comments(table_schema_info, target_table)
    table_data["data"]["column"] = column_comments

    # 获取原始列名（英文字段名），用于映射数据
    try:
        columns = table_schema_info.get(target_table, {}).get("columns", {})
        if not columns:
            columns = table_schema_info["columns"]
        english_columns = list(columns.keys())  # 保持与 comment 相同的顺序
    except Exception as e:
        logger.info(f"获取表 {target_table} 的列名失败: {e}")
        english_columns = []

    # 填充 result 数据
    if data_result and data_result.data:
        for row in data_result.data:
            # 确保 row 是 dict 类型
            if isinstance(row, dict):
                # 按 english_columns 顺序取出值，对应 column_comments 的顺序
                row_values = [convert_value(row.get(col, None)) for col in english_columns]
                # 修改此处：将 row_values 和 column_comments 组合成对象
                table_data["data"]["result"].append(dict(zip(column_comments, row_values)))
            else:
                # 兼容非 dict 格式（如元组或列表）
                logger.info(f"数据行格式异常，跳过: {row}")

    processed_data = process(json.dumps(table_data, ensure_ascii=False))
    state["apache_chart_data"] = processed_data

    return state


def convert_value(v):
    if isinstance(v, Decimal):
        return float(v)  # 或者 str(v)
    elif isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    else:
        return v


def extract_table_names_sqlglot(sql: str, db_type: str = "mysql") -> list:
    """
    使用 sqlglot 提取 SQL 中的所有表名（支持复杂语法、多表、子查询、CTE 等）

    :param sql: SQL 语句
    :param db_type: 数据库类型，用于选择正确的方言解析
    :return: 表名列表（去重）
    """
    try:
        # 将数据库类型映射到 sqlglot 方言
        dialect = DB_TYPE_TO_DIALECT.get(db_type.lower() if db_type else "mysql", "mysql")
        expression = parse(sql, read=dialect)[0]
        tables = set()
        for table in expression.find_all(sqlglot.exp.Table):
            # 取表名（去掉 schema）
            tables.add(table.name)
        return list(tables)
    except Exception as e:
        logger.info(f"SQL 解析错误: {e}")
        return []


def get_column_comments(schema_inspector: dict, table_name: str) -> list:
    """
    从 schema_inspector 中提取指定表的所有字段的 comment，放入 list 中。

    :param schema_inspector: 包含数据库 schema 信息的字典
    :param table_name: 要提取 comment 的表名
    :return: 包含所有字段 comment 的 list
    """
    try:

        table_info = schema_inspector.get(table_name, {})
        if not table_info:
            table_info = schema_inspector

        if not table_info:
            logger.info(f"未找到表 {table_name} 的信息")
            return []

        columns = table_info.get("columns", {})
        if not columns:
            logger.info(f"表 {table_name} 没有列信息")
            return []

        comments = []
        for col_name, col_info in columns.items():
            # 确保col_info是字典类型
            if isinstance(col_info, dict):
                comment = col_info.get("comment")
                # 如果 comment 为 'None' 字符串或 None，用空字符串代替
                if comment and comment != "None":
                    comments.append(comment)
                else:
                    comments.append("")  # 使用空字符串作为默认值
            else:
                comments.append("")  # 如果列信息格式不正确，使用空字符串
        return comments
    except Exception as e:
        traceback.print_exception(e)
        logger.info(f"处理表 {table_name} 的列注释时出错: {e}")
        return []
