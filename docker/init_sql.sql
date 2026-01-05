-- PostgreSQL 初始化脚本
-- 只包含核心业务表：t_datasource, t_datasource_field, t_datasource_table, t_user, t_user_qa_record

-- 创建数据库（如果不存在）
-- 注意：PostgreSQL 中需要先连接到 postgres 数据库才能创建新数据库
-- CREATE DATABASE chat_db;

-- t_datasource definition
DROP TABLE IF EXISTS t_datasource CASCADE;
CREATE TABLE t_datasource (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  type TEXT NOT NULL,
  type_name TEXT,
  configuration TEXT NOT NULL,
  create_time TIMESTAMP,
  create_by BIGINT,
  status TEXT,
  num TEXT,
  table_relation JSONB
);

COMMENT ON TABLE t_datasource IS '数据源表';
COMMENT ON COLUMN t_datasource.name IS '数据源名称';
COMMENT ON COLUMN t_datasource.description IS '描述';
COMMENT ON COLUMN t_datasource.type IS '数据源类型: mysql, postgresql, oracle, sqlserver等';
COMMENT ON COLUMN t_datasource.type_name IS '类型名称';
COMMENT ON COLUMN t_datasource.configuration IS '配置信息(加密)';
COMMENT ON COLUMN t_datasource.create_time IS '创建时间';
COMMENT ON COLUMN t_datasource.create_by IS '创建人ID';
COMMENT ON COLUMN t_datasource.status IS '状态: Success, Failed';
COMMENT ON COLUMN t_datasource.num IS '表数量统计: selected/total';
COMMENT ON COLUMN t_datasource.table_relation IS '表关系';

-- t_datasource_table definition
DROP TABLE IF EXISTS t_datasource_table CASCADE;
CREATE TABLE t_datasource_table (
  id BIGSERIAL PRIMARY KEY,
  ds_id BIGINT NOT NULL,
  checked BOOLEAN DEFAULT TRUE,
  table_name TEXT NOT NULL,
  table_comment TEXT,
  custom_comment TEXT
);

COMMENT ON TABLE t_datasource_table IS '数据源表信息';
COMMENT ON COLUMN t_datasource_table.ds_id IS '数据源ID';
COMMENT ON COLUMN t_datasource_table.checked IS '是否选中';
COMMENT ON COLUMN t_datasource_table.table_name IS '表名';
COMMENT ON COLUMN t_datasource_table.table_comment IS '表注释';
COMMENT ON COLUMN t_datasource_table.custom_comment IS '自定义注释';

-- t_datasource_field definition
DROP TABLE IF EXISTS t_datasource_field CASCADE;
CREATE TABLE t_datasource_field (
  id BIGSERIAL PRIMARY KEY,
  ds_id BIGINT NOT NULL,
  table_id BIGINT NOT NULL,
  checked BOOLEAN DEFAULT TRUE,
  field_name TEXT NOT NULL,
  field_type TEXT,
  field_comment TEXT,
  custom_comment TEXT,
  field_index BIGINT
);

COMMENT ON TABLE t_datasource_field IS '数据源字段信息';
COMMENT ON COLUMN t_datasource_field.ds_id IS '数据源ID';
COMMENT ON COLUMN t_datasource_field.table_id IS '表ID';
COMMENT ON COLUMN t_datasource_field.checked IS '是否选中';
COMMENT ON COLUMN t_datasource_field.field_name IS '字段名';
COMMENT ON COLUMN t_datasource_field.field_type IS '字段类型';
COMMENT ON COLUMN t_datasource_field.field_comment IS '字段注释';
COMMENT ON COLUMN t_datasource_field.custom_comment IS '自定义注释';
COMMENT ON COLUMN t_datasource_field.field_index IS '字段顺序';

-- t_user definition
DROP TABLE IF EXISTS t_user CASCADE;
CREATE TABLE t_user (
  id SERIAL PRIMARY KEY,
  "userName" VARCHAR(200),
  password VARCHAR(300),
  mobile VARCHAR(100),
  "createTime" TIMESTAMP,
  "updateTime" TIMESTAMP
);

COMMENT ON COLUMN t_user."userName" IS '用户名称';
COMMENT ON COLUMN t_user.password IS '密码';
COMMENT ON COLUMN t_user.mobile IS '手机号';
COMMENT ON COLUMN t_user."createTime" IS '创建时间';
COMMENT ON COLUMN t_user."updateTime" IS '修改时间';

INSERT INTO t_user (id, "userName", password, mobile, "createTime", "updateTime")
VALUES (1, 'admin', '123456', NULL, '2024-01-15 15:30:00', '2024-01-15 15:30:00');

-- t_user_qa_record definition
DROP TABLE IF EXISTS t_user_qa_record CASCADE;
CREATE TABLE t_user_qa_record (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER,
  uuid VARCHAR(200),
  conversation_id VARCHAR(100),
  message_id VARCHAR(100),
  task_id VARCHAR(100),
  chat_id VARCHAR(100),
  question TEXT,
  to2_answer TEXT,
  to4_answer TEXT,
  qa_type VARCHAR(100),
  file_key TEXT,
  create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE t_user_qa_record IS '问答记录表';
COMMENT ON COLUMN t_user_qa_record.user_id IS '用户id';
COMMENT ON COLUMN t_user_qa_record.uuid IS '自定义id';
COMMENT ON COLUMN t_user_qa_record.conversation_id IS 'diy/对话id';
COMMENT ON COLUMN t_user_qa_record.message_id IS 'dify/消息id';
COMMENT ON COLUMN t_user_qa_record.task_id IS 'dify/任务id';
COMMENT ON COLUMN t_user_qa_record.chat_id IS '对话id';
COMMENT ON COLUMN t_user_qa_record.question IS '用户问题';
COMMENT ON COLUMN t_user_qa_record.to2_answer IS '大模型答案';
COMMENT ON COLUMN t_user_qa_record.to4_answer IS '业务数据';
COMMENT ON COLUMN t_user_qa_record.qa_type IS '问答类型';
COMMENT ON COLUMN t_user_qa_record.file_key IS '文件minio/key';
COMMENT ON COLUMN t_user_qa_record.create_time IS '创建时间';
