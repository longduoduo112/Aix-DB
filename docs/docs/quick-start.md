确保上一步[环境配置](environment.md)已配置好


## 1. 启动服务
- 根据情况修改根目录下的**docker/docker-compose.yml**里**chat-service**服务的环境变量的值
    - **以下配置本机启动默认不用修改,在服务器上部署时host.docker.internal需修改为实际IP地址**
    - **1、非必需修改项**:
      - 可修改**MYSQL_HOST** MySQL数据服务地址
      - 可修改**SQLALCHEMY_DATABASE_URI** 数据库连接池地址
      - 可修改**MODEL_API_KEY** 大模型服务API-KEY
      - 可修改**MINIO_ENDPOINT** MinIO服务地址
      - 可修改**DIFY_SERVER_URL** Dify服务地址
      - 可修改**MODEL_NAME** 大模型名称如qwen-plus
      - 可修改**MODEL_BASE_URL** 公网大模型服务地址默认使用阿里云公网模型服务
      - 可修改**SHOW_THINKING_PROCESS** 是否显示大模型思考过程
      - 可修改**NEO4J_URI**  Neo4j数据库连接地址
      - 可修改**NEO4J_USER** Neo4j数据库用户名
      - 可修改**NEO4J_PASSWORD** Neo4j数据库密码
    - **2、必须修改项**:
      - **必须修改MINIO_ACCESS_KEY** MinIO服务Key
      - **必须修改MINIO_SECRET_KEY** MinIO服务密钥
      - **必须修改DIFY_DATABASE_QA_API_KEY** Dify智能体Api-Key
      - **必须修改MCP_HUB_COMMON_QA_GROUP_URL** 通用问答MCP-HUB工具集组地址
      - **必须修改MCP_HUB_DATABASE_QA_GROUP_URL** 数据问答MCP-HUB工具集组地址
  

- 根据情况修改**docker/docker-compose.yml里chat-web**前端**nginx.conf**配置文件
    - 服务器部署,请修改根目录下的**docker/nginx.conf**文件将**host.docker.internal**修改为实际IP地址
```angular2html
# 拉起前后端服务和中间件
cd docker
docker compose up -d
```

## 2. 数据初始化
- 如果使用已安装的mysql,初始化数据时需要修改源码initialize_mysql里面的链接信息
- 运行初始化脚本 ***如果执行脚本报错手动复制init_sql.sql到工具里面手动执行初始化***
```angular2html
# 安装依赖包
pip install pymysql
   
# Mac or Linux 用户执行
cd docker
./init_data.sh
   
# Windows 用户执行
cd common
python initialize_mysql.py
```
   
   
## 3. **访问服务**
- 前端服务：http://localhost:8081