"""
原生驱动数据源的 SQL 工具
用于支持 starrocks、doris 等使用原生驱动的数据源
"""

import json
import logging
from typing import List, Optional

from langchain_core.tools import tool

from common.datasource_util import (
    DB,
    ConnectType,
    DatasourceConfigUtil,
    DatasourceConnectionUtil,
)
from model.db_connection_pool import get_db_pool
from model.datasource_models import DatasourceTable, DatasourceField

logger = logging.getLogger(__name__)

# 全局变量存储数据源信息（在创建 agent 时设置）
_native_datasource_id: Optional[int] = None
_native_datasource_type: Optional[str] = None
_native_datasource_config: Optional[str] = None

# 记录最近执行的查询，用于检测重复查询（每个数据源独立记录）
_recent_queries: dict = {}  # {datasource_id: [query1, query2, ...]}
_MAX_RECENT_QUERIES = 10  # 记录最近10条查询

# 记录工具调用次数，防止死循环（每个数据源独立记录）
_tool_call_counts: dict = {}  # {datasource_id: {"sql_db_query": count, "sql_db_schema": count, ...}}
_MAX_TOOL_CALLS_PER_TYPE = 20  # 每个工具类型最多调用20次


def set_native_datasource_info(datasource_id: int, datasource_type: str, datasource_config: str):
    """设置原生数据源信息"""
    global _native_datasource_id, _native_datasource_type, _native_datasource_config
    _native_datasource_id = datasource_id
    _native_datasource_type = datasource_type
    _native_datasource_config = datasource_config
    
    # 初始化该数据源的查询记录
    if datasource_id not in _recent_queries:
        _recent_queries[datasource_id] = []
    
    # 初始化该数据源的工具调用计数
    if datasource_id not in _tool_call_counts:
        _tool_call_counts[datasource_id] = {
            "sql_db_query": 0,
            "sql_db_schema": 0,
            "sql_db_list_tables": 0,
            "sql_db_query_checker": 0,
        }


def _get_table_info_from_metadata() -> dict:
    """从元数据表获取表结构信息"""
    if not _native_datasource_id:
        return {}
    
    db_pool = get_db_pool()
    table_info = {}
    
    try:
        with db_pool.get_session() as session:
            # 获取该数据源下所有已勾选的表
            tables = session.query(DatasourceTable).filter(
                DatasourceTable.ds_id == _native_datasource_id,
                DatasourceTable.checked == True
            ).all()
            
            # 获取所有表的字段
            table_ids = [t.id for t in tables]
            fields = session.query(DatasourceField).filter(
                DatasourceField.ds_id == _native_datasource_id,
                DatasourceField.table_id.in_(table_ids),
                DatasourceField.checked == True
            ).all()
            
            # 按表ID分组字段
            fields_by_table = {}
            for field in fields:
                if field.table_id not in fields_by_table:
                    fields_by_table[field.table_id] = []
                fields_by_table[field.table_id].append(field)
            
            # 构建表信息
            for table in tables:
                table_fields = fields_by_table.get(table.id, [])
                if not table_fields:
                    continue
                
                columns = {}
                for field in table_fields:
                    columns[field.field_name] = {
                        "type": field.field_type or "",
                        "comment": field.custom_comment or field.field_comment or "",
                    }
                
                table_info[table.table_name] = {
                    "columns": columns,
                    "foreign_keys": [],  # 原生驱动暂不支持外键信息
                    "table_comment": table.custom_comment or table.table_comment or "",
                }
    except Exception as e:
        logger.error(f"从元数据获取表结构失败: {e}", exc_info=True)
    
    return table_info


@tool
def sql_db_list_tables() -> str:
    """列出数据库中的所有表名。"""
    if not _native_datasource_id:
        return "错误: 未设置数据源信息"
    
    # 检查调用次数限制
    if _native_datasource_id in _tool_call_counts:
        count = _tool_call_counts[_native_datasource_id].get("sql_db_list_tables", 0)
        if count >= _MAX_TOOL_CALLS_PER_TYPE:
            logger.warning(f"sql_db_list_tables 调用次数已达上限 ({_MAX_TOOL_CALLS_PER_TYPE})，可能陷入循环")
            return (
                "⚠️ 警告: 表列表已多次查询。"
                "如果之前已返回表列表，请直接使用已获取的信息，无需重复查询。"
                "如需查看特定表的结构，请使用 sql_db_schema 工具。"
            )
        _tool_call_counts[_native_datasource_id]["sql_db_list_tables"] = count + 1
    
    table_info = _get_table_info_from_metadata()
    table_names = list(table_info.keys())
    
    if not table_names:
        return "数据库中没有表"
    
    return f"数据库中有以下表: {', '.join(table_names)}"


@tool
def sql_db_schema(table_names: str) -> str:
    """
    获取指定表的架构信息。
    
    Args:
        table_names: 表名，可以是单个表名或多个表名（用逗号分隔）
    """
    if not _native_datasource_id:
        return "错误: 未设置数据源信息"
    
    # 检查调用次数限制
    if _native_datasource_id in _tool_call_counts:
        count = _tool_call_counts[_native_datasource_id].get("sql_db_schema", 0)
        if count >= _MAX_TOOL_CALLS_PER_TYPE:
            logger.warning(f"sql_db_schema 调用次数已达上限 ({_MAX_TOOL_CALLS_PER_TYPE})，可能陷入循环")
            return (
                "⚠️ 警告: 表架构已多次查询。"
                "如果之前已返回表架构信息，请直接使用已获取的信息，无需重复查询。"
                "请基于已获取的架构信息编写 SQL 查询。"
            )
        _tool_call_counts[_native_datasource_id]["sql_db_schema"] = count + 1
    
    table_info = _get_table_info_from_metadata()
    
    # 解析表名（支持逗号分隔的多个表名）
    if isinstance(table_names, str):
        table_list = [t.strip() for t in table_names.split(",")]
    else:
        table_list = [table_names]
    
    schema_parts = []
    for table_name in table_list:
        if table_name not in table_info:
            schema_parts.append(f"表 '{table_name}' 不存在")
            continue
        
        info = table_info[table_name]
        columns = info.get("columns", {})
        table_comment = info.get("table_comment", "")
        
        schema_text = f"\n表 '{table_name}':"
        if table_comment:
            schema_text += f"\n注释: {table_comment}"
        
        schema_text += "\n列:"
        for col_name, col_info in columns.items():
            col_type = col_info.get("type", "")
            col_comment = col_info.get("comment", "")
            schema_text += f"\n  - {col_name} ({col_type})"
            if col_comment:
                schema_text += f" - {col_comment}"
        
        schema_parts.append(schema_text)
    
    return "\n".join(schema_parts) if schema_parts else "未找到表信息"


@tool
def sql_db_query(query: str) -> str:
    """
    执行 SQL SELECT 查询并返回结果。
    只允许执行 SELECT 查询，不允许执行 INSERT、UPDATE、DELETE、DROP 等操作。
    
    Args:
        query: 要执行的 SQL 查询语句
    """
    if not _native_datasource_id or not _native_datasource_type or not _native_datasource_config:
        return "错误: 未设置数据源信息"
    
    # 安全检查：只允许 SELECT 查询
    query_upper = query.strip().upper()
    forbidden_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE"]
    for keyword in forbidden_keywords:
        if keyword in query_upper:
            return f"错误: 不允许执行 {keyword} 操作，只允许 SELECT 查询"
    
    if not query_upper.startswith("SELECT"):
        return "错误: 只允许执行 SELECT 查询"
    
    # 规范化 SQL 查询（去除多余空白，用于比较）
    normalized_query = " ".join(query.split()).upper()
    
    # 检测重复查询
    if _native_datasource_id and _native_datasource_id in _recent_queries:
        recent_queries = _recent_queries[_native_datasource_id]
        normalized_recent = [" ".join(q.split()).upper() for q in recent_queries]
        
        if normalized_query in normalized_recent:
            # 找到重复查询，返回明确的提示
            logger.warning(f"检测到重复查询，已跳过执行:\n{query[:200]}...")
            return (
                "⚠️ **重复查询检测**: 此查询刚刚已执行过，无需重复执行。\n\n"
                "**查询已成功完成，结果已在上方显示。**\n\n"
                "**请停止重复执行相同查询。**\n"
                "如果需要对结果进行进一步分析，请：\n"
                "1. 直接基于已获取的结果进行分析\n"
                "2. 或提出新的查询需求\n"
                "3. 或说明您想要的具体分析目标"
            )
    
    # 检查调用次数限制
    if _native_datasource_id in _tool_call_counts:
        count = _tool_call_counts[_native_datasource_id].get("sql_db_query", 0)
        if count >= _MAX_TOOL_CALLS_PER_TYPE:
            logger.warning(f"sql_db_query 调用次数已达上限 ({_MAX_TOOL_CALLS_PER_TYPE})，可能陷入循环")
            return (
                "⚠️ **警告: SQL 查询调用次数已达上限。**\n\n"
                "可能的原因：\n"
                "1. 反复执行相同的查询\n"
                "2. 查询持续失败并重试\n"
                "3. Agent 陷入循环\n\n"
                "**建议：**\n"
                "1. 检查之前的查询结果，可能已经包含所需信息\n"
                "2. 如果查询失败，请仔细分析错误信息，不要盲目重试\n"
                "3. 考虑简化查询或分步骤执行\n"
                "4. 如果问题持续，请重新描述您的需求"
            )
        _tool_call_counts[_native_datasource_id]["sql_db_query"] = count + 1
    
    # 记录执行的 SQL（用于调试）- 记录完整 SQL
    logger.info(f"执行 SQL 查询（数据源类型: {_native_datasource_type}，调用次数: {_tool_call_counts.get(_native_datasource_id, {}).get('sql_db_query', 0)}）:\n{query}")
    
    try:
        # 解密配置
        config = DatasourceConfigUtil.decrypt_config(_native_datasource_config)
        
        # 执行查询
        result_data = DatasourceConnectionUtil.execute_query(
            _native_datasource_type, config, query
        )
        
        # 记录成功执行的查询
        if _native_datasource_id:
            if _native_datasource_id not in _recent_queries:
                _recent_queries[_native_datasource_id] = []
            _recent_queries[_native_datasource_id].append(query)
            # 只保留最近 N 条查询
            if len(_recent_queries[_native_datasource_id]) > _MAX_RECENT_QUERIES:
                _recent_queries[_native_datasource_id].pop(0)
        
        if not result_data:
            return "✅ 查询成功执行，但没有返回数据。"
        
        # 格式化结果（限制返回行数，避免输出过长）
        max_rows = 50
        result_rows = result_data[:max_rows]
        
        # 构建结果字符串
        if len(result_data) > max_rows:
            result_str = f"✅ 查询成功执行，返回 {len(result_data)} 行数据（仅显示前 {max_rows} 行）:\n\n"
        else:
            result_str = f"✅ 查询成功执行，返回 {len(result_data)} 行数据:\n\n"
        
        # 格式化表格式输出
        if result_rows:
            # 获取列名
            columns = list(result_rows[0].keys())
            
            # 计算每列的最大宽度
            col_widths = {}
            for col in columns:
                col_widths[col] = max(len(str(col)), max(len(str(row.get(col, ""))) for row in result_rows))
            
            # 构建表头
            header = " | ".join(str(col).ljust(col_widths[col]) for col in columns)
            separator = "-" * len(header)
            result_str += header + "\n" + separator + "\n"
            
            # 构建数据行
            for row in result_rows:
                row_str = " | ".join(str(row.get(col, "")).ljust(col_widths[col]) for col in columns)
                result_str += row_str + "\n"
        
        # 添加明确的完成提示
        result_str += "\n✅ 查询已完成。如需进一步分析，请说明您的需求。"
        
        return result_str
        
    except Exception as e:
        error_msg = str(e)
        
        # 针对 StarRocks/Doris 的特殊错误处理
        if _native_datasource_type in ("starrocks", "doris"):
            # 检查是否是列无法解析的错误
            if "cannot be resolved" in error_msg.lower():
                # 提取具体的列名信息
                import re
                column_match = re.search(r"Column\s+['`]([^'`]+)['`]", error_msg, re.IGNORECASE)
                column_name = column_match.group(1) if column_match else "未知列"
                
                # 分析 SQL，提取表别名信息
                table_aliases = set()
                alias_pattern = r"FROM\s+[`]?(\w+)[`]?\s+(\w+)|JOIN\s+[`]?(\w+)[`]?\s+(\w+)"
                matches = re.findall(alias_pattern, query, re.IGNORECASE)
                for match in matches:
                    if match[1]:  # FROM 子句的别名
                        table_aliases.add(match[1])
                    if match[3]:  # JOIN 子句的别名
                        table_aliases.add(match[3])
                
                # 检查列名中使用的表别名
                column_alias_match = re.search(r"['`](\w+)['`]\s*\.\s*['`](\w+)['`]", column_name)
                if column_alias_match:
                    used_alias = column_alias_match.group(1)
                    used_column = column_alias_match.group(2)
                    
                    if used_alias not in table_aliases:
                        concise_error = (
                            f"SQL 执行失败: 表别名 '{used_alias}' 未在 FROM/JOIN 子句中定义。\n"
                            f"当前 SQL 中定义的表别名: {', '.join(sorted(table_aliases)) if table_aliases else '无'}。\n"
                            f"**请检查 JOIN 语句是否正确。**\n"
                            f"如果之前已使用 sql_db_schema 查看过表结构，请直接使用已获取的信息，无需重复查询。"
                        )
                    else:
                        concise_error = (
                            f"SQL 执行失败: 列 '{used_column}' 在表 '{used_alias}' 中不存在。\n"
                            f"**请检查列名是否正确。**\n"
                            f"如果之前已使用 sql_db_schema 查看过表结构，请直接使用已获取的信息，无需重复查询。"
                        )
                else:
                    concise_error = (
                        f"SQL 执行失败: 列 '{column_name}' 无法解析。\n"
                        f"**请检查：**\n"
                        f"1) 表别名是否正确定义\n"
                        f"2) 列名是否存在\n"
                        f"3) JOIN 语句是否正确\n\n"
                        f"**如果之前已使用 sql_db_schema 查看过表结构，请直接使用已获取的信息，无需重复查询。**"
                    )
                
                logger.error(f"SQL 查询失败: {error_msg}\n执行的完整 SQL:\n{query}", exc_info=True)
                return concise_error
            
            # 检查是否是表不存在的错误
            elif "table" in error_msg.lower() and ("doesn't exist" in error_msg.lower() or "not exist" in error_msg.lower()):
                concise_error = (
                    f"SQL 执行失败: 表不存在。\n"
                    f"**请检查表名是否正确。**\n"
                    f"如果之前已使用 sql_db_list_tables 查看过表列表，请直接使用已获取的信息，无需重复查询。"
                )
                logger.error(f"SQL 查询失败: {error_msg}\n执行的完整 SQL:\n{query}", exc_info=True)
                return concise_error
        
        # 通用错误处理：返回简洁的错误信息
        # 限制错误信息长度，避免 Agent 陷入循环
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        
        concise_error = f"SQL 执行失败: {error_msg}"
        logger.error(f"SQL 查询失败: {error_msg}\n执行的完整 SQL:\n{query}", exc_info=True)
        return concise_error


@tool
def sql_db_query_checker(query: str) -> str:
    """
    检查 SQL 查询的语法是否正确。
    注意：这只是一个基本的检查，不会实际执行查询。
    
    Args:
        query: 要检查的 SQL 查询语句
    """
    query_upper = query.strip().upper()
    
    # 基本语法检查
    if not query_upper:
        return "错误: SQL 查询为空"
    
    # 检查是否包含禁止的操作
    forbidden_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE"]
    for keyword in forbidden_keywords:
        if keyword in query_upper:
            return f"错误: 不允许执行 {keyword} 操作，只允许 SELECT 查询"
    
    if not query_upper.startswith("SELECT"):
        return "错误: 只允许执行 SELECT 查询"
    
    # 基本结构检查
    if "FROM" not in query_upper:
        return "警告: SQL 查询缺少 FROM 子句"
    
    return "SQL 查询语法检查通过"
