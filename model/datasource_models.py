"""
数据源管理模型
"""
import datetime
from typing import Optional, List
from sqlalchemy import Column, BigInteger, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from model.db_connection_pool import Base


class Datasource(Base):
    """数据源表"""
    __tablename__ = "t_datasource"
    __table_args__ = {"comment": "数据源表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, comment="数据源名称")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="描述")
    type: Mapped[str] = mapped_column(Text, nullable=False, comment="数据源类型: mysql, postgresql, oracle, sqlserver等")
    type_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="类型名称")
    configuration: Mapped[str] = mapped_column(Text, nullable=False, comment="配置信息(加密)")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True, comment="创建时间")
    create_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="创建人ID")
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="状态: Success, Failed")
    num: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="表数量统计: selected/total")
    table_relation: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="表关系")


class DatasourceTable(Base):
    """数据源表信息"""
    __tablename__ = "t_datasource_table"
    __table_args__ = {"comment": "数据源表信息"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ds_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="数据源ID")
    checked: Mapped[bool] = mapped_column(default=True, comment="是否选中")
    table_name: Mapped[str] = mapped_column(Text, nullable=False, comment="表名")
    table_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="表注释")
    custom_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="自定义注释")
    # 表结构向量：基于“表名 + 注释 + 字段名 + 字段注释”的文本生成的 embedding，存为 JSON 数组字符串
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="表结构 embedding (JSON 数组字符串)")


class DatasourceField(Base):
    """数据源字段信息"""
    __tablename__ = "t_datasource_field"
    __table_args__ = {"comment": "数据源字段信息"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ds_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="数据源ID")
    table_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="表ID")
    checked: Mapped[bool] = mapped_column(default=True, comment="是否选中")
    field_name: Mapped[str] = mapped_column(Text, nullable=False, comment="字段名")
    field_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="字段类型")
    field_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="字段注释")
    custom_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="自定义注释")
    field_index: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="字段顺序")

