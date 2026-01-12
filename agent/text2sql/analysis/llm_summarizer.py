import logging
from datetime import datetime
import json

from langchain_core.messages import SystemMessage, HumanMessage

from common.llm_util import get_llm
from agent.text2sql.state.agent_state import AgentState
from agent.text2sql.template.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)
"""
大模型数据总结节点
"""


def summarize(state: AgentState):
    """
    使用模板系统构建提示词并调用LLM进行数据总结
    
    Args:
        state: AgentState 包含 execution_result 和 user_query
        
    Returns:
        更新后的 state，包含 report_summary
    """
    llm = get_llm()
    prompt_builder = PromptBuilder()

    try:
        # 获取数据结果
        data_result = state["execution_result"].data
        
        # 如果数据是字典或列表，转换为JSON字符串
        if isinstance(data_result, (dict, list)):
            data_result_str = json.dumps(data_result, ensure_ascii=False, indent=2)
        else:
            data_result_str = str(data_result)
        
        # 获取当前时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 从模板中获取系统提示词和用户提示词
        summarizer_template = prompt_builder.base_template['template']['summarizer']
        system_prompt = summarizer_template['system']
        user_prompt = summarizer_template['user'].format(
            data_result=data_result_str,
            user_query=state["user_query"],
            current_time=current_time,
        )
        
        # 构建消息列表
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        # 调用 LLM
        response = llm.invoke(messages)
        state["report_summary"] = response.content

    except Exception as e:
        logger.error(f"Error in Summarizer: {e}", exc_info=True)
        state["report_summary"] = "数据总结生成失败，请稍后重试"

    return state
