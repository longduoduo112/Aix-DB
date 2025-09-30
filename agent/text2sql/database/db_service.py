import json
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="jieba")

import logging
import re
from typing import Dict, List, Any, Optional
import jieba
import pandas as pd
from sqlalchemy.inspection import inspect
from sqlalchemy.sql.expression import text
from rank_bm25 import BM25Okapi
from agent.text2sql.state.agent_state import AgentState, ExecutionResult
from model.db_connection_pool import get_db_pool
from functools import lru_cache

# 获取数据库连接池（全局）
db_pool = get_db_pool()
logger = logging.getLogger(__name__)


class DatabaseService:
    """
    数据库服务类：负责获取表结构、基于用户查询筛选相关表、执行SQL等。
    """

    def __init__(self):
        self._engine = db_pool.get_engine()

    @staticmethod
    def _tokenize_text(text_str: str) -> List[str]:
        """
        :param text_str
        https://github.com/fxsjy/jieba
        对文本进行中文/英文分词，过滤标点符号。
        """
        filtered_text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", " ", text_str)
        tokens = jieba.lcut(filtered_text, cut_all=False)
        # print(tokens)
        return [token.strip() for token in tokens if token.strip()]

    def _get_table_comment(self, table_name: str) -> str:
        """
        从 information_schema 获取 MySQL 表注释。
        """
        try:
            query = text(
                """
                SELECT table_comment 
                FROM information_schema.tables 
                WHERE table_schema = DATABASE() 
                  AND table_name = :table_name;
            """
            )
            with self._engine.connect() as conn:
                result = conn.execute(query, {"table_name": table_name})
                row = result.fetchone()
                return row[0].strip() if row else ""
        except Exception as e:
            logger.warning(f"无法获取表 {table_name} 的注释: {e}")
            return ""

    @staticmethod
    def _build_document(table_name: str, table_info: dict) -> str:
        """
        构建用于 BM25 匹配的文档文本。
        """
        parts = [table_name]

        # 添加表注释
        table_comment = table_info.get("table_comment", "")
        if table_comment:
            parts.append(table_comment)

        # 添加列信息：列名 + 中文名 + 注释
        for col_name, col_info in table_info.get("columns", {}).items():
            parts.append(col_name)
            # parts.append(col_info.get("cn_name", ""))
            parts.append(col_info.get("comment", ""))

        return " ".join(parts)

    @lru_cache(maxsize=1)  # 缓存整个 schema，仅当数据库不变时有效
    def _fetch_all_table_info(self) -> Dict[str, Dict]:
        """
        从数据库获取所有表的结构信息（带缓存）。
        """
        inspector = inspect(self._engine)
        table_info = {}

        for table_name in inspector.get_table_names():
            try:
                # 获取列信息
                columns = {}
                for col in inspector.get_columns(table_name):
                    comment = str(col["comment"] or "")
                    columns[col["name"]] = {
                        "type": str(col["type"]),
                        "comment": comment,
                        # "cn_name": comment,
                    }

                # 获取外键
                foreign_keys = [
                    f"{fk['constrained_columns'][0]} -> {fk['referred_table']}.{fk['referred_columns'][0]}"
                    for fk in inspector.get_foreign_keys(table_name)
                ]

                # 获取表注释
                table_comment = self._get_table_comment(table_name)

                table_info[table_name] = {
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "table_comment": table_comment,
                }
            except Exception as e:
                logger.warning(f"读取表 {table_name} 结构失败: {e}")

        logger.info(f"成功加载 {len(table_info)} 张表的 schema 信息")
        return table_info

    def _filter_relevant_tables_by_bm25(self, table_info: Dict[str, Dict], user_query: str) -> Dict[str, Dict]:
        """
        使用 BM25 算法筛选与用户查询最相关的表。
        """
        if not user_query or not table_info:
            return table_info

        # 构建语料
        corpus = []
        table_names = []
        table_comments = []

        for table_name, info in table_info.items():
            doc = self._build_document(table_name, info)
            corpus.append(doc)
            table_names.append(table_name)
            table_comments.append(info.get("table_comment", ""))

        # 分词
        tokenized_corpus = [self._tokenize_text(doc) for doc in corpus]
        query_tokens = self._tokenize_text(user_query)
        query_token_set = set(query_tokens)

        # 训练 BM25 模型
        bm25 = BM25Okapi(tokenized_corpus)
        doc_scores = bm25.get_scores(query_tokens)

        # 动态增强：如果表注释与查询有关键词重叠，则提权
        enhanced_scores = doc_scores.copy()
        for i, (comment, score) in enumerate(zip(table_comments, doc_scores)):
            if score <= 0:
                continue
            comment_tokens = self._tokenize_text(comment)
            comment_token_set = set(comment_tokens)
            overlap = query_token_set & comment_token_set
            if overlap:
                # 根据重叠比例提权
                overlap_ratio = len(overlap) / len(query_token_set)
                enhanced_scores[i] += score * overlap_ratio * 1.5  # 提升权重

        # 使用增强后得分排序
        scored_tables = sorted(
            [(idx, score) for idx, score in enumerate(enhanced_scores)],
            key=lambda x: x[1],
            reverse=True,
        )

        # 输出查询和得分日志
        print(f"\n🔍 查询: {user_query}")
        for idx, score in scored_tables[:5]:
            table_name = table_names[idx]
            print(f" ✅ {table_name:12} | 得分: {score:.4f}")

        # 动态阈值：保留得分 > 最高分 10% 的表，最多返回 5 个
        if not scored_tables:
            return {}

        max_score = scored_tables[0][1]
        threshold = max(max_score * 0.1, 0.5)  # 至少 0.5 或 10%
        top_indices = [i for i, s in scored_tables if s >= threshold][:5]

        filtered_table_info = {table_names[idx]: table_info[table_names[idx]] for idx in top_indices}

        logger.info(f"BM25 筛选出 {len(filtered_table_info)} 个相关表: {list(filtered_table_info.keys())}")
        return filtered_table_info

    def get_table_schema(self, state: AgentState) -> AgentState:
        """
        获取数据库表结构，并根据用户查询筛选相关表。
        """
        try:
            logger.info("开始获取数据库表 schema 信息")

            # 获取全部表结构（带缓存）
            all_table_info = self._fetch_all_table_info()

            user_query = state.get("user_query", "").strip()

            # 根据查询筛选相关表
            if user_query:
                filtered_info = self._filter_relevant_tables_by_bm25(all_table_info, user_query)
                state["db_info"] = filtered_info
            else:
                state["db_info"] = all_table_info

            logger.info(f"获取数据库表信息成功，共 {len(state['db_info'])} 张表")
        except Exception as e:
            logger.error(f"获取数据库表信息失败: {e}", exc_info=True)
            state["db_info"] = {}
            state["execution_result"] = ExecutionResult(success=False, error="无法连接数据库或获取元数据")

        return state

    @staticmethod
    def execute_sql(state: AgentState) -> AgentState:
        """
        执行生成的 SQL 语句。
        """
        generated_sql = state.get("generated_sql", "").strip()
        if not generated_sql:
            state["execution_result"] = ExecutionResult(success=False, error="SQL 为空")
            return state

        logger.info("执行 SQL 语句")
        try:
            with db_pool.get_session() as connection:
                # 防止大结果集，自动添加 LIMIT
                result = connection.execute(text(generated_sql))
                result_data = result.fetchall()
                columns = result.keys()
                frame = pd.DataFrame(result_data, columns=columns)

                state["execution_result"] = ExecutionResult(
                    success=True,
                    data=frame.to_dict(orient="records"),
                )
        except Exception as e:
            logger.error(f"执行 SQL 失败: {e}", exc_info=True)
            state["execution_result"] = ExecutionResult(success=False, error=str(e))

        return state

    @staticmethod
    def execute_correction_sql(state: AgentState) -> AgentState:
        """
        执行修正后的 SQL 语句。
        """
        correction_result = state.get("correction_result")
        if not correction_result or not hasattr(correction_result, "corrected_sql_query"):
            state["execution_result"] = ExecutionResult(success=False, error="无修正后的 SQL 可执行")
            return state

        corrected_sql = correction_result.corrected_sql_query.strip()
        if not corrected_sql:
            state["execution_result"] = ExecutionResult(success=False, error="修正后的 SQL 为空")
            return state

        logger.info("执行修正后的 SQL 语句")
        try:
            with db_pool.get_session() as connection:
                result = connection.execute(text(corrected_sql))
                result_data = result.fetchall()
                columns = result.keys()
                frame = pd.DataFrame(result_data, columns=columns)

                state["execution_result"] = ExecutionResult(
                    success=True,
                    data=frame.to_dict(orient="records"),
                )
        except Exception as e:
            logger.error(f"执行修正 SQL 失败: {e}", exc_info=True)
            state["execution_result"] = ExecutionResult(success=False, error=str(e))

        return state
