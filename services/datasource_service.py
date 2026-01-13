"""
数据源管理服务
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from py2neo import Graph
from sqlalchemy import and_
from sqlalchemy.orm import Session

from model.datasource_models import Datasource, DatasourceTable, DatasourceField
from model.db_connection_pool import get_db_pool
from model.db_models import TAiModel
from langfuse.openai import OpenAI

logger = logging.getLogger(__name__)


class DatasourceService:
    """数据源服务类"""

    @staticmethod
    def get_datasource_list(session: Session, user_id: Optional[int] = None) -> List[Datasource]:
        """获取数据源列表"""
        query = session.query(Datasource)

        if user_id:
            query = query.filter(Datasource.create_by == user_id)
        return query.order_by(Datasource.create_time.desc()).all()

    @staticmethod
    def get_datasource_by_id(session: Session, ds_id: int) -> Optional[Datasource]:
        """根据ID获取数据源"""
        return session.query(Datasource).filter(Datasource.id == ds_id).first()

    @staticmethod
    def create_datasource(session: Session, data: Dict[str, Any], user_id: int) -> Datasource:
        """创建数据源"""
        from common.datasource_util import DatasourceConfigUtil
        import json

        # 如果配置是字典，需要加密
        configuration = data.get("configuration", "")
        if isinstance(configuration, dict):
            configuration = DatasourceConfigUtil.encrypt_config(configuration)
        elif isinstance(configuration, str):
            try:
                # 尝试解析JSON，如果是JSON字符串则加密
                config_dict = json.loads(configuration)
                configuration = DatasourceConfigUtil.encrypt_config(config_dict)
            except (json.JSONDecodeError, TypeError):
                # 已经是加密后的字符串，直接使用
                pass

        datasource = Datasource(
            name=data.get("name"),
            description=data.get("description", ""),
            type=data.get("type"),
            type_name=data.get("type_name", ""),
            configuration=configuration,
            create_time=datetime.now(),
            create_by=user_id,
            status="Success",
            num="0/0",
        )
        session.add(datasource)
        session.commit()
        session.refresh(datasource)

        # 保存表和字段信息
        tables = data.get("tables", [])
        if tables:
            DatasourceService._save_tables_and_fields(session, datasource, tables)
            session.commit()

        return datasource

    @staticmethod
    def _save_tables_and_fields(session: Session, datasource: Datasource, tables: List[Dict[str, Any]]):
        """保存/同步表和字段信息，自动更新计数"""
        from common.datasource_util import DatasourceConnectionUtil, DatasourceConfigUtil

        # 解密配置
        config = DatasourceConfigUtil.decrypt_config(datasource.configuration)

        # 记录处理过的表、字段 id
        keep_table_ids: List[int] = []
        # 用于批量 embedding 计算的 (table, fields) 列表
        embedding_items: List[Dict[str, Any]] = []

        # 获取源库总表数，用于 num 统计
        try:
            all_db_tables = DatasourceConnectionUtil.get_tables(datasource.type, config)
            total_count = len(all_db_tables)
        except Exception:
            total_count = len(tables)

        for table_info in tables:
            table_name = table_info.get("table_name") or table_info.get("tableName")
            table_comment = table_info.get("table_comment") or table_info.get("tableComment") or ""
            if not table_name:
                continue

            # 创建或更新表记录
            table = (
                session.query(DatasourceTable)
                .filter(DatasourceTable.ds_id == datasource.id, DatasourceTable.table_name == table_name)
                .first()
            )

            if not table:
                table = DatasourceTable(
                    ds_id=datasource.id,
                    checked=True,
                    table_name=table_name,
                    table_comment=table_comment,
                    custom_comment=table_comment,
                )
                session.add(table)
                session.flush()
                session.refresh(table)
            else:
                table.table_comment = table_comment
                table.custom_comment = table.custom_comment or table_comment
                table.checked = True

            keep_table_ids.append(table.id)

            # 同步字段
            try:
                fields = DatasourceConnectionUtil.get_fields(datasource.type, config, table_name)
            except Exception:
                fields = []

            keep_field_ids: List[int] = []
            for field in fields:
                field_name = field.get("fieldName")
                if not field_name:
                    continue
                field_comment = field.get("fieldComment") or ""
                field_type = field.get("fieldType") or ""
                field_index = field.get("fieldIndex") or 0

                record = (
                    session.query(DatasourceField)
                    .filter(and_(DatasourceField.table_id == table.id, DatasourceField.field_name == field_name))
                    .first()
                )

                if record:
                    record.field_comment = field_comment
                    record.field_type = field_type
                    record.field_index = field_index
                    if record.custom_comment is None:
                        record.custom_comment = field_comment
                else:
                    record = DatasourceField(
                        ds_id=datasource.id,
                        table_id=table.id,
                        checked=True,
                        field_name=field_name,
                        field_type=field_type,
                        field_comment=field_comment,
                        custom_comment=field_comment,
                        field_index=field_index,
                    )
                    session.add(record)
                    session.flush()
                    session.refresh(record)

                keep_field_ids.append(record.id)

            # 删除未包含的字段
            if keep_field_ids:
                session.query(DatasourceField).filter(
                    and_(DatasourceField.table_id == table.id, DatasourceField.id.not_in(keep_field_ids))
                ).delete(synchronize_session=False)

            # 收集用于 embedding 的字段精简信息，避免在批量计算时再次查询
            field_docs = [
                {
                    "fieldName": f.get("fieldName"),
                    "fieldComment": f.get("fieldComment") or "",
                }
                for f in fields
                if f.get("fieldName")
            ]
            embedding_items.append({"table": table, "fields": field_docs})

        # 删除未包含的表及其字段
        if keep_table_ids:
            session.query(DatasourceTable).filter(
                and_(DatasourceTable.ds_id == datasource.id, DatasourceTable.id.not_in(keep_table_ids))
            ).delete(synchronize_session=False)
            session.query(DatasourceField).filter(
                and_(DatasourceField.ds_id == datasource.id, DatasourceField.table_id.not_in(keep_table_ids))
            ).delete(synchronize_session=False)

        # 更新 num 统计
        datasource.num = f"{len(keep_table_ids)}/{total_count}"
        session.add(datasource)

        # 批量计算并保存表的 embedding（表名 + 注释 + 字段名 + 字段注释）
        try:
            DatasourceService._compute_and_save_table_embeddings_batch(session, embedding_items)
        except Exception as e:
            logger.warning(f"批量计算表 embedding 失败: {e}", exc_info=True)

    @staticmethod
    def _get_embedding_client():
        """获取 embedding 客户端和模型名称"""
        try:
            db_pool = get_db_pool()
            with db_pool.get_session() as session:
                # model_type: 2 -> Embedding
                model = session.query(TAiModel).filter(TAiModel.model_type == 2, TAiModel.default_model == True).first()
                
                if not model:
                    # Fallback: 尝试查找任何 embedding 模型
                    model = session.query(TAiModel).filter(TAiModel.model_type == 2).first()
                
                # Fallback to LLM
                if not model:
                    model = session.query(TAiModel).filter(
                        TAiModel.model_type == 1,
                        TAiModel.default_model == True
                    ).first()
                
                if not model:
                    model = session.query(TAiModel).filter(TAiModel.model_type == 1).first()
                
                if not model:
                    logger.warning("未配置嵌入模型，无法计算表 embedding")
                    return None, None
                
                base_model = model.base_model
                if model.model_type == 1 and model.supplier == 1:
                    base_model = "text-embedding-3-small"
                
                embedding_client = OpenAI(
                    api_key=model.api_key or "empty",
                    base_url=model.api_domain
                )
                return embedding_client, base_model
        except Exception as e:
            logger.error(f"获取 embedding 客户端失败: {e}", exc_info=True)
            return None, None

    @staticmethod
    def _build_table_document(table: DatasourceTable, fields: List[Dict[str, Any]]) -> str:
        """
        构建用于检索的文档文本（表名 + 注释 + 字段名 + 字段注释）。
        
        Args:
            table: 表对象
            fields: 字段列表
            
        Returns:
            文档文本
        """
        parts = [table.table_name]
        
        # 添加表注释（优先使用 custom_comment，否则使用 table_comment）
        table_comment = table.custom_comment or table.table_comment or ""
        if table_comment:
            parts.append(table_comment)
        
        # 添加字段名和字段注释
        for field in fields:
            field_name = field.get("fieldName") or field.get("field_name")
            if field_name:
                parts.append(field_name)
                field_comment = field.get("fieldComment") or field.get("field_comment") or ""
                if field_comment:
                    parts.append(field_comment)
        
        return " ".join(parts)

    @staticmethod
    def _compute_and_save_table_embedding(session: Session, table: DatasourceTable, fields: List[Dict[str, Any]]):
        """
        计算并保存表的 embedding。
        
        Args:
            session: 数据库会话
            table: 表对象
            fields: 字段列表
        """
        # 检查是否有 embedding 字段
        if not hasattr(table, 'embedding'):
            logger.debug(f"表 {table.table_name} 没有 embedding 字段，跳过计算")
            return
        
        # 获取 embedding 客户端
        embedding_client, model_name = DatasourceService._get_embedding_client()
        if not embedding_client or not model_name:
            return
        
        try:
            # 构建文档文本
            document = DatasourceService._build_table_document(table, fields)
            
            if not document or not document.strip():
                logger.warning(f"表 {table.table_name} 的文档文本为空，跳过 embedding 计算")
                return
            
            # 计算 embedding
            logger.info(f"计算表 {table.table_name} 的 embedding...")
            response = embedding_client.embeddings.create(model=model_name, input=document)
            embedding_vec = response.data[0].embedding
            
            # 将 embedding 转换为 JSON 字符串并保存
            embedding_json = json.dumps(embedding_vec)
            table.embedding = embedding_json
            
            logger.info(f"✅ 表 {table.table_name} 的 embedding 计算并保存成功")
            
        except Exception as e:
            logger.error(f"计算表 {table.table_name} 的 embedding 失败: {e}", exc_info=True)
            # 不抛出异常，避免影响表同步流程

    @staticmethod
    def _compute_and_save_table_embeddings_batch(session: Session, items: List[Dict[str, Any]]):
        """
        批量计算并保存多个表的 embedding，减少 API 调用次数。

        Args:
            session: 数据库会话
            items: 列表，每项包含 {"table": DatasourceTable, "fields": List[Dict]}
        """
        if not items:
            return

        # 统一检查是否支持 embedding 字段
        tables_for_embedding: List[DatasourceTable] = []
        docs: List[str] = []

        for item in items:
            table: DatasourceTable = item.get("table")
            fields: List[Dict[str, Any]] = item.get("fields") or []

            if not table or not hasattr(table, "embedding"):
                continue

            doc = DatasourceService._build_table_document(table, fields)
            if not doc or not doc.strip():
                continue

            tables_for_embedding.append(table)
            docs.append(doc)

        if not docs:
            return

        # 获取 embedding 客户端
        embedding_client, model_name = DatasourceService._get_embedding_client()
        if not embedding_client or not model_name:
            return

        try:
            logger.info(f"批量计算 {len(docs)} 个表的 embedding...")
            response = embedding_client.embeddings.create(model=model_name, input=docs)
            data = response.data or []

            if len(data) != len(tables_for_embedding):
                logger.warning(
                    f"批量 embedding 返回数量与请求数量不一致: 请求 {len(tables_for_embedding)}, 返回 {len(data)}"
                )

            for idx, table in enumerate(tables_for_embedding):
                if idx >= len(data):
                    break
                embedding_vec = data[idx].embedding
                embedding_json = json.dumps(embedding_vec)
                table.embedding = embedding_json

            logger.info("✅ 批量表 embedding 计算并保存成功")
        except Exception as e:
            logger.error(f"批量计算表 embedding 失败: {e}", exc_info=True)

    @staticmethod
    def update_datasource(session: Session, ds_id: int, data: Dict[str, Any]) -> Optional[Datasource]:
        """更新数据源"""
        datasource = session.query(Datasource).filter(Datasource.id == ds_id).first()
        if not datasource:
            return None

        if "name" in data:
            datasource.name = data["name"]
        if "description" in data:
            datasource.description = data["description"]
        if "configuration" in data:
            configuration = data["configuration"]
            if isinstance(configuration, dict):
                from common.datasource_util import DatasourceConfigUtil
                configuration = DatasourceConfigUtil.encrypt_config(configuration)
            elif isinstance(configuration, str):
                try:
                    from common.datasource_util import DatasourceConfigUtil
                    import json
                    config_dict = json.loads(configuration)
                    configuration = DatasourceConfigUtil.encrypt_config(config_dict)
                except (json.JSONDecodeError, TypeError):
                    pass
            datasource.configuration = configuration
        if "status" in data:
            datasource.status = data["status"]

        # 同步表/字段
        tables = data.get("tables")
        if tables is not None:
            DatasourceService._save_tables_and_fields(session, datasource, tables)

        session.commit()
        session.refresh(datasource)
        return datasource

    @staticmethod
    def sync_tables(session: Session, ds_id: int, tables: List[Dict[str, Any]]) -> bool:
        """根据传入的表列表同步表/字段数据"""
        datasource = session.query(Datasource).filter(Datasource.id == ds_id).first()
        if not datasource:
            return False
        DatasourceService._save_tables_and_fields(session, datasource, tables)
        session.commit()
        return True

    @staticmethod
    def get_fields_by_config(ds_type: str, config_str: str, table_name: str) -> List[Dict[str, Any]]:
        """根据配置直接获取某张表的字段"""
        from common.datasource_util import DatasourceConnectionUtil

        config = json.loads(config_str)
        return DatasourceConnectionUtil.get_fields(ds_type, config, table_name)

    @staticmethod
    def delete_datasource(session: Session, ds_id: int) -> bool:
        """删除数据源"""
        datasource = session.query(Datasource).filter(Datasource.id == ds_id).first()
        if not datasource:
            return False

        # 删除关联的表和字段
        session.query(DatasourceField).filter(DatasourceField.ds_id == ds_id).delete()
        session.query(DatasourceTable).filter(DatasourceTable.ds_id == ds_id).delete()
        session.delete(datasource)
        session.commit()
        return True

    @staticmethod
    def check_connection(ds: Datasource) -> (bool, str):
        """检查数据源连接"""
        try:
            from common.datasource_util import DatasourceConnectionUtil, DatasourceConfigUtil

            # 解密配置
            config = DatasourceConfigUtil.decrypt_config(ds.configuration)
            # 测试连接
            return DatasourceConnectionUtil.test_connection(ds.type, config)
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False, str(e)

    @staticmethod
    def check_connection_by_config(ds_type: str, config_str: str) -> (bool, str):
        """根据配置检查连接"""
        try:
            from common.datasource_util import DatasourceConnectionUtil
            import json

            config = json.loads(config_str)
            return DatasourceConnectionUtil.test_connection(ds_type, config)
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False, str(e)

    @staticmethod
    def get_tables_by_config(ds_type: str, config_str: str) -> List[Dict[str, Any]]:
        """根据配置获取表列表"""
        try:
            from common.datasource_util import DatasourceConnectionUtil
            import json

            config = json.loads(config_str)
            return DatasourceConnectionUtil.get_tables(ds_type, config)
        except Exception as e:
            logger.error(f"获取表列表失败: {e}")
            raise

    @staticmethod
    def get_tables_by_ds_id(session: Session, ds_id: int) -> List[DatasourceTable]:
        """获取数据源的所有表"""
        return session.query(DatasourceTable).filter(DatasourceTable.ds_id == ds_id).all()

    @staticmethod
    def get_fields_by_table_id(session: Session, table_id: int) -> List[DatasourceField]:
        """获取表的所有字段"""
        return session.query(DatasourceField).filter(DatasourceField.table_id == table_id).all()

    @staticmethod
    def save_table(session: Session, data: Dict[str, Any]) -> bool:
        """保存表信息"""
        table_id = data.get("id")
        if not table_id:
            return False

        table = session.query(DatasourceTable).filter(DatasourceTable.id == table_id).first()
        if not table:
            return False

        if "custom_comment" in data:
            table.custom_comment = data["custom_comment"]
        if "checked" in data:
            table.checked = data["checked"]

        # 如果表注释或字段信息发生变化，重新计算 embedding
        # 获取该表的所有字段
        fields = session.query(DatasourceField).filter(DatasourceField.table_id == table_id).all()
        fields_data = [
            {
                "fieldName": field.field_name,
                "fieldComment": field.custom_comment or field.field_comment or "",
            }
            for field in fields
        ]
        
        # 重新计算 embedding
        try:
            DatasourceService._compute_and_save_table_embedding(session, table, fields_data)
        except Exception as e:
            logger.warning(f"更新表 {table.table_name} 的 embedding 失败: {e}", exc_info=True)

        session.commit()
        return True

    @staticmethod
    def save_field(session: Session, data: Dict[str, Any]) -> bool:
        """保存字段信息"""
        field_id = data.get("id")
        if not field_id:
            return False

        field = session.query(DatasourceField).filter(DatasourceField.id == field_id).first()
        if not field:
            return False

        if "custom_comment" in data:
            field.custom_comment = data["custom_comment"]
        if "checked" in data:
            field.checked = data["checked"]

        # 如果字段信息发生变化，重新计算所属表的 embedding
        table = session.query(DatasourceTable).filter(DatasourceTable.id == field.table_id).first()
        if table:
            # 获取该表的所有字段
            fields = session.query(DatasourceField).filter(DatasourceField.table_id == field.table_id).all()
            fields_data = [
                {
                    "fieldName": f.field_name,
                    "fieldComment": f.custom_comment or f.field_comment or "",
                }
                for f in fields
            ]
            
            # 重新计算 embedding
            try:
                DatasourceService._compute_and_save_table_embedding(session, table, fields_data)
            except Exception as e:
                logger.warning(f"更新表 {table.table_name} 的 embedding 失败: {e}", exc_info=True)

        session.commit()
        return True

    @staticmethod
    def preview_table_data(
        session: Session, ds_id: int, table: Dict[str, Any], fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """预览表数据"""
        from common.datasource_util import DatasourceConnectionUtil, DatasourceConfigUtil

        # 获取数据源
        datasource = session.query(Datasource).filter(Datasource.id == ds_id).first()
        if not datasource:
            return {"data": [], "fields": []}

        # 解密配置
        config = DatasourceConfigUtil.decrypt_config(datasource.configuration)

        # 获取表名
        raw_table_name = table.get("table_name")
        if not raw_table_name:
            raw_table_name = table.get("tableName")
        table_name = raw_table_name or ""
        if not table_name:
            return {"data": [], "fields": []}

        # 构建带 schema 的表标识
        db_schema = config.get("dbSchema") or config.get("database") or ""
        if datasource.type in ["pg", "oracle", "sqlServer"] and db_schema:
            table_identifier = f"{db_schema}.{table_name}"
        else:
            table_identifier = table_name

        # 构建字段列表（只包含选中的字段）
        selected_fields = [f.get("field_name") or f.get("fieldName") for f in (fields or []) if f.get("checked", True)]
        selected_fields = [f for f in selected_fields if f]
        if not selected_fields:
            selected_fields = ["*"]

        # 构建 SQL
        fields_str = ", ".join(selected_fields) if selected_fields != ["*"] else "*"
        sql = f"SELECT {fields_str} FROM {table_identifier} LIMIT 100"

        try:
            # 执行查询
            result = DatasourceConnectionUtil.execute_query(datasource.type, config, sql)

            if not result:
                return {"data": [], "fields": []}

            # 转换为字典列表
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict):
                    data_list = result
                else:
                    # 如果是元组列表，转换为字典
                    field_names = (
                        selected_fields
                        if selected_fields != ["*"]
                        else list(result[0].keys()) if isinstance(result[0], dict) else []
                    )
                    data_list = [
                        dict(zip(field_names, row)) if isinstance(row, (list, tuple)) else row for row in result
                    ]
            else:
                data_list = []

            # 获取字段名
            if data_list and len(data_list) > 0:
                field_names = list(data_list[0].keys())
            else:
                field_names = selected_fields if selected_fields != ["*"] else []

            return {"data": data_list, "fields": field_names}
        except Exception as e:
            logger.error(f"预览数据失败: {e}")
            return {"data": [], "fields": [], "error": str(e)}

    @staticmethod
    def save_table_relation(session: Session, ds_id: int, relation_data: List[Dict[str, Any]]) -> bool:
        """保存表关系"""
        datasource = session.query(Datasource).filter(Datasource.id == ds_id).first()
        if not datasource:
            return False

        # 将关系数据保存为 JSON
        datasource.table_relation = relation_data
        session.commit()

        # 同步到 Neo4j（不阻断主流程）
        try:
            sync_table_relation_to_neo4j(relation_data)
        except Exception as e:
            logger.warning(f"同步表关系到 Neo4j 失败: {e}")
        return True

    @staticmethod
    def get_table_relation(session: Session, ds_id: int) -> Optional[List[Dict[str, Any]]]:
        """获取表关系"""
        datasource = session.query(Datasource).filter(Datasource.id == ds_id).first()
        if not datasource:
            return []

        return datasource.table_relation if datasource.table_relation else []

    @staticmethod
    def get_neo4j_relation(ds_id: int) -> List[Dict[str, Any]]:
        """
        从 Neo4j 获取数据源的表关系数据
        返回格式: [{"from_table": str, "to_table": str, "field_relation": str}, ...]
        """
        try:
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "neo4j123")

            graph = Graph(uri, auth=(user, password))

            # 首先获取该数据源的所有表名
            db_pool = get_db_pool()
            with db_pool.get_session() as session:
                tables = DatasourceService.get_tables_by_ds_id(session, ds_id)
                table_names = [table.table_name for table in tables]

            if not table_names:
                return []

            # 查询 Neo4j 中这些表之间的关系
            query = """
            MATCH (t1:Table)-[r:REFERENCES]->(t2:Table)
            WHERE t1.name IN $table_names AND t2.name IN $table_names
            RETURN 
              t1.name AS from_table,
              t2.name AS to_table,
              r.field_relation AS field_relation
            ORDER BY t1.name, t2.name
            """

            result = graph.run(query, table_names=table_names).data()
            return result if result else []
        except Exception as e:
            logger.error(f"获取 Neo4j 关系失败: {e}", exc_info=True)
            return []


def sync_table_relation_to_neo4j(relation_data: List[Dict[str, Any]]):
    """
    将前端保存的表关系同步到 Neo4j。
    节点：Table(name)
    关系：REFERENCES(field_relation=表.列=表.列)
    支持多关系，重复 MERGE。
    """
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j123")

    graph = Graph(uri, auth=(user, password))

    nodes = [r for r in relation_data if r.get("shape") != "edge"]
    edges = [r for r in relation_data if r.get("shape") == "edge"]

    # table id -> name
    table_map: Dict[str, str] = {}
    # table id -> port id -> field name
    port_map: Dict[str, Dict[str, str]] = {}

    for node in nodes:
        node_id = str(node.get("id"))
        label = (
            node.get("attrs", {}).get("label", {}).get("text")
            or node.get("label")
            or node.get("attrs", {}).get("text", {}).get("text")
        )
        if not label:
            continue
        table_map[node_id] = label

        ports = node.get("ports", {}).get("items", [])
        port_dict = {}
        for p in ports:
            pid = str(p.get("id"))
            pname = p.get("attrs", {}).get("portNameLabel", {}).get("text")
            if pid and pname:
                port_dict[pid] = pname
        port_map[node_id] = port_dict

    # 全量重建：先清理所有 REFERENCES，再重建，确保删除的表/边被移除
    graph.run("MATCH ()-[r:REFERENCES]->() DELETE r")

    # 创建表节点（若存在则忽略）
    for name in set(table_map.values()):
        graph.run("MERGE (:Table {name: $name, label: $name})", name=name)

    # 创建关系（多条 MERGE）
    for edge in edges:
        source_cell = str(edge.get("source", {}).get("cell"))
        target_cell = str(edge.get("target", {}).get("cell"))
        if not source_cell or not target_cell:
            continue
        source_table = table_map.get(source_cell)
        target_table = table_map.get(target_cell)
        if not source_table or not target_table:
            continue

        source_port = str(edge.get("source", {}).get("port"))
        target_port = str(edge.get("target", {}).get("port"))
        source_field = port_map.get(source_cell, {}).get(source_port, "")
        target_field = port_map.get(target_cell, {}).get(target_port, "")

        field_relation = ""
        if source_field and target_field:
            field_relation = f"{source_table}.{source_field}={target_table}.{target_field}"

        graph.run(
            """
            MATCH (s:Table {name: $source_table})
            MATCH (t:Table {name: $target_table})
            MERGE (s)-[r:REFERENCES {field_relation: $field_relation}]->(t)
            """,
            source_table=source_table,
            target_table=target_table,
            field_relation=field_relation,
        )
