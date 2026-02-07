"""
数据源工具类
"""

import json
import logging
import platform
import urllib.parse
from base64 import b64encode
from decimal import Decimal
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple

import pymysql
import psycopg2
import requests
from elasticsearch import Elasticsearch
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

# 达梦数据库驱动（可选依赖）
try:
    import dmPython
except ImportError:
    dmPython = None

# AWS Redshift 驱动
try:
    import redshift_connector
except ImportError:
    redshift_connector = None

logger = logging.getLogger(__name__)


class ConnectType(Enum):
    """数据库连接类型"""
    sqlalchemy = 'sqlalchemy'
    py_driver = 'py_driver'


class DB(Enum):
    """数据库类型枚举"""
    mysql = ('mysql', 'MySQL', '`', '`', ConnectType.sqlalchemy)
    pg = ('pg', 'PostgreSQL', '"', '"', ConnectType.sqlalchemy)
    oracle = ('oracle', 'Oracle', '"', '"', ConnectType.sqlalchemy)
    sqlServer = ('sqlServer', 'SQL Server', '[', ']', ConnectType.sqlalchemy)
    ck = ('ck', 'ClickHouse', '"', '"', ConnectType.sqlalchemy)
    dm = ('dm', '达梦', '"', '"', ConnectType.py_driver)
    doris = ('doris', 'Apache Doris', '`', '`', ConnectType.py_driver)
    redshift = ('redshift', 'AWS Redshift', '"', '"', ConnectType.py_driver)
    es = ('es', 'Elasticsearch', '"', '"', ConnectType.py_driver)
    kingbase = ('kingbase', 'Kingbase', '"', '"', ConnectType.py_driver)
    starrocks = ('starrocks', 'StarRocks', '`', '`', ConnectType.py_driver)

    def __init__(self, type_code: str, db_name: str, prefix: str, suffix: str, connect_type: ConnectType):
        self.type_code = type_code
        self.db_name = db_name
        self.prefix = prefix
        self.suffix = suffix
        self.connect_type = connect_type

    @classmethod
    def get_db(cls, ds_type: str, default_if_none: bool = False):
        """根据类型代码获取数据库枚举"""
        for db in cls:
            if db.type_code.lower() == ds_type.lower():
                return db
        if default_if_none:
            return DB.pg
        raise ValueError(f"不支持的数据库类型: {ds_type}")


class DatasourceConnectionUtil:
    """数据源连接工具类"""

    # 需要 Schema 的数据库类型
    NEED_SCHEMA_TYPES = ['sqlServer', 'pg', 'oracle', 'dm', 'redshift', 'kingbase']

    @staticmethod
    def build_connection_uri(ds_type: str, config: Dict[str, Any]) -> str:
        """构建数据库连接URI（仅用于 SQLAlchemy 驱动的数据库）"""
        host = config.get("host", "")
        port = config.get("port", 3306)
        username = config.get("username", "")
        password = config.get("password", "")
        database = config.get("database", "")
        extra_jdbc = config.get("extraJdbc", "")
        mode = config.get("mode", "service_name")

        # URL编码用户名和密码
        username_encoded = urllib.parse.quote(username)
        password_encoded = urllib.parse.quote(password)

        if ds_type == "mysql":
            if extra_jdbc:
                return f"mysql+pymysql://{username_encoded}:{password_encoded}@{host}:{port}/{database}?{extra_jdbc}"
            return f"mysql+pymysql://{username_encoded}:{password_encoded}@{host}:{port}/{database}"

        elif ds_type == "pg":
            if extra_jdbc:
                return (
                    f"postgresql+psycopg2://{username_encoded}:{password_encoded}@{host}:{port}/{database}?{extra_jdbc}"
                )
            return f"postgresql+psycopg2://{username_encoded}:{password_encoded}@{host}:{port}/{database}"

        elif ds_type == "oracle":
            if mode == "service_name":
                if extra_jdbc:
                    return f"oracle+oracledb://{username_encoded}:{password_encoded}@{host}:{port}?service_name={database}&{extra_jdbc}"
                return f"oracle+oracledb://{username_encoded}:{password_encoded}@{host}:{port}?service_name={database}"
            else:
                if extra_jdbc:
                    return (
                        f"oracle+oracledb://{username_encoded}:{password_encoded}@{host}:{port}/{database}?{extra_jdbc}"
                    )
                return f"oracle+oracledb://{username_encoded}:{password_encoded}@{host}:{port}/{database}"

        elif ds_type == "sqlServer":
            if extra_jdbc:
                return f"mssql+pymssql://{username_encoded}:{password_encoded}@{host}:{port}/{database}?{extra_jdbc}"
            return f"mssql+pymssql://{username_encoded}:{password_encoded}@{host}:{port}/{database}"

        elif ds_type == "ck":
            if extra_jdbc:
                return f"clickhouse+http://{username_encoded}:{password_encoded}@{host}:{port}/{database}?{extra_jdbc}"
            return f"clickhouse+http://{username_encoded}:{password_encoded}@{host}:{port}/{database}"

        else:
            raise ValueError(f"不支持使用 SQLAlchemy 连接的数据源类型: {ds_type}")

    @staticmethod
    def _get_extra_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """解析额外的JDBC参数"""
        config_dict = {}
        extra_jdbc = config.get("extraJdbc", "")
        if extra_jdbc:
            config_arr = extra_jdbc.split("&")
            for item in config_arr:
                kv = item.split("=")
                if len(kv) == 2 and kv[0] and kv[1]:
                    config_dict[kv[0]] = kv[1]
        return config_dict

    @staticmethod
    def _get_es_auth(config: Dict[str, Any]) -> Dict[str, str]:
        """获取 Elasticsearch 认证头"""
        username = config.get("username", "")
        password = config.get("password", "")
        credentials = f"{username}:{password}"
        encoded_credentials = b64encode(credentials.encode()).decode()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}"
        }

    @staticmethod
    def _get_es_connect(config: Dict[str, Any]) -> Elasticsearch:
        """获取 Elasticsearch 连接"""
        host = config.get("host", "")
        username = config.get("username", "")
        password = config.get("password", "")

        es_client = Elasticsearch(
            [host],
            basic_auth=(username, password),
            verify_certs=False,
            compatibility_mode=True,
            headers=DatasourceConnectionUtil._get_es_auth(config)
        )
        return es_client

    @staticmethod
    def test_connection(ds_type: str, config: Dict[str, Any]) -> Tuple[bool, str]:
        """测试数据库连接"""
        try:
            db = DB.get_db(ds_type)
            timeout = config.get("timeout", 30)
            extra_config = DatasourceConnectionUtil._get_extra_config(config)

            if db.connect_type == ConnectType.sqlalchemy:
                # SQLAlchemy 驱动的数据库
                uri = DatasourceConnectionUtil.build_connection_uri(ds_type, config)
                # 注意：部分驱动（如 oracledb）不支持 connect_timeout 关键字参数
                if ds_type in ("oracle"):
                    engine = create_engine(uri, pool_pre_ping=True)
                elif ds_type == "sqlServer":
                    # SQL Server 2022 需要禁用加密以兼容 pymssql
                    # pymssql 不支持 connect_timeout，使用 login_timeout 和 timeout
                    engine = create_engine(
                        uri, pool_pre_ping=True, connect_args={"timeout": timeout, "login_timeout": timeout, "encryption": "off"}
                    )
                else:
                    engine = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": timeout})
                with engine.connect() as conn:
                    # Oracle 要求 SELECT 必须有 FROM 子句
                    test_sql = "SELECT 1 FROM DUAL" if ds_type in ("oracle") else "SELECT 1"
                    conn.execute(text(test_sql))
                return True, ""

            else:
                # Python 原生驱动的数据库
                host = config.get("host", "")
                port = config.get("port", 3306)
                username = config.get("username", "")
                password = config.get("password", "")
                database = config.get("database", "")

                if ds_type == "dm":
                    # 达梦数据库
                    if dmPython is None:
                        return False, "未安装达梦数据库驱动 dmPython"
                    with dmPython.connect(user=username, password=password, server=host,
                                          port=port, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute('SELECT 1', timeout=timeout)
                            cursor.fetchall()
                    return True, ""

                elif ds_type in ("doris", "starrocks"):
                    # Apache Doris / StarRocks（使用 MySQL 协议）
                    # 使用优化的连接参数以提高连接稳定性
                    connect_timeout = max(timeout, 60)  # 至少 60 秒连接超时
                    with pymysql.connect(
                        user=username,
                        passwd=password,
                        host=host,
                        port=port,
                        db=database,
                        connect_timeout=connect_timeout,
                        read_timeout=timeout,
                        write_timeout=timeout,
                        charset='utf8mb4',
                        autocommit=True,
                        **extra_config
                    ) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute('SELECT 1')
                    return True, ""

                elif ds_type == "redshift":
                    # AWS Redshift
                    if redshift_connector is None:
                        return False, "未安装 redshift_connector 驱动"
                    with redshift_connector.connect(host=host, port=port, database=database,
                                                    user=username, password=password,
                                                    timeout=timeout, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute('SELECT 1')
                    return True, ""

                elif ds_type == "kingbase":
                    # 人大金仓（使用 PostgreSQL 协议）
                    with psycopg2.connect(host=host, port=port, database=database,
                                          user=username, password=password,
                                          connect_timeout=timeout, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute('SELECT 1')
                    return True, ""

                elif ds_type == "es":
                    # Elasticsearch
                    es_client = DatasourceConnectionUtil._get_es_connect(config)
                    if es_client.ping():
                        return True, ""
                    else:
                        return False, "Elasticsearch 连接失败"

                else:
                    return False, f"不支持的数据源类型: {ds_type}"

        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False, str(e)

    @staticmethod
    def _get_table_sql(ds_type: str, config: Dict[str, Any]) -> Tuple[str, Any]:
        """获取查询表列表的 SQL"""
        database = config.get("database", "")
        db_schema = config.get("dbSchema") or database

        if ds_type == "mysql":
            return """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = :param
            """, database

        elif ds_type == "sqlServer":
            return """
                SELECT
                    TABLE_NAME AS [TABLE_NAME],
                    ISNULL(ep.value, '') AS [TABLE_COMMENT]
                FROM INFORMATION_SCHEMA.TABLES t
                LEFT JOIN sys.extended_properties ep
                    ON ep.major_id = OBJECT_ID(t.TABLE_SCHEMA + '.' + t.TABLE_NAME)
                    AND ep.minor_id = 0
                    AND ep.name = 'MS_Description'
                WHERE t.TABLE_TYPE IN ('BASE TABLE', 'VIEW')
                    AND t.TABLE_SCHEMA = :param
            """, db_schema

        elif ds_type == "pg":
            return """
                SELECT c.relname AS TABLE_NAME,
                       COALESCE(d.description, obj_description(c.oid)) AS TABLE_COMMENT
                FROM pg_class c
                LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
                WHERE n.nspname = :param
                    AND c.relkind IN ('r', 'v', 'p', 'm')
                    AND c.relname NOT LIKE 'pg_%'
                    AND c.relname NOT LIKE 'sql_%'
                ORDER BY c.relname
            """, db_schema

        elif ds_type == "oracle":
            return """
                SELECT DISTINCT
                    t.TABLE_NAME AS "TABLE_NAME",
                    NVL(c.COMMENTS, '') AS "TABLE_COMMENT"
                FROM (
                    SELECT TABLE_NAME, 'TABLE' AS OBJECT_TYPE FROM ALL_TABLES WHERE OWNER = :param
                    UNION ALL
                    SELECT VIEW_NAME AS TABLE_NAME, 'VIEW' AS OBJECT_TYPE FROM ALL_VIEWS WHERE OWNER = :param
                    UNION ALL
                    SELECT MVIEW_NAME AS TABLE_NAME, 'MATERIALIZED VIEW' AS OBJECT_TYPE FROM ALL_MVIEWS WHERE OWNER = :param
                ) t
                LEFT JOIN ALL_TAB_COMMENTS c
                    ON t.TABLE_NAME = c.TABLE_NAME
                    AND c.TABLE_TYPE = t.OBJECT_TYPE
                    AND c.OWNER = :param
                ORDER BY t.TABLE_NAME
            """, db_schema

        elif ds_type == "ck":
            return """
                SELECT name, comment
                FROM system.tables
                WHERE database = :param
                    AND engine NOT IN ('Dictionary')
                ORDER BY name
            """, database

        elif ds_type == "dm":
            return """
                SELECT table_name, comments
                FROM all_tab_comments
                WHERE owner = :param
                    AND (table_type = 'TABLE' OR table_type = 'VIEW')
            """, db_schema

        elif ds_type == "redshift":
            return """
                SELECT relname AS TableName,
                       obj_description(relfilenode::regclass, 'pg_class') AS TableDescription
                FROM pg_class
                WHERE relkind IN ('r', 'p', 'f')
                    AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = %s)
            """, db_schema

        elif ds_type in ("doris", "starrocks"):
            return """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
            """, database

        elif ds_type == "kingbase":
            return """
                SELECT c.relname AS TABLE_NAME,
                       COALESCE(d.description, obj_description(c.oid)) AS TABLE_COMMENT
                FROM pg_class c
                LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
                WHERE n.nspname = '{0}'
                    AND c.relkind IN ('r', 'v', 'p', 'm')
                    AND c.relname NOT LIKE 'pg_%'
                    AND c.relname NOT LIKE 'sql_%'
                ORDER BY c.relname
            """, db_schema

        elif ds_type == "es":
            return "", None

        else:
            raise ValueError(f"不支持的数据源类型: {ds_type}")

    @staticmethod
    def get_tables(ds_type: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取数据库表列表"""
        try:
            db = DB.get_db(ds_type)
            timeout = config.get("timeout", 30)
            extra_config = DatasourceConnectionUtil._get_extra_config(config)
            sql, sql_param = DatasourceConnectionUtil._get_table_sql(ds_type, config)

            tables = []

            if db.connect_type == ConnectType.sqlalchemy:
                # SQLAlchemy 驱动的数据库
                uri = DatasourceConnectionUtil.build_connection_uri(ds_type, config)
                if ds_type == "oracle":
                    engine = create_engine(uri, pool_pre_ping=True)
                elif ds_type == "sqlServer":
                    # SQL Server 2022 需要禁用加密以兼容 pymssql
                    # pymssql 不支持 connect_timeout，使用 login_timeout 和 timeout
                    engine = create_engine(
                        uri, pool_pre_ping=True, connect_args={"timeout": timeout, "login_timeout": timeout, "encryption": "off"}
                    )
                else:
                    engine = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": timeout})
                with engine.connect() as conn:
                    result = conn.execute(text(sql), {"param": sql_param})
                    for row in result.fetchall():
                        # 处理 bytes 类型（SQL Server 可能返回 bytes）
                        table_name = row[0]
                        table_comment = row[1] or ""
                        if isinstance(table_comment, bytes):
                            try:
                                table_comment = table_comment.decode('utf-8')
                            except UnicodeDecodeError:
                                try:
                                    table_comment = table_comment.decode('latin-1')
                                except:
                                    table_comment = ""
                        if isinstance(table_name, bytes):
                            try:
                                table_name = table_name.decode('utf-8')
                            except UnicodeDecodeError:
                                try:
                                    table_name = table_name.decode('latin-1')
                                except:
                                    table_name = str(table_name)
                        tables.append({
                            "tableName": table_name,
                            "tableComment": table_comment,
                        })
            else:
                # Python 原生驱动的数据库
                host = config.get("host", "")
                port = config.get("port", 3306)
                username = config.get("username", "")
                password = config.get("password", "")
                database = config.get("database", "")

                if ds_type == "dm":
                    if dmPython is None:
                        raise Exception("未安装达梦数据库驱动 dmPython")
                    with dmPython.connect(user=username, password=password, server=host,
                                          port=port, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql, {"param": sql_param}, timeout=timeout)
                            for row in cursor.fetchall():
                                tables.append({
                                    "tableName": row[0],
                                    "tableComment": row[1] or "",
                                })

                elif ds_type in ("doris", "starrocks"):
                    # 使用优化的连接参数以提高连接稳定性
                    connect_timeout = max(timeout, 60)  # 至少 60 秒连接超时
                    with pymysql.connect(
                        user=username,
                        passwd=password,
                        host=host,
                        port=port,
                        db=database,
                        connect_timeout=connect_timeout,
                        read_timeout=timeout,
                        write_timeout=timeout,
                        charset='utf8mb4',
                        autocommit=True,
                        **extra_config
                    ) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql, (sql_param,))
                            for row in cursor.fetchall():
                                tables.append({
                                    "tableName": row[0],
                                    "tableComment": row[1] or "",
                                })

                elif ds_type == "redshift":
                    if redshift_connector is None:
                        raise Exception("未安装 redshift_connector 驱动")
                    with redshift_connector.connect(host=host, port=port, database=database,
                                                    user=username, password=password,
                                                    timeout=timeout, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql, (sql_param,))
                            for row in cursor.fetchall():
                                tables.append({
                                    "tableName": row[0],
                                    "tableComment": row[1] or "",
                                })

                elif ds_type == "kingbase":
                    db_schema = config.get("dbSchema") or database
                    with psycopg2.connect(host=host, port=port, database=database,
                                          user=username, password=password,
                                          options=f"-c statement_timeout={timeout * 1000}",
                                          **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql.format(db_schema))
                            for row in cursor.fetchall():
                                tables.append({
                                    "tableName": row[0],
                                    "tableComment": row[1] or "",
                                })

                elif ds_type == "es":
                    # Elasticsearch：获取索引列表
                    es_client = DatasourceConnectionUtil._get_es_connect(config)
                    indices = es_client.cat.indices(format="json")
                    if indices:
                        for idx in indices:
                            index_name = idx.get('index')
                            desc = ''
                            # 获取 mapping 中的描述
                            try:
                                mapping = es_client.indices.get_mapping(index=index_name)
                                mappings = mapping.get(index_name, {}).get("mappings", {})
                                if mappings.get('_meta'):
                                    desc = mappings.get('_meta', {}).get('description', '')
                            except Exception:
                                pass
                            tables.append({
                                "tableName": index_name,
                                "tableComment": desc,
                            })

            return tables
        except Exception as e:
            logger.error(f"获取表列表失败: {e}")
            raise

    @staticmethod
    def _get_field_sql(ds_type: str, config: Dict[str, Any], table_name: str) -> Tuple[str, Any, Any]:
        """获取查询字段列表的 SQL"""
        database = config.get("database", "")
        db_schema = config.get("dbSchema") or database

        if ds_type == "mysql":
            sql = """
                SELECT COLUMN_NAME, DATA_TYPE, COLUMN_COMMENT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :param1
            """
            if table_name:
                sql += " AND TABLE_NAME = :param2"
            return sql, database, table_name

        elif ds_type == "sqlServer":
            sql = """
                SELECT
                    COLUMN_NAME AS [COLUMN_NAME],
                    DATA_TYPE AS [DATA_TYPE],
                    ISNULL(EP.value, '') AS [COLUMN_COMMENT]
                FROM INFORMATION_SCHEMA.COLUMNS C
                LEFT JOIN sys.extended_properties EP
                    ON EP.major_id = OBJECT_ID(C.TABLE_SCHEMA + '.' + C.TABLE_NAME)
                    AND EP.minor_id = C.ORDINAL_POSITION
                    AND EP.name = 'MS_Description'
                WHERE C.TABLE_SCHEMA = :param1
            """
            if table_name:
                sql += " AND C.TABLE_NAME = :param2"
            return sql, db_schema, table_name

        elif ds_type == "pg":
            sql = """
                SELECT a.attname AS COLUMN_NAME,
                       pg_catalog.format_type(a.atttypid, a.atttypmod) AS DATA_TYPE,
                       col_description(c.oid, a.attnum) AS COLUMN_COMMENT
                FROM pg_catalog.pg_attribute a
                JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = :param1
                    AND a.attnum > 0
                    AND NOT a.attisdropped
            """
            if table_name:
                sql += " AND c.relname = :param2"
            return sql, db_schema, table_name

        elif ds_type == "oracle":
            sql = """
                SELECT
                    col.COLUMN_NAME AS "COLUMN_NAME",
                    (CASE
                        WHEN col.DATA_TYPE IN ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR')
                            THEN col.DATA_TYPE || '(' || col.DATA_LENGTH || ')'
                        WHEN col.DATA_TYPE = 'NUMBER' AND col.DATA_PRECISION IS NOT NULL
                            THEN col.DATA_TYPE || '(' || col.DATA_PRECISION ||
                                 CASE WHEN col.DATA_SCALE > 0 THEN ',' || col.DATA_SCALE END || ')'
                        ELSE col.DATA_TYPE
                    END) AS "DATA_TYPE",
                    NVL(com.COMMENTS, '') AS "COLUMN_COMMENT"
                FROM ALL_TAB_COLUMNS col
                LEFT JOIN ALL_COL_COMMENTS com
                    ON col.OWNER = com.OWNER
                    AND col.TABLE_NAME = com.TABLE_NAME
                    AND col.COLUMN_NAME = com.COLUMN_NAME
                WHERE col.OWNER = :param1
            """
            if table_name:
                sql += " AND col.TABLE_NAME = :param2"
            return sql, db_schema, table_name

        elif ds_type == "ck":
            sql = """
                SELECT name AS COLUMN_NAME, type AS DATA_TYPE, comment AS COLUMN_COMMENT
                FROM system.columns
                WHERE database = :param1
            """
            if table_name:
                sql += " AND table = :param2"
            return sql, database, table_name

        elif ds_type == "dm":
            sql = """
                SELECT
                    c.COLUMN_NAME AS "COLUMN_NAME",
                    c.DATA_TYPE AS "DATA_TYPE",
                    COALESCE(com.COMMENTS, '') AS "COMMENTS"
                FROM ALL_TAB_COLS c
                LEFT JOIN ALL_COL_COMMENTS com
                    ON c.OWNER = com.OWNER
                    AND c.TABLE_NAME = com.TABLE_NAME
                    AND c.COLUMN_NAME = com.COLUMN_NAME
                WHERE c.OWNER = :param1
            """
            if table_name:
                sql += " AND c.TABLE_NAME = :param2"
            return sql, db_schema, table_name

        elif ds_type == "redshift":
            sql = """
                SELECT a.attname AS COLUMN_NAME,
                       pg_catalog.format_type(a.atttypid, a.atttypmod) AS DATA_TYPE,
                       col_description(c.oid, a.attnum) AS COLUMN_COMMENT
                FROM pg_catalog.pg_attribute a
                JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                    AND a.attnum > 0
                    AND NOT a.attisdropped
            """
            if table_name:
                sql += " AND c.relname = %s"
            return sql, db_schema, table_name

        elif ds_type in ("doris", "starrocks"):
            sql = """
                SELECT COLUMN_NAME, DATA_TYPE, COLUMN_COMMENT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s
            """
            if table_name:
                sql += " AND TABLE_NAME = %s"
            return sql, database, table_name

        elif ds_type == "kingbase":
            sql = """
                SELECT a.attname AS COLUMN_NAME,
                       pg_catalog.format_type(a.atttypid, a.atttypmod) AS DATA_TYPE,
                       col_description(c.oid, a.attnum) AS COLUMN_COMMENT
                FROM pg_catalog.pg_attribute a
                JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = '{0}'
                    AND a.attnum > 0
                    AND NOT a.attisdropped
            """
            if table_name:
                sql += " AND c.relname = '{1}'"
            return sql, db_schema, table_name

        elif ds_type == "es":
            return "", None, None

        else:
            raise ValueError(f"不支持的数据源类型: {ds_type}")

    @staticmethod
    def get_fields(ds_type: str, config: Dict[str, Any], table_name: str) -> List[Dict[str, Any]]:
        """获取指定表的字段列表（名称/类型/注释）"""
        try:
            db = DB.get_db(ds_type)
            timeout = config.get("timeout", 30)
            extra_config = DatasourceConnectionUtil._get_extra_config(config)
            sql, p1, p2 = DatasourceConnectionUtil._get_field_sql(ds_type, config, table_name)

            fields = []

            if db.connect_type == ConnectType.sqlalchemy:
                # SQLAlchemy 驱动的数据库
                uri = DatasourceConnectionUtil.build_connection_uri(ds_type, config)
                if ds_type == "oracle":
                    engine = create_engine(uri, pool_pre_ping=True)
                elif ds_type == "sqlServer":
                    # SQL Server 2022 需要禁用加密以兼容 pymssql
                    # pymssql 不支持 connect_timeout，使用 login_timeout 和 timeout
                    engine = create_engine(
                        uri, pool_pre_ping=True, connect_args={"timeout": timeout, "login_timeout": timeout, "encryption": "off"}
                    )
                else:
                    engine = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": timeout})
                with engine.connect() as conn:
                    result = conn.execute(text(sql), {"param1": p1, "param2": p2})
                    for idx, row in enumerate(result.fetchall()):
                        # 处理 bytes 类型（SQL Server 可能返回 bytes）
                        def _decode_value(value):
                            if isinstance(value, bytes):
                                try:
                                    return value.decode('utf-8')
                                except UnicodeDecodeError:
                                    try:
                                        return value.decode('latin-1')
                                    except:
                                        return str(value)
                            return value or ""

                        fields.append({
                            "fieldName": _decode_value(row[0]),
                            "fieldType": _decode_value(row[1]),
                            "fieldComment": _decode_value(row[2]),
                            "fieldIndex": idx
                        })
            else:
                # Python 原生驱动的数据库
                host = config.get("host", "")
                port = config.get("port", 3306)
                username = config.get("username", "")
                password = config.get("password", "")
                database = config.get("database", "")

                if ds_type == "dm":
                    if dmPython is None:
                        raise Exception("未安装达梦数据库驱动 dmPython")
                    with dmPython.connect(user=username, password=password, server=host,
                                          port=port, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql, {"param1": p1, "param2": p2}, timeout=timeout)
                            for idx, row in enumerate(cursor.fetchall()):
                                fields.append({
                                    "fieldName": row[0],
                                    "fieldType": row[1] or "",
                                    "fieldComment": row[2] or "",
                                    "fieldIndex": idx
                                })

                elif ds_type in ("doris", "starrocks"):
                    # 使用优化的连接参数以提高连接稳定性
                    connect_timeout = max(timeout, 60)  # 至少 60 秒连接超时
                    with pymysql.connect(
                        user=username,
                        passwd=password,
                        host=host,
                        port=port,
                        db=database,
                        connect_timeout=connect_timeout,
                        read_timeout=timeout,
                        write_timeout=timeout,
                        charset='utf8mb4',
                        autocommit=True,
                        **extra_config
                    ) as conn:
                        with conn.cursor() as cursor:
                            params = (p1, p2) if p2 else (p1,)
                            cursor.execute(sql, params)
                            for idx, row in enumerate(cursor.fetchall()):
                                fields.append({
                                    "fieldName": row[0],
                                    "fieldType": row[1] or "",
                                    "fieldComment": row[2] or "",
                                    "fieldIndex": idx
                                })

                elif ds_type == "redshift":
                    if redshift_connector is None:
                        raise Exception("未安装 redshift_connector 驱动")
                    with redshift_connector.connect(host=host, port=port, database=database,
                                                    user=username, password=password,
                                                    timeout=timeout, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            params = (p1, p2) if p2 else (p1,)
                            cursor.execute(sql, params)
                            for idx, row in enumerate(cursor.fetchall()):
                                fields.append({
                                    "fieldName": row[0],
                                    "fieldType": row[1] or "",
                                    "fieldComment": row[2] or "",
                                    "fieldIndex": idx
                                })

                elif ds_type == "kingbase":
                    with psycopg2.connect(host=host, port=port, database=database,
                                          user=username, password=password,
                                          options=f"-c statement_timeout={timeout * 1000}",
                                          **extra_config) as conn:
                        with conn.cursor() as cursor:
                            formatted_sql = sql.format(p1, p2) if p2 else sql.format(p1)
                            cursor.execute(formatted_sql)
                            for idx, row in enumerate(cursor.fetchall()):
                                fields.append({
                                    "fieldName": row[0],
                                    "fieldType": row[1] or "",
                                    "fieldComment": row[2] or "",
                                    "fieldIndex": idx
                                })

                elif ds_type == "es":
                    # Elasticsearch：获取索引的字段
                    es_client = DatasourceConnectionUtil._get_es_connect(config)
                    mapping = es_client.indices.get_mapping(index=table_name)
                    properties = mapping.get(table_name, {}).get("mappings", {}).get("properties", {})
                    for idx, (field, field_config) in enumerate(properties.items()):
                        field_type = field_config.get("type", "")
                        desc = ""
                        if field_config.get("_meta"):
                            desc = field_config.get("_meta", {}).get('description', '')
                        if not field_type:
                            # object、nested 等类型
                            field_type = ','.join(list(field_config.keys()))
                        fields.append({
                            "fieldName": field,
                            "fieldType": field_type,
                            "fieldComment": desc,
                            "fieldIndex": idx
                        })

            return fields
        except Exception as e:
            logger.error(f"获取表 {table_name} 字段失败: {e}")
            raise

    @staticmethod
    def _process_row_value(value: Any) -> Any:
        """处理行数据中的值"""
        if isinstance(value, Decimal):
            return float(value)
        elif hasattr(value, "isoformat"):
            return value.isoformat()
        elif hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, bytes):
            return value.decode('utf-8', errors='ignore')
        return value

    @staticmethod
    def execute_query(ds_type: str, config: Dict[str, Any], sql: str) -> List[Dict[str, Any]]:
        """执行SQL查询并返回结果"""
        # 移除末尾的分号
        while sql.endswith(';'):
            sql = sql[:-1]

        try:
            db = DB.get_db(ds_type)
            timeout = config.get("timeout", 30)
            extra_config = DatasourceConnectionUtil._get_extra_config(config)

            if db.connect_type == ConnectType.sqlalchemy:
                # SQLAlchemy 驱动的数据库
                uri = DatasourceConnectionUtil.build_connection_uri(ds_type, config)
                if ds_type == "oracle":
                    engine = create_engine(uri, pool_pre_ping=True)
                elif ds_type == "sqlServer":
                    # SQL Server 2022 需要禁用加密以兼容 pymssql
                    # pymssql 不支持 connect_timeout，使用 login_timeout 和 timeout
                    engine = create_engine(
                        uri, pool_pre_ping=True, connect_args={"timeout": timeout, "login_timeout": timeout, "encryption": "off"}
                    )
                else:
                    engine = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": timeout})
                with engine.connect() as conn:
                    result = conn.execute(text(sql))
                    rows = result.fetchall()
                    columns = list(result.keys())
                    data = []
                    for row in rows:
                        row_dict = {}
                        for i, col in enumerate(columns):
                            row_dict[col] = DatasourceConnectionUtil._process_row_value(row[i])
                        data.append(row_dict)
                    return data
            else:
                # Python 原生驱动的数据库
                host = config.get("host", "")
                port = config.get("port", 3306)
                username = config.get("username", "")
                password = config.get("password", "")
                database = config.get("database", "")

                if ds_type == "dm":
                    if dmPython is None:
                        raise Exception("未安装达梦数据库驱动 dmPython")
                    with dmPython.connect(user=username, password=password, server=host,
                                          port=port, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql, timeout=timeout)
                            rows = cursor.fetchall()
                            columns = [field[0] for field in cursor.description]
                            data = []
                            for row in rows:
                                row_dict = {}
                                for i, col in enumerate(columns):
                                    row_dict[col] = DatasourceConnectionUtil._process_row_value(row[i])
                                data.append(row_dict)
                            return data

                elif ds_type in ("doris", "starrocks"):
                    # StarRocks/Doris 连接参数优化：
                    # 1. 增加 connect_timeout 到至少 60 秒（连接建立可能需要更长时间）
                    # 2. 添加 write_timeout 防止写入超时
                    # 3. 设置 charset 确保编码正确
                    # 4. 设置 autocommit 提高兼容性
                    connect_timeout = max(timeout, 60)  # 至少 60 秒连接超时
                    with pymysql.connect(
                        user=username,
                        passwd=password,
                        host=host,
                        port=port,
                        db=database,
                        connect_timeout=connect_timeout,
                        read_timeout=timeout,
                        write_timeout=timeout,
                        charset='utf8mb4',
                        autocommit=True,
                        **extra_config
                    ) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql)
                            rows = cursor.fetchall()
                            columns = [field[0] for field in cursor.description]
                            data = []
                            for row in rows:
                                row_dict = {}
                                for i, col in enumerate(columns):
                                    row_dict[col] = DatasourceConnectionUtil._process_row_value(row[i])
                                data.append(row_dict)
                            return data

                elif ds_type == "redshift":
                    if redshift_connector is None:
                        raise Exception("未安装 redshift_connector 驱动")
                    with redshift_connector.connect(host=host, port=port, database=database,
                                                    user=username, password=password,
                                                    timeout=timeout, **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql)
                            rows = cursor.fetchall()
                            columns = [field[0] for field in cursor.description]
                            data = []
                            for row in rows:
                                row_dict = {}
                                for i, col in enumerate(columns):
                                    row_dict[col] = DatasourceConnectionUtil._process_row_value(row[i])
                                data.append(row_dict)
                            return data

                elif ds_type == "kingbase":
                    with psycopg2.connect(host=host, port=port, database=database,
                                          user=username, password=password,
                                          options=f"-c statement_timeout={timeout * 1000}",
                                          **extra_config) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql)
                            rows = cursor.fetchall()
                            columns = [field[0] for field in cursor.description]
                            data = []
                            for row in rows:
                                row_dict = {}
                                for i, col in enumerate(columns):
                                    row_dict[col] = DatasourceConnectionUtil._process_row_value(row[i])
                                data.append(row_dict)
                            return data

                elif ds_type == "es":
                    # Elasticsearch：通过 SQL API 执行查询
                    host_url = config.get("host", "")
                    while host_url.endswith('/'):
                        host_url = host_url[:-1]
                    url = f'{host_url}/_sql?format=json'
                    response = requests.post(
                        url,
                        data=json.dumps({"query": sql}),
                        headers=DatasourceConnectionUtil._get_es_auth(config),
                        verify=False
                    )
                    res = response.json()
                    if res.get('error'):
                        raise Exception(json.dumps(res))
                    columns = [col.get('name') for col in res.get('columns', [])]
                    rows = res.get('rows', [])
                    data = []
                    for row in rows:
                        row_dict = {}
                        for i, col in enumerate(columns):
                            row_dict[col] = DatasourceConnectionUtil._process_row_value(row[i])
                        data.append(row_dict)
                    return data

                else:
                    raise Exception(f"不支持的数据源类型: {ds_type}")

        except Exception as e:
            logger.error(f"执行查询失败: {e}")
            raise


class DatasourceConfigUtil:
    """数据源配置工具类 - 加密/解密"""

    # 简单的加密密钥（生产环境应使用更安全的方式）
    KEY = b"AixDB12345678901"  # 16字节密钥

    @staticmethod
    def encrypt_config(config: Dict[str, Any]) -> str:
        """加密配置信息"""
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
            import base64

            config_str = json.dumps(config)
            cipher = AES.new(DatasourceConfigUtil.KEY, AES.MODE_ECB)
            padded_data = pad(config_str.encode("utf-8"), AES.block_size)
            encrypted = cipher.encrypt(padded_data)
            return base64.b64encode(encrypted).decode("utf-8")
        except ImportError:
            # 如果没有安装pycryptodome，使用简单的base64编码（不安全，仅用于开发）
            logger.warning("pycryptodome未安装，使用base64编码（不安全）")
            import base64

            config_str = json.dumps(config)
            return base64.b64encode(config_str.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error(f"加密配置失败: {e}")
            raise

    @staticmethod
    def decrypt_config(encrypted_config: str) -> Dict[str, Any]:
        """解密配置信息"""
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
            import base64

            encrypted_data = base64.b64decode(encrypted_config)
            cipher = AES.new(DatasourceConfigUtil.KEY, AES.MODE_ECB)
            decrypted = cipher.decrypt(encrypted_data)
            unpadded = unpad(decrypted, AES.block_size)
            return json.loads(unpadded.decode("utf-8"))
        except ImportError:
            # 如果没有安装pycryptodome，使用简单的base64解码
            logger.warning("pycryptodome未安装，使用base64解码")
            import base64

            config_str = base64.b64decode(encrypted_config).decode("utf-8")
            return json.loads(config_str)
        except Exception as e:
            logger.error(f"解密配置失败: {e}")
            raise
