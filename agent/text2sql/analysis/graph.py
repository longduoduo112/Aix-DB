import logging

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from agent.text2sql.analysis.data_render_antv import data_render_ant
from agent.text2sql.analysis.llm_summarizer import summarize
from agent.text2sql.database.db_service import DatabaseService
from agent.text2sql.database.neo4j_search import get_table_relationship
from agent.text2sql.sql.generator import sql_generate
from agent.text2sql.permission.filter_injector import permission_filter_injector
from agent.text2sql.chart.generator import chart_generator
from agent.text2sql.datasource.selector import datasource_selector
from agent.text2sql.question.recommender import question_recommender
from agent.text2sql.state.agent_state import AgentState

logger = logging.getLogger(__name__)


def data_render_condition(state: AgentState) -> str:
    """
    数据渲染条件判断
    统一使用 data_render 节点
    """
    return "data_render"


def should_continue_after_datasource_selector(state: AgentState) -> str:
    """
    数据源选择节点后的条件判断
    如果 datasource_id 仍然为空，说明选择失败，直接结束
    否则进入 schema_inspector
    """
    datasource_id = state.get("datasource_id")
    if not datasource_id:
        logger.warning("数据源选择失败，无法继续")
        return END  # 直接结束
    return "schema_inspector"


def create_graph(datasource_id: int = None):
    """
    :return:
    """
    graph = StateGraph(AgentState)
    db_service = DatabaseService(datasource_id)

    graph.add_node("datasource_selector", datasource_selector)
    graph.add_node("schema_inspector", db_service.get_table_schema)
    graph.add_node("table_relationship", get_table_relationship)
    graph.add_node("sql_generator", sql_generate)
    graph.add_node("permission_filter", permission_filter_injector)
    graph.add_node("sql_executor", db_service.execute_sql)
    graph.add_node("chart_generator", chart_generator)
    graph.add_node("data_render", data_render_ant)
    graph.add_node("summarize", summarize)
    graph.add_node("question_recommender", question_recommender)

    # 入口：根据是否有 datasource_id 决定是否进入数据源选择节点
    # 如果已有 datasource_id，则直接进入 schema_inspector
    # 否则先进入 datasource_selector
    graph.set_entry_point("datasource_selector")
    graph.add_conditional_edges(
        "datasource_selector",
        should_continue_after_datasource_selector,
        {END: END, "schema_inspector": "schema_inspector"},
    )
    
    graph.add_edge("schema_inspector", "table_relationship")
    graph.add_edge("table_relationship", "sql_generator")
    graph.add_edge("sql_generator", "permission_filter")
    graph.add_edge("permission_filter", "sql_executor")
    graph.add_edge("sql_executor", "chart_generator")
    graph.add_edge("chart_generator", "summarize")

    graph.add_conditional_edges(
        "summarize", data_render_condition, {"data_render": "data_render"}
    )

    graph.add_edge("data_render", "question_recommender")
    graph.add_edge("question_recommender", END)

    graph_compiled: CompiledStateGraph = graph.compile()
    return graph_compiled
