"""
通过图数据库检索表之间的关系
"""

import logging
import os
import traceback

from py2neo import Graph

from agent.text2sql.state.agent_state import AgentState

# Neo4j 配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")

logger = logging.getLogger(__name__)


"""
# 查询任意表之间的关系数据
MATCH (t1:Table)-[r:REFERENCES]-(t2:Table)
WHERE t1.name IN ["t_customers","t_products", "t_sales_orders", "t_order_details"]
  AND t2.name IN ["t_customers","t_products", "t_sales_orders", "t_order_details"]
  AND t1.name < t2.name

RETURN 
  t1.name AS from_table,
  r.field_relation AS relationship,
  t2.name AS to_table

"""


def get_table_relationship(state: AgentState):
    """
    查询指定表之间所有的 REFERENCES 关系（双向），并去重。

    :return: 包含 from_table, relationship, to_table 的字典列表
    """
    try:
        # 连接图数据库
        graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        # Cypher 查询语句
        query = """
        MATCH (t1:Table)-[r:REFERENCES]-(t2:Table)
        WHERE t1.name IN $table_names
          AND t2.name IN $table_names
          AND t1.name < t2.name
        RETURN 
          t1.name AS from_table,
          r.field_relation AS relationship,
          t2.name AS to_table
        """

        table_schema_info = state["db_info"]
        if table_schema_info:
            table_names = list(table_schema_info.keys())
        else:
            table_names = []

        # 如果没有表名，直接返回空结果
        if not table_names:
            result = []
        else:
            # 执行查询
            result = graph.run(query, table_names=table_names).data()

        state["table_relationship"] = result

    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"获取表关系时发生错误: {e}")
        state["table_relationship"] = []

    return state
