import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Integer,
    String,
    TIMESTAMP,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from model.db_connection_pool import Base

"""
读取数据生成ORM数据库实体Bean
sqlacodegen postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/chat_db --outfile=models.py
"""


class TUser(Base):
    __tablename__ = "t_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userName: Mapped[Optional[str]] = mapped_column(String(200), comment="用户名称")
    password: Mapped[Optional[str]] = mapped_column(String(300), comment="密码")
    mobile: Mapped[Optional[str]] = mapped_column(String(100), comment="手机号")
    role: Mapped[Optional[str]] = mapped_column(String(20), default="user", comment="角色: admin/user")
    createTime: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP, comment="创建时间")
    updateTime: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP, comment="修改时间")


class TUserQaRecord(Base):
    __tablename__ = "t_user_qa_record"
    __table_args__ = {"comment": "问答记录表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, comment="用户id")
    uuid: Mapped[Optional[str]] = mapped_column(String(200), comment="自定义id")
    conversation_id: Mapped[Optional[str]] = mapped_column(String(100), comment="对话id")
    message_id: Mapped[Optional[str]] = mapped_column(String(100), comment="消息id")
    task_id: Mapped[Optional[str]] = mapped_column(String(100), comment="任务id")
    chat_id: Mapped[Optional[str]] = mapped_column(String(100), comment="对话id")
    question: Mapped[Optional[str]] = mapped_column(Text, comment="用户问题")
    to2_answer: Mapped[Optional[str]] = mapped_column(Text, comment="大模型答案")
    to4_answer: Mapped[Optional[str]] = mapped_column(Text, comment="业务数据")
    qa_type: Mapped[Optional[str]] = mapped_column(String(100), comment="问答类型")
    datasource_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="数据源ID")
    file_key: Mapped[Optional[str]] = mapped_column(String(100), comment="文件minio/key")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class TAiModel(Base):
    __tablename__ = "t_ai_model"
    __table_args__ = {"comment": "AI模型表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    supplier: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="供应商: 1:OpenAI, 2:Azure, 3:Ollama, 4:vLLM, 5:DeepSeek, 6:Qwen, 7:Moonshot, 8:ZhipuAI, 9:Other",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="模型名称")
    model_type: Mapped[int] = mapped_column(Integer, nullable=False, comment="模型类型: 1:LLM, 2:Embedding, 3:Rerank")
    base_model: Mapped[str] = mapped_column(String(255), nullable=False, comment="基础模型")
    default_model: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否默认")
    api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="API Key")
    api_domain: Mapped[str] = mapped_column(String(255), nullable=False, comment="API Domain")
    protocol: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="协议: 1:OpenAI, 2:Ollama")
    config: Mapped[Optional[str]] = mapped_column(Text, comment="配置JSON")
    status: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="状态: 1:正常")
    create_time: Mapped[int] = mapped_column(BigInteger, default=0, comment="创建时间")
