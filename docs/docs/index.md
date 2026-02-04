# 配置说明

> Aix-DB 系统配置指南



## 目录

- [配置说明](#配置说明)
  - [目录](#目录)
  - [系统设置](#系统设置)
    - [第一步：配置大模型](#第一步配置大模型)
    - [第二步：配置数据源](#第二步配置数据源)
    - [第三步：配置全链路监控（可选）](#第三步配置全链路监控可选)
      - [安装 Langfuse](#安装-langfuse)
      - [配置 Aix-DB](#配置-aix-db)
  - [下一步](#下一步)



## 系统设置

系统部署完成后，需要进行以下配置才能正常使用。

### 第一步：配置大模型

进入 **系统设置 → 模型配置**，添加您的大模型服务。

![大模型配置](./images/llm_setting.png)

**支持的模型类型：**

| 类型               | 必填  | 说明                                                           |
| ------------------ | :---: | -------------------------------------------------------------- |
| **大语言模型**     |   ✅   | 用于意图理解、SQL 生成、对话交互（如 Qwen、DeepSeek、MiniMax） |
| **Embedding 模型** |   ❌   | 用于文本向量化，支持 RAG 检索（如 text-embedding-v4）          |
| **Rerank 模型**    |   ❌   | 用于检索结果重排序，提升检索精度（如 gte-rerank-v2）           |

> **提示**：Embedding 和 Rerank 模型为可选配置，系统默认可正常运行。如需提升检索精度，可额外配置这两类模型。

**配置步骤：**

1. 点击右上角 **+ 添加模型**
2. 填写模型名称、选择模型类型
3. 输入基础模型名称（如 `qwen-flash`、`deepseek-chat`）
4. 配置 API 域名和密钥
5. 点击 **设为默认模型** 启用该模型



### 第二步：配置数据源

进入 **系统设置 → 库表配置**，添加您要查询的数据库。

![数据源配置](./images/datasource_setting.png)

**支持的数据源：**

| 数据库       | 说明                 |
| ------------ | -------------------- |
| MySQL        | 主流关系型数据库     |
| PostgreSQL   | 功能强大的开源数据库 |
| Oracle       | 企业级数据库         |
| SQL Server   | 微软企业级数据库     |
| ClickHouse   | 列式存储分析数据库   |
| StarRocks    | 高性能分析数据库     |
| Apache Doris | 实时分析数据库       |
| 达梦 DM      | 国产数据库           |

**配置步骤：**

1. 点击右上角 **+ 新建数据源**
2. 选择数据库类型
3. 填写连接信息：
   - 主机地址（如 `host.docker.internal`）
   - 端口号
   - 数据库名称
   - 用户名和密码
4. 点击 **测试连接** 验证配置
5. 保存后系统会自动同步表结构



### 第三步：配置全链路监控（可选）

Aix-DB 支持 [Langfuse](https://langfuse.com/) 进行 LLM 调用的全链路监控和追踪。

#### 安装 Langfuse

```bash
# 克隆 Langfuse 仓库
git clone https://github.com/langfuse/langfuse.git
cd langfuse

# 启动 Langfuse 服务
docker compose up
```

启动后访问 `http://localhost:3000` 创建项目并获取 API 密钥。

#### 配置 Aix-DB

**本地开发环境**

编辑项目根目录下的 `.env.dev` 文件，添加以下配置：

```bash
# Langfuse 配置（可选）
LANGFUSE_TRACING_ENABLED=true
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_BASE_URL=http://localhost:3000
```

**Docker 容器部署**

如果使用 `docker run` 命令部署，添加以下环境变量：

```bash
docker run -d \
  ...
  -e LANGFUSE_TRACING_ENABLED=true \
  -e LANGFUSE_SECRET_KEY=your_secret_key \
  -e LANGFUSE_PUBLIC_KEY=your_public_key \
  -e LANGFUSE_BASE_URL=http://host.docker.internal:3000 \
  ...
```

如果使用 `docker-compose` 部署，在 `docker-compose.yaml` 的 `environment` 中配置：

```yaml
environment:
  LANGFUSE_TRACING_ENABLED: true
  LANGFUSE_SECRET_KEY: your_secret_key
  LANGFUSE_PUBLIC_KEY: your_public_key
  LANGFUSE_BASE_URL: http://host.docker.internal:3000
```

> **注意**：在 Docker 环境中访问宿主机的 Langfuse 服务时，请使用 `host.docker.internal` 代替 `localhost`。

| 配置项                     | 说明                                            |
| -------------------------- | ----------------------------------------------- |
| `LANGFUSE_TRACING_ENABLED` | 是否启用追踪，设为 `true` 开启                  |
| `LANGFUSE_SECRET_KEY`      | Langfuse 项目的 Secret Key                      |
| `LANGFUSE_PUBLIC_KEY`      | Langfuse 项目的 Public Key                      |
| `LANGFUSE_BASE_URL`        | Langfuse 服务地址（如 `http://localhost:3000`） |

> **提示**：启用后可在 Langfuse 控制台查看 LLM 调用链路、Token 消耗、响应时间等监控数据。


## 下一步

配置完成后，您可以：

1. 进入 **数据问答** 页面，开始使用自然语言查询数据
2. 在 **术语配置** 中添加业务术语，提升查询准确率
3. 在 **SQL 示例** 中添加常用查询模板
