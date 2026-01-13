"""
基于sqlalchemy ORM框架数据库连接池
"""

import logging
import os
import traceback
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class DBConnectionPool:
    """
    数据库连接池 (单例模式)
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBConnectionPool, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        try:
            # 防止重复初始化
            if DBConnectionPool._initialized:
                return

            # 获取数据库连接URI，如果环境变量不存在则使用默认值
            database_uri = os.getenv("SQLALCHEMY_DATABASE_URI", "postgresql+psycopg2://aix_db:1@127.0.0.1:5432/aix_db")

            self.engine = create_engine(
                database_uri,
                pool_size=10,  # 连接池大小
                max_overflow=20,  # 连接池最大溢出大小
                pool_recycle=3600,  # 连接回收时间（秒），避免长时间连接失效
                pool_timeout=30,  # 连接池等待超时时间（秒）
                pool_pre_ping=True,  # 启用连接预检测，确保连接有效性
                echo=False,  # 是否打印SQL语句，用于调试
            )
            self.SessionLocal = sessionmaker(bind=self.engine)
            self.Base = Base
            DBConnectionPool._initialized = True

            logger.info("Database connection pool initialized.")
        except Exception as e:
            traceback.print_exception(e)
            logger.error(f"Error initializing database connection pool: {e}")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        获取数据库会话的上下文管理器
        用法:
        with db_pool.get_session() as session:
            # 使用session进行数据库操作
        """
        session: Session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            traceback.print_exception(e)
            session.rollback()
            raise
        finally:
            session.close()

    def get_engine(self):
        """
        获取数据库引擎
        :return: Engine
        """
        return self.engine

    def create_tables(self):
        """
        创建所有表
        """
        self.Base.metadata.create_all(self.engine)


# 提供全局访问点
def get_db_pool() -> DBConnectionPool:
    """
    获取数据库连接池实例
    :return: DBConnectionPool
    """
    return DBConnectionPool()
