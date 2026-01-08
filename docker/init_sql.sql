-- PostgreSQL 初始化脚本
-- 只包含核心业务表：t_datasource, t_datasource_field, t_datasource_table, t_user, t_user_qa_record

-- 创建数据库（如果不存在）
-- 注意：PostgreSQL 中需要先连接到 postgres 数据库才能创建新数据库
-- CREATE DATABASE chat_db;

-- 启用向量扩展（只需一次）
CREATE EXTENSION IF NOT EXISTS vector;

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
VALUES (1, 'admin', '$2b$12$rmnFss1KlnSgcRKCv/Q8e.cSeK2OpV9qPg.7TFc7QyCAxdJEnEfDK', NULL, '2024-01-15 15:30:00', '2024-01-15 15:30:00');

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
  datasource_id BIGINT,
  file_key TEXT,
  create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE t_user_qa_record IS '问答记录表';
COMMENT ON COLUMN t_user_qa_record.user_id IS '用户id';
COMMENT ON COLUMN t_user_qa_record.uuid IS '自定义id';
COMMENT ON COLUMN t_user_qa_record.conversation_id IS '对话id';
COMMENT ON COLUMN t_user_qa_record.message_id IS '消息id';
COMMENT ON COLUMN t_user_qa_record.task_id IS '任务id';
COMMENT ON COLUMN t_user_qa_record.chat_id IS '对话id';
COMMENT ON COLUMN t_user_qa_record.question IS '用户问题';
COMMENT ON COLUMN t_user_qa_record.to2_answer IS '大模型答案';
COMMENT ON COLUMN t_user_qa_record.to4_answer IS '业务数据';
COMMENT ON COLUMN t_user_qa_record.qa_type IS '问答类型';
COMMENT ON COLUMN t_user_qa_record.datasource_id IS '数据源ID';
COMMENT ON COLUMN t_user_qa_record.file_key IS '文件minio/key';
COMMENT ON COLUMN t_user_qa_record.create_time IS '创建时间';

-- t_ai_model definition
DROP TABLE IF EXISTS t_ai_model CASCADE;
CREATE TABLE t_ai_model (
  id BIGSERIAL PRIMARY KEY,
  supplier INTEGER NOT NULL,
  name VARCHAR(255) NOT NULL,
  model_type INTEGER NOT NULL,
  base_model VARCHAR(255) NOT NULL,
  default_model BOOLEAN DEFAULT FALSE NOT NULL,
  api_key VARCHAR(255),
  api_domain VARCHAR(255) NOT NULL,
  protocol INTEGER DEFAULT 1 NOT NULL,
  config TEXT,
  status INTEGER DEFAULT 1 NOT NULL,
  create_time BIGINT DEFAULT 0
);

COMMENT ON TABLE t_ai_model IS 'AI模型配置表';
COMMENT ON COLUMN t_ai_model.supplier IS '供应商: 1:OpenAI, 2:Azure, 3:Ollama, 4:vLLM, 5:DeepSeek, 6:Qwen, 7:Moonshot, 8:ZhipuAI, 9:Other';
COMMENT ON COLUMN t_ai_model.name IS '模型名称';
COMMENT ON COLUMN t_ai_model.model_type IS '模型类型: 1:LLM, 2:Embedding, 3:Rerank';
COMMENT ON COLUMN t_ai_model.base_model IS '基础模型';
COMMENT ON COLUMN t_ai_model.default_model IS '是否默认';
COMMENT ON COLUMN t_ai_model.api_key IS 'API Key';
COMMENT ON COLUMN t_ai_model.api_domain IS 'API Domain';
COMMENT ON COLUMN t_ai_model.protocol IS '协议: 1:OpenAI, 2:Ollama';
COMMENT ON COLUMN t_ai_model.config IS '配置JSON';
COMMENT ON COLUMN t_ai_model.status IS '状态: 1:正常';
COMMENT ON COLUMN t_ai_model.create_time IS '创建时间';

-- t_ds_rules definition
DROP TABLE IF EXISTS t_ds_rules CASCADE;
CREATE TABLE t_ds_rules (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  description VARCHAR(512),
  permission_list TEXT,
  user_list TEXT,
  white_list_user TEXT,
  enable BOOLEAN DEFAULT TRUE,
  create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  oid BIGINT
);

COMMENT ON TABLE t_ds_rules IS '权限规则组';
COMMENT ON COLUMN t_ds_rules.name IS '规则名称';
COMMENT ON COLUMN t_ds_rules.permission_list IS '权限ID列表(JSON)';
COMMENT ON COLUMN t_ds_rules.user_list IS '用户ID列表(JSON)';
COMMENT ON COLUMN t_ds_rules.enable IS '是否启用';

-- t_ds_permission definition
DROP TABLE IF EXISTS t_ds_permission CASCADE;
CREATE TABLE t_ds_permission (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(128),
  type VARCHAR(64) NOT NULL,
  ds_id BIGINT,
  table_id BIGINT,
  expression_tree TEXT,
  permissions TEXT,
  white_list_user TEXT,
  enable BOOLEAN DEFAULT TRUE,
  create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  auth_target_type VARCHAR(128),
  auth_target_id BIGINT
);

COMMENT ON TABLE t_ds_permission IS '数据权限详情';
COMMENT ON COLUMN t_ds_permission.type IS '权限类型: row, column';
COMMENT ON COLUMN t_ds_permission.expression_tree IS '行权限表达式树(JSON)';
COMMENT ON COLUMN t_ds_permission.permissions IS '列权限配置(JSON)';


CREATE TABLE IF NOT EXISTS t_terminology (
    id BIGSERIAL PRIMARY KEY,
    oid BIGINT DEFAULT 1,
    pid BIGINT,
    word VARCHAR(255),
    description TEXT,
    specific_ds BOOLEAN DEFAULT FALSE,
    datasource_ids TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE t_terminology IS '术语配置表';
COMMENT ON COLUMN t_terminology.oid IS '组织ID';
COMMENT ON COLUMN t_terminology.pid IS '父ID';
COMMENT ON COLUMN t_terminology.word IS '术语名称';
COMMENT ON COLUMN t_terminology.description IS '描述';
COMMENT ON COLUMN t_terminology.specific_ds IS '是否指定数据源';
COMMENT ON COLUMN t_terminology.datasource_ids IS '数据源ID列表(JSON)';
COMMENT ON COLUMN t_terminology.enabled IS '是否启用';
COMMENT ON COLUMN t_terminology.create_time IS '创建时间';

DROP TABLE IF EXISTS t_data_training CASCADE;
CREATE TABLE t_data_training (
  id BIGSERIAL PRIMARY KEY,
  oid BIGINT DEFAULT 1,
  datasource BIGINT,
  create_time TIMESTAMP,
  question VARCHAR(255),
  description TEXT,
  embedding VECTOR,
  enabled BOOLEAN DEFAULT TRUE,
  advanced_application BIGINT
);

COMMENT ON TABLE t_data_training IS '数据训练表';
COMMENT ON COLUMN t_data_training.oid IS '组织ID';
COMMENT ON COLUMN t_data_training.datasource IS '数据源ID';
COMMENT ON COLUMN t_data_training.create_time IS '创建时间';
COMMENT ON COLUMN t_data_training.question IS '问题描述';
COMMENT ON COLUMN t_data_training.description IS '示例SQL';
COMMENT ON COLUMN t_data_training.embedding IS '向量数据';
COMMENT ON COLUMN t_data_training.enabled IS '是否启用';
COMMENT ON COLUMN t_data_training.advanced_application IS '高级应用ID';
