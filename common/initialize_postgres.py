import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

"""
PostgreSQL 初始化脚本工具类
使用 SQLAlchemy 执行 SQL 文件
"""

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from model.db_connection_pool import get_db_pool

# 配置信息
SQL_FILE = os.path.join(project_root, "docker", "init_sql.sql")  # SQL 文件路径


def check_sql_file(file_path):
    """
    检查 SQL 文件是否存在
    :param file_path:
    :return:
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Error: SQL file {file_path} not found.")


def execute_sql_file(file_path):
    """
    使用 SQLAlchemy 执行 SQL 文件
    :param file_path:
    :return:
    """
    try:
        # 获取数据库连接池
        db_pool = get_db_pool()
        engine = db_pool.get_engine()

        print(f"Initializing PostgreSQL with {file_path}...")

        # 读取 SQL 文件
        with open(file_path, "r", encoding="utf-8") as file:
            sql_script = file.read()

        # 使用 SQLAlchemy 连接执行 SQL
        with engine.begin() as connection:
            # 分割 SQL 命令并执行 (PostgreSQL 使用分号分隔)
            commands = sql_script.split(";")
            for command in commands:
                command = command.strip()
                # 忽略空命令和注释
                if command and not command.startswith("--"):
                    try:
                        # 使用 text() 包装 SQL 语句
                        connection.execute(text(command))
                    except SQLAlchemyError as e:
                        # 某些命令可能已经存在（如 DROP TABLE IF EXISTS），继续执行
                        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                        if "does not exist" in error_msg or "already exists" in error_msg:
                            print(f"Warning: {error_msg}")
                            # 对于这些错误，继续执行下一条命令
                            continue
                        else:
                            print(f"Warning executing command: {error_msg}")
                            # 对于其他错误，也继续执行，但记录警告
                            continue

        print("PostgreSQL initialization completed successfully.")
    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    check_sql_file(SQL_FILE)
    execute_sql_file(SQL_FILE)
