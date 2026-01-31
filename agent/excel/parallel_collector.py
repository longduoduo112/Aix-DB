"""
表格问答并行执行收集器
并行执行 chart_generator 和 summarize
最后统一收集结果，按顺序返回
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Dict, Optional

from agent.excel.excel_agent_state import ExcelAgentState
from agent.excel.excel_chart_generator import excel_chart_generator
from agent.excel.excel_summarizer import summarize

logger = logging.getLogger(__name__)

# 全局线程池，用于并行执行任务
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    """获取或创建线程池"""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="excel_parallel_collector"
                )
                logger.info("✅ 创建表格问答并行执行线程池")
    return _executor


def parallel_collect(
    state: ExcelAgentState, tasks: list[str] = None
) -> ExcelAgentState:
    """
    并行执行多个任务并收集结果

    Args:
        state: ExcelAgent 状态对象
        tasks: 要执行的任务列表，默认为 ['chart_generator', 'summarize']

    Returns:
        更新后的 state，包含所有任务的结果
    """
    if tasks is None:
        tasks = ["chart_generator", "summarize"]

    logger.info(f"🔄 开始并行执行任务: {tasks}")

    # 创建状态的深拷贝，确保并行任务不会互相影响
    state_copies = {}
    for task in tasks:
        state_copies[task] = deepcopy(state)

    # 定义任务函数映射
    task_functions = {
        "chart_generator": excel_chart_generator,
        "summarize": summarize,
    }

    # 提交所有任务到线程池
    executor = get_executor()
    futures = {}

    for task in tasks:
        if task in task_functions:
            task_func = task_functions[task]
            future = executor.submit(task_func, state_copies[task])
            futures[task] = future
            logger.info(f"📤 提交任务: {task}")

    # 等待所有任务完成并收集结果
    results = {}
    errors = {}

    for task, future in futures.items():
        try:
            result_state = future.result(timeout=180)  # 最多等待180秒
            results[task] = result_state
            logger.info(f"✅ 任务完成: {task}")
        except Exception as e:
            logger.error(f"❌ 任务失败: {task}, 错误: {e}", exc_info=True)
            errors[task] = str(e)
            results[task] = None

    # 按顺序合并结果到原始 state
    # 顺序：summarize → chart_config
    merge_order = ["summarize", "chart_generator"]

    for task in merge_order:
        if task in results and results[task] is not None:
            result_state = results[task]

            if task == "summarize":
                if "report_summary" in result_state and result_state.get(
                    "report_summary"
                ):
                    state["report_summary"] = result_state["report_summary"]
                    logger.info(f"✅ 合并 summarize 结果")

            elif task == "chart_generator":
                if "chart_config" in result_state and result_state.get("chart_config"):
                    state["chart_config"] = result_state["chart_config"]
                    if "chart_type" in result_state:
                        state["chart_type"] = result_state["chart_type"]
                    logger.info(f"✅ 合并 chart_generator 结果")

    # 记录错误（如果有）
    if errors:
        logger.warning(f"⚠️ 部分任务执行失败: {errors}")

    logger.info("✅ 并行执行完成，所有结果已合并")
    return state


def parallel_collect_after_sql_executor(state: ExcelAgentState) -> ExcelAgentState:
    """
    在 sql_executor 之后并行执行 chart_generator 和 summarize

    Args:
        state: ExcelAgent 状态对象（包含 sql_executor 的结果）

    Returns:
        更新后的 state
    """
    logger.info("🔄 并行执行 chart_generator 和 summarize")
    return parallel_collect(state, tasks=["chart_generator", "summarize"])
