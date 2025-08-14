from sqlalchemy.inspection import inspect

from model.db_connection_pool import get_db_pool

db_pool = get_db_pool()


class DatabaseService:
    """
    数据库服务类
    """

    def __init__(self):
        self.engine = db_pool.get_engine()

    def get_table_schema(self):
        """
        获取数据中所有表结构
        :return: 表结构
        """
        inspector = inspect(self.engine)
        table_info = {}

        for table_name in inspector.get_table_names():
            columns = {
                col["name"]: {"type": str(col["type"]), "comment": str(col["comment"])}
                for col in inspector.get_columns(table_name)
            }
            foreign_keys = [
                f"{fk['constrained_columns'][0]} -> {fk['referred_table']}.{fk['referred_columns'][0]}"
                for fk in inspector.get_foreign_keys(table_name)
            ]

            table_info[table_name] = {"columns": columns, "foreign_keys": foreign_keys}

        print(table_info)
