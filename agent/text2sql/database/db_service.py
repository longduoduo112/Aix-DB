import warnings

from sqlalchemy import create_engine

from common.datasource_util import DatasourceConfigUtil, DatasourceConnectionUtil, DB, ConnectType
from model import Datasource

warnings.filterwarnings("ignore", message=".*pkg_resources.*deprecated.*")

import json
import logging
import os
import re
import time
from typing import Dict, List, Tuple, Optional
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

import faiss
import jieba
import numpy as np
import pandas as pd
import requests

# Langfuse OpenAI 延迟导入，避免在模块加载时触发 Langfuse 客户端初始化
# from langfuse.openai import OpenAI
from rank_bm25 import BM25Okapi
from sqlalchemy.inspection import inspect
from sqlalchemy.sql.expression import text

from agent.text2sql.state.agent_state import AgentState, ExecutionResult
from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel, TDsPermission, TDsRules
from model.datasource_models import DatasourceTable, DatasourceField
from agent.text2sql.permission.permission_retriever import get_user_permission_filters
from sqlalchemy import select

# 日志配置
logger = logging.getLogger(__name__)

# 数据库连接池
db_pool = get_db_pool()


# 返回表数量配置（可配置，默认 6 个）
TABLE_RETURN_COUNT = int(os.getenv("TABLE_RETURN_COUNT", "6"))

# 缓存配置
_table_info_cache: Dict[Tuple[int, Optional[int]], Tuple[Dict[str, Dict], float]] = {}
_cache_lock = Lock()
CACHE_TTL = int(os.getenv("TABLE_INFO_CACHE_TTL", "300"))  # 缓存有效期（秒），默认5分钟


# 嵌入模型配置
def get_embedding_model_config():
    """
    获取嵌入模型配置
    只查找 Embedding 类型的模型（model_type=2），不回退到 LLM
    如果没有配置，返回 None（将使用离线模型）
    """
    with db_pool.get_session() as session:
        # model_type: 2 -> Embedding
        model = session.query(TAiModel).filter(TAiModel.model_type == 2, TAiModel.default_model == True).first()

        if not model:
            # 尝试查找任何 embedding 模型
            model = session.query(TAiModel).filter(TAiModel.model_type == 2).first()

        if not model:
            # 没有找到在线模型，返回 None（将使用离线模型）
            return None

        # 处理 base_url，确保包含协议前缀
        base_url = (model.api_domain or "").strip()
        if not base_url:
            logger.warning("表结构检索使用的 embedding 模型 API Domain 为空，将使用离线模型")
            return None

        if not base_url.startswith(("http://", "https://")):
            # 本地地址默认 http，其它默认 https
            if base_url.startswith(("localhost", "127.0.0.1", "0.0.0.0")):
                base_url = f"http://{base_url}"
            else:
                base_url = f"https://{base_url}"

        return {"name": model.base_model, "api_key": model.api_key, "base_url": base_url}


# 重排模型配置
def get_rerank_model_config():
    with db_pool.get_session() as session:
        # model_type: 3 -> Rerank
        model = session.query(TAiModel).filter(TAiModel.model_type == 3, TAiModel.default_model == True).first()

        if not model:
            # Fallback
            model = session.query(TAiModel).filter(TAiModel.model_type == 3).first()

        if not model:
            return None

        return {"name": model.base_model, "api_key": model.api_key, "base_url": model.api_domain}


# 全局变量占位，实际使用时动态获取或在 init 中初始化
# 但为了保持兼容性，这里我们使用 lazy initialization 或者 property


class DatabaseService:
    """
    支持混合检索（BM25 + 向量）与索引持久化的数据库服务。
    提供表结构检索、SQL 执行、错误修正 SQL 执行等功能。
    """

    def __init__(self, datasource_id: int = None):
        self._engine = None
        self._datasource_id = datasource_id
        # 存储数据源的关键属性（避免 SQLAlchemy DetachedInstanceError）
        self._datasource_type = None
        self._datasource_config = None

        if datasource_id:
            try:
                with db_pool.get_session() as session:
                    ds = session.query(Datasource).filter(Datasource.id == datasource_id).first()
                    if ds:
                        # 在 session 内提取并存储需要的属性
                        self._datasource_type = ds.type
                        self._datasource_config = ds.configuration
                        # 检查数据源是否支持 SQLAlchemy 连接
                        db_enum = DB.get_db(ds.type, default_if_none=True)
                        if db_enum.connect_type == ConnectType.sqlalchemy:
                            config = DatasourceConfigUtil.decrypt_config(ds.configuration)
                            uri = DatasourceConnectionUtil.build_connection_uri(ds.type, config)
                            # SQL Server 2022 需要禁用加密以兼容 pymssql
                            if ds.type == "sqlServer":
                                self._engine = create_engine(uri, connect_args={"encryption": "off"})
                            else:
                                self._engine = create_engine(uri)
                            logger.info(f"Initialized DatabaseService with datasource_id: {datasource_id}")
                        else:
                            # 对于使用原生驱动的数据库（如 Doris），不创建 SQLAlchemy engine
                            logger.info(f"Datasource {datasource_id} ({ds.type}) uses native driver, skipping SQLAlchemy engine")
            except Exception as e:
                logger.error(f"Failed to initialize datasource {datasource_id}: {e}")

        if not self._engine:
            self._engine = db_pool.get_engine()

        self._faiss_index: Optional[faiss.Index] = None
        self._table_names: List[str] = []
        self._corpus: List[str] = []
        self._tokenized_corpus: List[List[str]] = []
        self._index_initialized: bool = False
        self.USE_RERANKER: bool = True  # 是否启用重排序器

        # Initialize clients lazily or now
        emb_config = get_embedding_model_config()
        if emb_config:
            # 使用在线 embedding 模型
            try:
                # 延迟导入，避免在模块加载时触发 Langfuse 客户端初始化
                from langfuse.openai import OpenAI
                self.embedding_model_name = emb_config["name"]
                self.embedding_client = OpenAI(api_key=emb_config["api_key"] or "empty", base_url=emb_config["base_url"])
                self.use_local_embedding = False
                logger.info(f"✅ 使用在线 embedding 模型: {self.embedding_model_name}")
            except Exception as e:
                logger.error(f"初始化在线嵌入模型失败: {e}，将使用离线模型")
                self.embedding_client = None
                self.use_local_embedding = True
        else:
            # 没有配置在线模型，使用离线模型
            logger.info("未配置在线 embedding 模型，将使用离线 CPU 模型")
            self.embedding_client = None
            self.embedding_model_name = None
            self.use_local_embedding = True

        try:
            rerank_config = get_rerank_model_config()
            if rerank_config:
                self.rerank_model_name = rerank_config["name"]
                self.rerank_api_key = rerank_config["api_key"]
                self.rerank_base_url = rerank_config["base_url"]
                self.USE_RERANKER = True
            else:
                self.USE_RERANKER = False
                logger.warning("未配置重排模型，重排功能将被禁用")
        except Exception as e:
            logger.error(f"初始化重排模型失败: {e}")
            self.USE_RERANKER = False

    @staticmethod
    def _tokenize_text(text_str: str) -> List[str]:
        """
        对中文/英文文本进行分词，过滤标点符号。
        """
        filtered_text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", " ", text_str)
        tokens = jieba.lcut(filtered_text, cut_all=False)
        return [token.strip() for token in tokens if token.strip()]

    def _get_table_comment(self, table_name: str) -> str:
        """
        获取指定表的注释，兼容当前支持的多种数据源类型。
        优先使用 SQLAlchemy Inspector 的统一接口，不同数据库再做兜底处理。
        """
        try:
            # 0. 对于原生驱动的数据库，直接从元数据表获取注释
            if self._datasource_type and self._datasource_id:
                db_enum = DB.get_db(self._datasource_type, default_if_none=True)
                if db_enum.connect_type == ConnectType.py_driver:
                    return self._get_table_comment_from_metadata(table_name)

            # 1. 优先使用 SQLAlchemy 的 inspector 接口（支持多数主流数据库）
            try:
                inspector = inspect(self._engine)
                info = inspector.get_table_comment(table_name)
                if isinstance(info, dict):
                    comment = info.get("text") or info.get("comment") or ""
                else:
                    comment = info or ""
                if comment:
                    return str(comment).strip()
            except Exception as e:
                logger.debug(f"Inspector 获取表 {table_name} 注释失败，尝试方言级兜底: {e}")

            # 2. 根据方言名称做兜底处理，避免使用单一 MySQL 语法在其它数据库上报错
            dialect_name = getattr(getattr(self._engine, "dialect", None), "name", "") or ""
            dialect_name = dialect_name.lower()

            with self._engine.connect() as conn:
                # MySQL / MariaDB
                if dialect_name in ("mysql", "mariadb"):
                    query = text(
                        """
                        SELECT table_comment
                        FROM information_schema.tables
                        WHERE table_schema = DATABASE()
                          AND table_name = :table_name
                        """
                    )
                    row = conn.execute(query, {"table_name": table_name}).fetchone()
                    return (row[0] or "").strip() if row and row[0] else ""

                # PostgreSQL / Kingbase / Redshift 等 PG 协议
                if dialect_name in ("postgresql", "postgres"):
                    query = text(
                        """
                        SELECT obj_description(c.oid) AS table_comment
                        FROM pg_class c
                        WHERE c.relname = :table_name
                          AND c.relkind IN ('r','v','m','f','p')
                        """
                    )
                    row = conn.execute(query, {"table_name": table_name}).fetchone()
                    return (row[0] or "").strip() if row and row[0] else ""

                # SQL Server
                if dialect_name in ("mssql", "sqlserver"):
                    query = text(
                        """
                        SELECT CAST(ep.value AS NVARCHAR(4000)) AS table_comment
                        FROM sys.tables t
                        LEFT JOIN sys.extended_properties ep
                          ON ep.major_id = t.object_id
                         AND ep.minor_id = 0
                         AND ep.name = 'MS_Description'
                        WHERE t.name = :table_name
                        """
                    )
                    row = conn.execute(query, {"table_name": table_name}).fetchone()
                    return (row[0] or "").strip() if row and row[0] else ""

                # Oracle
                if "oracle" in dialect_name:
                    query = text(
                        """
                        SELECT comments
                        FROM user_tab_comments
                        WHERE table_name = :table_name
                        """
                    )
                    row = conn.execute(query, {"table_name": table_name.upper()}).fetchone()
                    return (row[0] or "").strip() if row and row[0] else ""

                # ClickHouse
                if "clickhouse" in dialect_name:
                    query = text(
                        """
                        SELECT comment
                        FROM system.tables
                        WHERE database = currentDatabase()
                          AND name = :table_name
                        """
                    )
                    row = conn.execute(query, {"table_name": table_name}).fetchone()
                    return (row[0] or "").strip() if row and row[0] else ""

        except Exception as e:
            logger.warning(f"⚠️ 获取表 {table_name} 注释失败: {e}")

        # 兜底：没有注释或不支持，返回空字符串即可（不影响后续流程）
        return ""

    def _get_table_comment_from_metadata(self, table_name: str) -> str:
        """
        从 t_datasource_table 元数据表获取表注释。
        用于原生驱动的数据库（如 Doris、StarRocks 等），这些数据库无法通过 SQLAlchemy inspector 获取注释。

        Args:
            table_name: 表名

        Returns:
            表注释字符串，如果未找到则返回空字符串
        """
        if not self._datasource_id:
            return ""

        try:
            with db_pool.get_session() as session:
                table = session.query(DatasourceTable).filter(
                    DatasourceTable.ds_id == self._datasource_id,
                    DatasourceTable.table_name == table_name
                ).first()

                if table:
                    # 优先使用自定义注释，其次使用原始注释
                    return table.custom_comment or table.table_comment or ""
                return ""
        except Exception as e:
            logger.warning(f"⚠️ 从元数据获取表 {table_name} 注释失败: {e}")
            return ""

    @staticmethod
    def _build_document(table_name: str, table_info: dict) -> str:
        """
        构建用于检索的文档文本（表名 + 注释 + 字段名 + 字段注释）。
        """
        parts = [table_name]
        if table_info.get("table_comment"):
            parts.append(table_info["table_comment"])
        for col_name, col_info in table_info.get("columns", {}).items():
            parts.append(col_name)
            if col_info.get("comment"):
                parts.append(col_info["comment"])
        return " ".join(parts)

    def _fetch_all_table_info(self, user_id: Optional[int] = None, use_cache: bool = True) -> Dict[str, Dict]:
        """
        获取数据库中所有表的结构信息（带权限过滤和缓存）。

        Args:
            user_id: 用户ID，用于权限过滤（管理员不应用权限过滤）
            use_cache: 是否使用缓存

        Returns:
            表信息字典
        """
        from common.permission_util import is_admin

        # 检查缓存
        cache_key = (self._datasource_id or 0, user_id)
        if use_cache:
            with _cache_lock:
                if cache_key in _table_info_cache:
                    cached_data, cached_time = _table_info_cache[cache_key]
                    if time.time() - cached_time < CACHE_TTL:
                        logger.debug(f"✅ 使用缓存的表结构信息 (datasource_id={self._datasource_id}, user_id={user_id})")
                        return cached_data

        start_time = time.time()

        # 检查数据源是否使用原生驱动（非 SQLAlchemy）
        use_native_driver = False
        if self._datasource_type and self._datasource_id:
            db_enum = DB.get_db(self._datasource_type, default_if_none=True)
            use_native_driver = db_enum.connect_type == ConnectType.py_driver

        if use_native_driver and self._datasource_id:
            # 对于原生驱动的数据库（如 Doris、StarRocks 等），从 t_datasource_table 获取表结构
            return self._fetch_table_info_from_metadata(user_id, use_cache, start_time)

        inspector = inspect(self._engine)
        table_names = inspector.get_table_names()
        logger.info(f"🔍 开始加载 {len(table_names)} 张表的 schema 信息...")

        # 获取列权限配置（集成完整的权限系统）
        column_permissions = {}
        if user_id and not is_admin(user_id) and self._datasource_id:
            try:
                with db_pool.get_session() as session:
                    # 获取该数据源下所有表
                    tables = session.query(DatasourceTable).filter(
                        DatasourceTable.ds_id == self._datasource_id,
                        DatasourceTable.table_name.in_(table_names)
                    ).all()

                    # 获取所有规则
                    rules_stmt = select(TDsRules).where(TDsRules.enable == True)
                    rules = session.execute(rules_stmt).scalars().all()

                    for table in tables:
                        allowed_fields = set()

                        # 如果有规则，查询列权限配置
                        if rules:
                            permissions_stmt = select(TDsPermission).where(
                                TDsPermission.table_id == table.id,
                                TDsPermission.type == 'column',
                                TDsPermission.enable == True
                            )
                            column_perms = session.execute(permissions_stmt).scalars().all()

                            if column_perms:
                                # 检查权限是否与用户匹配
                                matching_permissions = []
                                for permission in column_perms:
                                    for rule in rules:
                                        perm_ids = []
                                        if rule.permission_list:
                                            try:
                                                perm_ids = json.loads(rule.permission_list)
                                            except:
                                                pass

                                        user_ids = []
                                        if rule.user_list:
                                            try:
                                                user_ids = json.loads(rule.user_list)
                                            except:
                                                pass

                                        if perm_ids and user_ids:
                                            if permission.id in perm_ids and (
                                                user_id in user_ids or str(user_id) in user_ids
                                            ):
                                                matching_permissions.append(permission)
                                                break

                                # 解析列权限配置
                                for perm in matching_permissions:
                                    if perm.permissions:
                                        try:
                                            perm_config = json.loads(perm.permissions)
                                            if isinstance(perm_config, list):
                                                for field_perm in perm_config:
                                                    if field_perm.get("enable", False):
                                                        field_name = field_perm.get("field_name")
                                                        if field_name:
                                                            allowed_fields.add(field_name)
                                        except Exception as e:
                                            logger.debug(f"解析列权限配置失败: {e}, permission_id={perm.id}")

                        # 如果没有匹配的权限配置，使用 checked 字段作为基础
                        if not allowed_fields:
                            fields = session.query(DatasourceField).filter(
                                DatasourceField.ds_id == self._datasource_id,
                                DatasourceField.table_id == table.id,
                                DatasourceField.checked == True
                            ).all()
                            allowed_fields = {field.field_name for field in fields}

                        if allowed_fields:
                            column_permissions[table.table_name] = allowed_fields

            except Exception as e:
                logger.warning(f"⚠️ 获取列权限失败: {e}", exc_info=True)

        table_info = {}
        for table_name in table_names:
            try:
                columns = {}
                for col in inspector.get_columns(table_name):
                    # 权限过滤：如果配置了列权限，只返回有权限的字段
                    if table_name in column_permissions:
                        if col["name"] not in column_permissions[table_name]:
                            continue

                    columns[col["name"]] = {
                        "type": str(col["type"]),
                        "comment": str(col["comment"] or ""),
                    }

                # 如果过滤后没有字段，跳过该表
                if not columns:
                    logger.debug(f"⚠️ 表 {table_name} 无可用字段（权限过滤后），跳过")
                    continue

                foreign_keys = [
                    f"{fk['constrained_columns'][0]} -> {fk['referred_table']}.{fk['referred_columns'][0]}"
                    for fk in inspector.get_foreign_keys(table_name)
                ]

                table_comment = self._get_table_comment(table_name)

                table_info[table_name] = {
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "table_comment": table_comment,
                }
            except Exception as e:
                logger.error(f"❌ 读取表 {table_name} 结构失败: {e}")

        elapsed = time.time() - start_time
        logger.info(f"✅ 成功加载 {len(table_info)} 张表，耗时 {elapsed:.2f}s")

        # 更新缓存
        if use_cache:
            with _cache_lock:
                _table_info_cache[cache_key] = (table_info, time.time())

        return table_info

    def _fetch_table_info_from_metadata(self, user_id: Optional[int], use_cache: bool, start_time: float) -> Dict[str, Dict]:
        """
        从 t_datasource_table 和 t_datasource_field 获取表结构信息。
        用于原生驱动的数据库（如 Doris、StarRocks 等），这些数据库不能通过 SQLAlchemy inspect 获取表结构。

        Args:
            user_id: 用户ID，用于权限过滤
            use_cache: 是否使用缓存
            start_time: 开始时间，用于计算耗时

        Returns:
            表信息字典
        """
        from common.permission_util import is_admin

        cache_key = (self._datasource_id or 0, user_id)
        table_info = {}

        try:
            with db_pool.get_session() as session:
                # 获取该数据源下所有已勾选的表
                tables = session.query(DatasourceTable).filter(
                    DatasourceTable.ds_id == self._datasource_id,
                    DatasourceTable.checked == True
                ).all()

                logger.info(f"🔍 从元数据加载 {len(tables)} 张表的 schema 信息（原生驱动模式）...")

                # 获取所有表的字段
                table_ids = [t.id for t in tables]
                fields = session.query(DatasourceField).filter(
                    DatasourceField.ds_id == self._datasource_id,
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
                        logger.debug(f"⚠️ 表 {table.table_name} 无可用字段，跳过")
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
            logger.error(f"❌ 从元数据获取表结构失败: {e}", exc_info=True)
            return {}

        elapsed = time.time() - start_time
        logger.info(f"✅ 成功加载 {len(table_info)} 张表（原生驱动模式），耗时 {elapsed:.2f}s")

        # 更新缓存
        if use_cache:
            with _cache_lock:
                _table_info_cache[cache_key] = (table_info, time.time())

        return table_info

    def _get_precomputed_embeddings(self, table_info: Dict[str, Dict]) -> Tuple[Optional[np.ndarray], List[str], List[str]]:
        """
        尝试从数据库获取预计算的 embedding。
        仅从 t_datasource_table.embedding 字段读取，不做任何实时计算。

        Returns:
            (预计算的 embedding 数组, 有预计算 embedding 的表名列表, 需要计算的表名列表)
        """
        if not self._datasource_id:
            return None, [], list(table_info.keys())

        try:
            with db_pool.get_session() as session:
                # 查询数据源下的所有表（不再按表名过滤，避免大小写不一致导致漏查）
                tables = (
                    session.query(DatasourceTable)
                    .filter(DatasourceTable.ds_id == self._datasource_id)
                    .all()
                )

                # 构建表名到表的映射（不区分大小写，兼容 Oracle 等会返回大写表名的数据库）
                table_map = {str(table.table_name).upper(): table for table in tables}

                # 收集有预计算 embedding 的表
                precomputed_embeddings = []
                precomputed_table_names = []
                missing_table_names = []

                for table_name, info in table_info.items():
                    # 统一按大写匹配，避免 T_ALARM_INFO / t_alarm_info 不一致导致无法命中
                    table = table_map.get(str(table_name).upper())
                    # 检查是否有 embedding 字段（通过 hasattr 检查，避免字段不存在时报错）
                    if table and hasattr(table, 'embedding') and table.embedding:
                        try:
                            embedding_vec = json.loads(table.embedding)
                            if isinstance(embedding_vec, list) and len(embedding_vec) > 0:
                                precomputed_embeddings.append(embedding_vec)
                                precomputed_table_names.append(table_name)
                            else:
                                missing_table_names.append(table_name)
                        except Exception as e:
                            logger.debug(f"解析表 {table_name} 的 embedding 失败: {e}")
                            missing_table_names.append(table_name)
                    else:
                        missing_table_names.append(table_name)

                if precomputed_embeddings:
                    embeddings_array = np.array(precomputed_embeddings).astype("float32")
                    faiss.normalize_L2(embeddings_array)
                    logger.info(f"✅ 从数据库加载了 {len(precomputed_embeddings)} 个预计算的 embedding")
                    return embeddings_array, precomputed_table_names, missing_table_names
                else:
                    return None, [], missing_table_names

        except Exception as e:
            logger.warning(f"⚠️ 获取预计算 embedding 失败: {e}")
            return None, [], list(table_info.keys())

    def _create_embeddings_with_dashscope(self, texts: List[str]) -> np.ndarray:
        """
        生成文本嵌入向量。
        优先使用在线模型，如果没有配置则使用离线模型。

        注意：该方法不在在线检索路径中调用，仅用于离线预计算工具
        或强制重建索引等管理场景中使用。
        """
        if self.use_local_embedding or not self.embedding_client:
            # 使用离线模型
            from common.local_embedding import generate_embedding_local_sync
            logger.info("🖥️ 使用离线 CPU 模型生成 embedding...")
            start_time = time.time()
            embeddings = []
            embedding_dim = None  # 动态获取维度

            for doc in texts:
                try:
                    embedding = generate_embedding_local_sync(doc)
                    if embedding:
                        if embedding_dim is None:
                            embedding_dim = len(embedding)
                        embeddings.append(embedding)
                    else:
                        logger.warning(f"⚠️ 离线模型生成 embedding 失败 ({doc[:30]}...)，使用零向量")
                        if embedding_dim is None:
                            embedding_dim = 768  # 默认维度
                        embeddings.append([0.0] * embedding_dim)
                except Exception as e:
                    logger.error(f"❌ 离线模型嵌入生成失败 ({doc[:30]}...): {e}")
                    if embedding_dim is None:
                        embedding_dim = 768  # 默认维度
                    embeddings.append([0.0] * embedding_dim)

            if not embeddings:
                logger.error("❌ 所有 embedding 生成都失败")
                return np.array([])

            embeddings = np.array(embeddings).astype("float32")
            faiss.normalize_L2(embeddings)
            logger.info(f"✅ 离线模型嵌入生成完成，耗时 {time.time() - start_time:.2f}s，维度: {embedding_dim}")
            return embeddings

        # 使用在线模型
        logger.info(f"🌐 调用在线嵌入模型 {self.embedding_model_name}...")
        start_time = time.time()
        embeddings = []
        for doc in texts:
            try:
                response = self.embedding_client.embeddings.create(model=self.embedding_model_name, input=doc)
                embeddings.append(response.data[0].embedding)
            except Exception as e:
                logger.error(f"❌ 在线模型嵌入生成失败 ({doc[:30]}...): {e}")
                embeddings.append(np.zeros(1024))  # 占位符

        embeddings = np.array(embeddings).astype("float32")
        faiss.normalize_L2(embeddings)
        logger.info(f"✅ 在线模型嵌入生成完成，耗时 {time.time() - start_time:.2f}s")
        return embeddings

    def _initialize_vector_index(self, table_info: Dict[str, Dict]):
        """
        初始化 FAISS 向量索引：从数据库读取预计算的 embedding 并构建内存索引。
        仅使用预计算的 embedding，不在检索时做实时计算。
        """
        if self._index_initialized:
            return

        # 构建新索引
        logger.info("🏗️ 开始构建向量索引（从数据库读取 embedding）...")
        start_time = time.time()

        # 记录所有表名和语料（用于 BM25 等）
        self._table_names = list(table_info.keys())
        self._corpus = [self._build_document(name, info) for name, info in table_info.items()]

        # 从数据库获取预计算的 embedding（不会做任何实时计算）
        precomputed_embeddings, precomputed_table_names, missing_table_names = self._get_precomputed_embeddings(
            table_info
        )

        # 如果没有任何预计算 embedding，则禁用向量索引（仅使用 BM25）
        if precomputed_embeddings is None or len(precomputed_table_names) == 0:
            logger.warning("⚠️ 未找到任何预计算的表结构 embedding，向量检索将被禁用，仅使用 BM25")
            self._faiss_index = None
            self._index_initialized = True
            return

        # 如果存在缺失的 embedding，为避免索引和表顺序不一致，这里直接禁用向量检索
        if len(missing_table_names) > 0:
            logger.warning(
                f"⚠️ 共有 {len(missing_table_names)} 张表缺少预计算 embedding，"
                "为保证索引与表顺序一致，本次禁用向量检索，仅使用 BM25"
            )
            self._faiss_index = None
            self._index_initialized = True
            return

        # 此时说明所有表都存在预计算 embedding，顺序与 self._table_names 一致
        embeddings = precomputed_embeddings

        if embeddings.size == 0:
            logger.error("❌ 无法生成嵌入，索引构建失败")
            return

        # 初始化 FAISS 索引（仅在内存中）
        dimension = embeddings.shape[1]
        self._faiss_index = faiss.IndexFlatIP(dimension)  # 内积 = 余弦相似度
        self._faiss_index.add(embeddings)

        elapsed = time.time() - start_time
        logger.info(f"🎉 向量索引构建完成，共 {len(self._table_names)} 张表，耗时 {elapsed:.2f}s")
        self._index_initialized = True

    def _retrieve_by_vector(self, query: str, top_k: int = 10) -> List[int]:
        """
        使用向量相似度检索最相关的表。
        优先使用在线模型，如果没有配置则使用离线模型。
        """
        if not self._faiss_index:
            logger.error("❌ 向量索引未初始化")
            return []

        try:
            # 生成查询向量
            if self.use_local_embedding or not self.embedding_client:
                # 使用离线模型
                from common.local_embedding import generate_embedding_local_sync
                embedding = generate_embedding_local_sync(query)
                if not embedding:
                    logger.warning("⚠️ 离线模型生成 embedding 失败，跳过向量检索")
                    return []
                query_vec = np.array([embedding]).astype("float32")
            else:
                # 使用在线模型
                response = self.embedding_client.embeddings.create(model=self.embedding_model_name, input=query)
                query_vec = np.array([response.data[0].embedding]).astype("float32")

            # 检查维度是否匹配
            query_dim = query_vec.shape[1]
            index_dim = self._faiss_index.d
            if query_dim != index_dim:
                logger.error(
                    f"❌ 向量维度不匹配：查询向量维度={query_dim}，索引维度={index_dim}。"
                    f"这可能是因为索引使用的是在线模型的 embedding，而查询使用的是离线模型。"
                    f"建议：重新计算表的 embedding 或使用相同的模型。"
                )
                return []

            faiss.normalize_L2(query_vec)
            _, indices = self._faiss_index.search(query_vec, top_k)
            return indices[0].tolist()
        except Exception as e:
            logger.error(f"❌ 向量检索失败: {e}", exc_info=True)
            return []

    def _retrieve_by_bm25(self, table_info: Dict[str, Dict], user_query: str) -> List[int]:
        """
        使用 BM25 算法进行关键词匹配检索。
        """
        if not user_query or not table_info:
            return list(range(len(table_info)))

        logger.info("🔄 执行 BM25 检索...")
        self._corpus = [self._build_document(name, info) for name, info in table_info.items()]
        self._tokenized_corpus = [self._tokenize_text(doc) for doc in self._corpus]
        query_tokens = self._tokenize_text(user_query)

        bm25 = BM25Okapi(self._tokenized_corpus)
        doc_scores = bm25.get_scores(query_tokens)

        # 增强：若查询词出现在表注释中，则提升分数
        enhanced_scores = doc_scores.copy()
        table_comments = [info.get("table_comment", "") for info in table_info.values()]
        for i, (comment, score) in enumerate(zip(table_comments, doc_scores)):
            if score <= 0:
                continue
            comment_tokens = self._tokenize_text(comment)
            overlap = set(query_tokens) & set(comment_tokens)
            if overlap:
                overlap_ratio = len(overlap) / len(set(query_tokens))
                enhanced_scores[i] += score * overlap_ratio * 1.5

        scored_indices = sorted(enumerate(enhanced_scores), key=lambda x: x[1], reverse=True)
        return [idx for idx, _ in scored_indices]

    @staticmethod
    def _rrf_fusion(bm25_indices: List[int], vector_indices: List[int], k: int = 60) -> List[int]:
        """
        使用 RRF（Reciprocal Rank Fusion）融合两种检索结果。
        """
        scores = {}
        for rank, idx in enumerate(bm25_indices):
            scores[idx] = scores.get(idx, 0) + 1 / (k + rank + 1)
        for rank, idx in enumerate(vector_indices):
            scores[idx] = scores.get(idx, 0) + 1 / (k + rank + 1)
        sorted_indices = sorted(scores.items(), key=lambda x: -x[1])
        return [idx for idx, _ in sorted_indices]

    def _rerank_with_dashscope(self, query: str, candidate_tables: Dict[str, Dict]) -> List[Tuple[str, float]]:
        """
        使用 DashScope 重排 API 对候选表进行重排序。
        """
        if not self.USE_RERANKER:
            logger.debug("⏭️ Reranker 已禁用或配置不完整，跳过重排序")
            return [(name, 1.0) for name in candidate_tables.keys()]

        try:
            documents = []
            name_to_text = {}
            for table_name, info in candidate_tables.items():
                doc_text = self._build_document(table_name, info)
                documents.append(doc_text)
                name_to_text[table_name] = doc_text

            if not documents:
                return []

            logger.info(f"🔁 调用重排模型 {self.rerank_model_name} 进行重排序...")

            # 根据API类型选择不同的请求结构
            if "aliyuncs" in self.rerank_base_url or "Qwen" in self.rerank_model_name:
                # 阿里云 DashScope 格式
                payload = {
                    "model": self.rerank_model_name,
                    "input": {"query": query, "documents": documents},
                    "parameters": {"top_n": len(documents), "return_documents": False},
                }
            else:
                # 其他格式（如本地模型或通用rerank API）
                payload = {"query": query, "documents": documents}

            # 设置请求头
            headers = {"Authorization": f"Bearer {self.rerank_api_key}", "Content-Type": "application/json"}

            # 调用重排 API
            response = requests.post(self.rerank_base_url, headers=headers, json=payload, timeout=30)

            # 检查响应状态
            if response.status_code != 200:
                logger.warning(f"⚠️ Rerank API 调用失败: {response.status_code} - {response.text}")
                return [(name, 1.0) for name in candidate_tables.keys()]

            # 解析响应
            result_data = response.json()

            # 根据API类型解析响应
            if "aliyuncs" in self.rerank_base_url or "Qwen" in self.rerank_model_name:
                # 阿里云格式响应
                if "output" in result_data and "results" in result_data["output"]:
                    results = []
                    for item in result_data["output"]["results"]:
                        idx = item["index"]
                        score = item["relevance_score"]
                        table_name = next(name for name, text in name_to_text.items() if text == documents[idx])
                        results.append((table_name, score))

                    results.sort(key=lambda x: x[1], reverse=True)
                    logger.info("✅ Rerank 完成")
                    return results
            else:
                # 通用格式响应 - 假设直接返回排序结果
                if "results" in result_data:
                    results = []
                    for item in result_data["results"]:
                        if "index" in item and "relevance_score" in item:  # 使用relevance_score
                            idx = item["index"]
                            score = item["relevance_score"]  # 使用relevance_score字段
                            # 从document对象中提取文本
                            if "document" in item and "text" in item["document"]:
                                doc_text = item["document"]["text"]
                                table_name = next(name for name, text in name_to_text.items() if text == doc_text)
                            else:
                                table_name = next(name for name, text in name_to_text.items() if text == documents[idx])
                            results.append((table_name, score))
                    results.sort(key=lambda x: x[1], reverse=True)
                    logger.info("✅ Rerank 完成")
                    return results
                elif isinstance(result_data, list):
                    # 假设直接返回了排序后的索引列表
                    results = []
                    for i, item in enumerate(result_data):
                        if isinstance(item, dict) and "index" in item:
                            idx = item["index"]
                            score = item.get("score", 1.0 - i * 0.01)  # 默认分数递减
                            table_name = next(name for name, text in name_to_text.items() if text == documents[idx])
                            results.append((table_name, score))
                    logger.info("✅ Rerank 完成")
                    return results

            logger.warning("⚠️ Rerank API 返回格式异常")
            return [(name, 1.0) for name in candidate_tables.keys()]

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Rerank API 请求失败: {e}")
            return [(name, 1.0) for name in candidate_tables.keys()]
        except Exception as e:
            logger.error(f"❌ Rerank 过程出错: {e}")
            return [(name, 1.0) for name in candidate_tables.keys()]

    def supplement_related_tables(
        self,
        selected_table_names: List[str],
        all_table_info: Dict[str, Dict],
    ) -> List[str]:
        """

        - 表节点: {"id": 15, "shape": "er-rect", "attrs": {"text": {"text": "t_products"}}, ...}
        - 关系边: {"shape": "edge", "source": {"cell": 15, "port": "135"}, "target": {"cell": 14, "port": "128"}}

        其中 edge.source/target.cell 使用的是表记录主键 ID（对应 DatasourceTable.id）。

        Args:
            selected_table_names: 已选中的表名列表（来自检索阶段返回的 db_info.keys()）
            all_table_info: 当前数据源下所有可用表的信息 dict（用于过滤补充表是否在权限范围内）

        Returns:
            扩展后的表名列表（包含原始表和通过表关系补充的关联表）
        """
        if not self._datasource_id or not selected_table_names:
            return selected_table_names

        try:
            with db_pool.get_session() as session:
                datasource = session.query(Datasource).filter(
                    Datasource.id == self._datasource_id
                ).first()
                if not datasource or not datasource.table_relation:
                    return selected_table_names

                relations = datasource.table_relation
                if not isinstance(relations, list):
                    return selected_table_names

                # 节点和边
                table_nodes = [
                    r for r in relations if r.get("shape") in ("er-rect", "rect")
                ]
                edges = [r for r in relations if r.get("shape") == "edge"]
                if not edges:
                    return selected_table_names

                # 查询该数据源下所有表，构建 id <-> name 映射
                all_tables = session.query(DatasourceTable).filter(
                    DatasourceTable.ds_id == self._datasource_id
                ).all()
                if not all_tables:
                    return selected_table_names

                table_id_to_name = {table.id: table.table_name for table in all_tables}

                # 已选中的表对应的表 ID（embedding / 检索阶段选中的表）
                selected_name_set = set(selected_table_names)
                selected_table_ids = {
                    table.id for table in all_tables if table.table_name in selected_name_set
                }
                if not selected_table_ids:
                    return selected_table_names

                selected_table_ids_str = {str(tid) for tid in selected_table_ids}

                # 找出与选中表相关的所有关系（任一端命中即可）
                related_relations = []
                for edge in edges:
                    source = edge.get("source", {}) or {}
                    target = edge.get("target", {}) or {}
                    source_id = str(source.get("cell", "")) if source.get("cell") is not None else ""
                    target_id = str(target.get("cell", "")) if target.get("cell") is not None else ""
                    if source_id in selected_table_ids_str or target_id in selected_table_ids_str:
                        related_relations.append(edge)

                if not related_relations:
                    logger.debug(
                        f"表关系补充：未发现与选中表 {selected_table_names} 相关的关系边，跳过补充"
                    )
                    return selected_table_names

                # 提取关系中的所有表 ID
                relation_table_ids_str = set()
                for rel in related_relations:
                    source = rel.get("source", {}) or {}
                    target = rel.get("target", {}) or {}
                    source_id = str(source.get("cell", "")) if source.get("cell") is not None else ""
                    target_id = str(target.get("cell", "")) if target.get("cell") is not None else ""
                    if source_id:
                        relation_table_ids_str.add(source_id)
                    if target_id:
                        relation_table_ids_str.add(target_id)

                # 找出缺失的表 ID：关系中出现，但当前未选中
                missing_table_ids_str = relation_table_ids_str - selected_table_ids_str

                # 根据 ID 映射到表名，并确保在 all_table_info 中（权限过滤之后）
                missing_table_names: List[str] = []
                for tid_str in missing_table_ids_str:
                    try:
                        tid = int(tid_str)
                    except (TypeError, ValueError):
                        continue
                    table_name = table_id_to_name.get(tid)
                    if table_name and table_name in all_table_info:
                        missing_table_names.append(table_name)

                if missing_table_names:
                    logger.info(
                        f"🔗 表关系补充：从 {selected_table_names} 补充 "
                        f"{len(missing_table_names)} 个关联表: {missing_table_names}"
                    )
                    extended_names = selected_table_names + [
                        name for name in missing_table_names if name not in selected_name_set
                    ]
                else:
                    extended_names = selected_table_names

                # 生成 table1.field1=table2.field2 形式的外键信息，写入 all_table_info
                # 构建 node 映射，便于通过 (cell, port) 找到字段名
                node_by_id = {str(n.get("id")): n for n in table_nodes if n.get("id") is not None}

                def _get_field_name(cell_id: str, port_id: str) -> str:
                    """从关系图节点或 DatasourceField 中解析字段名。"""
                    # 1) 从前端关系图的 ports 中取
                    node = node_by_id.get(cell_id)
                    if node:
                        ports = (node.get("ports") or {}).get("items") or []
                        for p in ports:
                            if str(p.get("id")) == str(port_id):
                                return (
                                    p.get("attrs", {})
                                    .get("portNameLabel", {})
                                    .get("text", "")
                                    .strip()
                                )
                    # 2) 兜底：从 DatasourceField.id 读取
                    try:
                        if port_id and str(port_id).isdigit():
                            field = session.query(DatasourceField).filter(
                                DatasourceField.id == int(port_id)
                            ).first()
                            if field and field.field_name:
                                return field.field_name.strip()
                    except Exception:
                        pass
                    return ""

                # 为参与关系的表构建 foreign_keys 列表
                extracted_fks = []
                for rel in related_relations:
                    source = rel.get("source", {}) or {}
                    target = rel.get("target", {}) or {}
                    source_id = str(source.get("cell", "")) if source.get("cell") is not None else ""
                    target_id = str(target.get("cell", "")) if target.get("cell") is not None else ""
                    source_port = str(source.get("port", "")) if source.get("port") is not None else ""
                    target_port = str(target.get("port", "")) if target.get("port") is not None else ""

                    # cell id -> 表名
                    try:
                        s_tid = int(source_id) if source_id and source_id.isdigit() else None
                        t_tid = int(target_id) if target_id and target_id.isdigit() else None
                    except ValueError:
                        s_tid = t_tid = None

                    s_table = table_id_to_name.get(s_tid) if s_tid is not None else None
                    t_table = table_id_to_name.get(t_tid) if t_tid is not None else None

                    if not s_table or not t_table:
                        logger.debug(f"跳过关系：无法解析表名 (source_id={source_id}, target_id={target_id})")
                        continue
                    if s_table not in all_table_info or t_table not in all_table_info:
                        logger.debug(f"跳过关系：表不在权限范围内 (s_table={s_table}, t_table={t_table})")
                        continue

                    # 获取字段名
                    s_field = _get_field_name(source_id, source_port)
                    t_field = _get_field_name(target_id, target_port)
                    if not s_field or not t_field:
                        logger.debug(f"跳过关系：无法解析字段名 (source_id={source_id}, port={source_port}, target_id={target_id}, port={target_port})")
                        continue

                    fk_str = f"{s_table}.{s_field}={t_table}.{t_field}"
                    extracted_fks.append(fk_str)

                    # 写入两端表的 foreign_keys 列表（避免重复）
                    for tbl in (s_table, t_table):
                        fk_list = all_table_info[tbl].setdefault("foreign_keys", [])
                        if fk_str not in fk_list:
                            fk_list.append(fk_str)

                # 记录关系提取结果（仅记录数量）
                if extracted_fks:
                    logger.debug(f"提取到 {len(extracted_fks)} 条外键关系")
                else:
                    logger.debug("未提取到外键关系")

                return extended_names

        except Exception as e:
            logger.warning(f"⚠️ 表关系补充失败: {e}", exc_info=True)
            return selected_table_names

    def get_table_schema(self, state: AgentState) -> AgentState:
        """
        根据用户查询，通过混合检索筛选出最相关的数据库表结构。
        包含权限过滤、表关系补充等功能。
        """
        try:
            logger.info("🔍 开始获取数据库表 schema 信息")
            user_id = state.get("user_id")
            all_table_info = self._fetch_all_table_info(user_id=user_id)

            user_query = state.get("user_query", "").strip()
            if not user_query:
                state["db_info"] = all_table_info
                state["bm25_tokens"] = []  # 无查询时，分词列表为空
                logger.info(f"ℹ️ 无用户查询，返回全部 {len(all_table_info)} 张表")
                return state

            # 记录 BM25 分词信息，便于在 schema_inspector 节点向用户解释
            try:
                bm25_tokens = self._tokenize_text(user_query)
                state["bm25_tokens"] = bm25_tokens
                if bm25_tokens:
                    logger.info(f"✅ BM25 分词成功: {len(bm25_tokens)} 个词: {bm25_tokens[:5]}")
                else:
                    logger.warning(f"⚠️ BM25 分词结果为空，用户查询: {user_query}")
            except Exception as e:
                logger.error(f"❌ BM25 分词记录失败: {e}", exc_info=True)
                state["bm25_tokens"] = []  # 分词失败时，设置为空列表

            # 确保 user_query 也在返回的 state 中（虽然它应该已经在初始 state 中了）
            state["user_query"] = user_query

            # 初始化向量索引
            self._initialize_vector_index(all_table_info)

            # 混合检索 - 并行执行 BM25 和向量检索以提高性能
            logger.info("🔍 开始混合检索：BM25 + 向量检索（并行执行）")

            # 使用线程池并行执行 BM25 和向量检索
            with ThreadPoolExecutor(max_workers=2) as executor:
                bm25_future = executor.submit(self._retrieve_by_bm25, all_table_info, user_query)
                vector_future = executor.submit(self._retrieve_by_vector, user_query, 20)

                # 等待两个任务完成
                bm25_top_indices = bm25_future.result()
                vector_top_indices = vector_future.result()

            logger.info(f"📊 BM25检索返回 {len(bm25_top_indices)} 个结果")
            logger.info(f"🔗 向量检索返回 {len(vector_top_indices)} 个结果")

            # 过滤：仅保留同时在 BM25 前 50 和向量结果中的表
            valid_bm25_set = set(bm25_top_indices[:50])
            candidate_indices = [idx for idx in vector_top_indices if idx in valid_bm25_set]
            logger.info(f"🎯 初步筛选后保留 {len(candidate_indices)} 个候选表")

            if not candidate_indices:
                candidate_indices = bm25_top_indices[:TABLE_RETURN_COUNT]  # 降级
                logger.info(f"⚠️ 候选表为空，降级使用BM25前{TABLE_RETURN_COUNT}个结果")

            fused_indices = self._rrf_fusion(bm25_top_indices, candidate_indices, k=60)
            logger.info(f"🔄 RRF融合后得到 {len(fused_indices)} 个结果")

            # 评分筛选
            selected_indices = []
            for idx in fused_indices:
                bm25_rank = bm25_top_indices.index(idx) + 1 if idx in bm25_top_indices else len(all_table_info) + 1
                vector_rank = (
                    vector_top_indices.index(idx) + 1 if idx in vector_top_indices else len(all_table_info) + 1
                )
                score = 1 / (60 + bm25_rank) + 1 / (60 + vector_rank)
                if score >= 0.01 and len(selected_indices) < 10:
                    selected_indices.append(idx)

            candidate_table_names = [self._table_names[i] for i in selected_indices]
            candidate_table_info = {name: all_table_info[name] for name in candidate_table_names}

            # 重排序
            reranked_results = self._rerank_with_dashscope(user_query, candidate_table_info)
            final_table_names = [name for name, _ in reranked_results][:TABLE_RETURN_COUNT]  # 取 top N（可配置）

            # 去重
            final_table_names = list(dict.fromkeys(final_table_names))

            # 构建输出（表关系补充将在 SQL 生成阶段进行）
            filtered_info = {name: all_table_info[name] for name in final_table_names if name in all_table_info}

            # 打印结果摘要（使用 logger 以便统一格式化）
            logger.info("🔍 用户查询: %s", user_query)
            logger.info("📊 检索与排序结果:")
            for i, table_name in enumerate(final_table_names[:TABLE_RETURN_COUNT]):
                if table_name in self._table_names:
                    bm25_idx = self._table_names.index(table_name)
                    bm25_rank = bm25_top_indices.index(bm25_idx) + 1 if bm25_idx in bm25_top_indices else "-"
                    vector_rank = vector_top_indices.index(bm25_idx) + 1 if bm25_idx in vector_top_indices else "-"
                    rerank_score = next((score for name, score in reranked_results if name == table_name), 0.0)
                    logger.info(
                        "  %s. %-15s | BM25: %2s | Vector: %2s | Rerank: %.3f",
                        i + 1,
                        table_name,
                        bm25_rank,
                        vector_rank,
                        rerank_score,
                    )

            state["db_info"] = filtered_info
            logger.info(f"✅ 最终筛选出 {len(filtered_info)} 个相关表: {list(filtered_info.keys())}")

        except Exception as e:
            logger.error(f"❌ 获取数据库表信息失败: {e}", exc_info=True)
            state["db_info"] = {}
            state["execution_result"] = ExecutionResult(success=False, error="无法连接数据库或获取元数据")
            # 即使出错，也确保 bm25_tokens 和 user_query 被设置
            if "bm25_tokens" not in state:
                state["bm25_tokens"] = []
            if "user_query" not in state:
                state["user_query"] = state.get("user_query", "")

        return state

    def execute_sql(self, state: AgentState) -> AgentState:
        """
        执行生成的 SQL 语句。
        优先使用权限过滤后的SQL（filtered_sql），如果没有则使用原始生成的SQL（generated_sql）。
        支持 SQLAlchemy 驱动和原生驱动两种执行方式。
        """
        # 优先使用权限过滤后的SQL，如果没有则使用原始生成的SQL
        sql_to_execute = state.get("filtered_sql") or state.get("generated_sql", "")
        sql_to_execute = sql_to_execute.strip() if sql_to_execute else ""

        if not sql_to_execute:
            error_msg = "SQL 为空，无法执行"
            logger.warning(error_msg)
            state["execution_result"] = ExecutionResult(success=False, error=error_msg)
            return state

        logger.info("▶️ 执行 SQL 语句")
        # 记录使用的SQL类型（用于调试）
        if state.get("filtered_sql"):
            logger.info("使用权限过滤后的SQL执行")
        else:
            logger.info("使用原始生成的SQL执行")

        try:
            # 检查数据源是否使用原生驱动
            use_native_driver = False
            if self._datasource_type and self._datasource_id:
                db_enum = DB.get_db(self._datasource_type, default_if_none=True)
                use_native_driver = db_enum.connect_type == ConnectType.py_driver

            if use_native_driver and self._datasource_config:
                # 对于原生驱动的数据库，使用 DatasourceConnectionUtil.execute_query
                logger.info(f"使用原生驱动执行 SQL（数据源类型: {self._datasource_type}）")
                config = DatasourceConfigUtil.decrypt_config(self._datasource_config)
                result_data = DatasourceConnectionUtil.execute_query(
                    self._datasource_type, config, sql_to_execute
                )
                state["execution_result"] = ExecutionResult(success=True, data=result_data)
                logger.info(f"✅ SQL 执行成功（原生驱动），返回 {len(result_data)} 条记录")
            else:
                # 对于 SQLAlchemy 驱动的数据库，使用 engine 执行
                with self._engine.connect() as connection:
                    result = connection.execute(text(sql_to_execute))
                    result_data = result.fetchall()
                    columns = result.keys()
                    frame = pd.DataFrame(result_data, columns=columns)
                    state["execution_result"] = ExecutionResult(success=True, data=frame.to_dict(orient="records"))
                    logger.info(f"✅ SQL 执行成功，返回 {len(result_data)} 条记录")
        except Exception as e:
            error_msg = f"执行 SQL 失败: {e}"
            logger.error(error_msg, exc_info=True)
            state["execution_result"] = ExecutionResult(success=False, error=str(e))
        return state
