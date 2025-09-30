## 💡环境配置要求

在开始之前，请确保您的开发环境满足以下最低配置要求：

- **操作系统**：Windows 10/11, macOs M系列, Centos/Ubuntu
- **GPU**: 本地使用ollama部署，推荐使用Nvidia显卡或CPU模式。**推荐公网购买APIKEY形式**
- **内存**：8GB+

### 🔧 **前置条件**
* Python 3.11.x
* uv 0.8.0+
* Dify 0.7.1+
* Mysql 8.0+
* Node.js 18.12.x+
* Pnpm 9.x
* Mcp-Hub 0.9.0+
* Gpt-vis-api 0.0.1+

### 📚 **大模型选择**
- 推荐购买公网大模型[阿里云公网大模型服务APIKEY](http://aliyun.com/product/bailian)
- 模型要求: **Qwen3/Qwen-Plus/Deepseek** 模型


### 🧩 **Clone仓库**
```angular2html
git clone https://github.com/apconw/sanic-web.git
```

### 🌲 Mino
> 下面chat-service/gpt-vis-api服务都依赖Minio服务
#### 安装
```angular2html
cd docker
docker compose up -d minio
```

#### 配置
 - 访问MinIO服务，http://localhost:19001/ 账号:admin 密码:12345678
 - 创建两个个bucket，名称**filedata和chart-images** **同时配置Access Key保存好下面会使用**
 - 修改bucket的**chart-images**访问策略为**public**

 ![image](images/minio.png)
 ![image](images/minio-b.png)


### 🌳 **Dify**

#### 安装
- **安装Dify** [官方参考文档](https://docs.dify.ai/zh-hans)
- **如果已经安装过Dify环境，可跳过该步骤**
- 为了兼顾第一次接触大模型应用的同学，本项目提供了一键拉起Dify服务方便大家快速体验。
- Dify本机访问地址：http://localhost:18000 账号/密码: 需自己注册
```angular2html
# 拉起内置的dify服务
cd docker/dify/docker
docker-compose up -d
```
#### 配置
 - 购买[阿里云公网大模型服务APIKEY](http://aliyun.com/product/bailian)
 - 导入项目根目录下的**docker/docker/dify/数据问答_v1.1.6_qwen_plus.yml画布** 
 - 获取画布对应的**api-key**先复制出来下面步骤会使用
 - 导入画布后**大模型节点**需要手动选择一下当前你配置的大模型并保存
 - 画布**HTTP节点**地址修改,本地部署默认不用修改服务器上需修改为实际IP地址
    - **服务器上启动画布里面所有地方host.docker.internal需修改为实际IP地址**
 - 操作步骤如下图:
 ![image](images/llm-setting.png)
 ![image](images/import-convas.png)
 ![image](images/convas-api-key.png)


### 🌴 gpt-vis-api
  GPT-VIS-API 是一个轻量级图表生成服务，**旨在解决 antv/mcp-server-chart 在私有化部署方面的局限性**。该服务接收数据请求，生成图表图像，上传到 MinIO 对象存储，并返回带有效期的预签名访问链接。
- [GPT-VIS API](https://github.com/apconw/gpt-vis-api)

> mcp-server-chart是蚂蚁开源的MCP图表渲染工具支持以下图表

![image](images/antv-chart.png)

#### 配置
- 根据情况修改docker/docker-compose.yml里**gpt-vis-api**服务的环境变量的值
- **以下配置本机启动默认不用修改,在服务器上部署时host.docker.internal需修改为实际IP地址**
      - 可修改**MINIO_ENDPOINT** MinIO服务地址
      - **必须修改MINIO_ACCESS_KEY** MinIO服务访问密钥
      - **必须修改MINIO_SECRET_KEY** MinIO服务密钥
      - 可修改**MINIO_PUBLIC_DOMAIN** 图片访问域名

#### 启动
```angular2html
cd docker
docker compose up -d gpt-vis-api
```

#### 验证
```shell
curl -X POST http://localhost:3100/generate \
  -H "Content-Type: application/json" \
  -d '{
    "type": "line",
    "data": [
      {"time": "2025-05", "value": 512},
      {"time": "2025-06", "value": 1024}
    ]
  }'

响应示例：
{
  "url": "http://localhost:19000/gpt-vis/chart-123.png?Expires=XYZ"
}
```



### 🌵 mcp-hub
- [官方文档](https://github.com/samanhappy/mcphub)
> mcp-hub是一个开源的MCP聚合工具方便安装和管理MCP工具

#### 启动
```angular2html
cd docker

# 创建volume目录
mkdir -p ./volume/mcp-data

# 创建一个空的或默认的 mcp_settings.json 文件
touch ./volume/mcp-data/mcp_settings.json

# 启动容器
docker compose up -d mcphub
```
![image](images/mcp-hub-01.png)

#### 配置
- 登录http://localhost:3300/ admin/admin123
- **国内镜像配置**
    - Python 包仓库地址: https://mirrors.aliyun.com/pypi/simple
    - NPM 仓库地址: https://registry.npmmirror.com
![image](images/mcp-hub-02.png)

#### 工具
> 需要安装两个工具mcp-server-chart蚂蚁图表工具/12306火车票查询工具

- **mcp-server-chart**
    - **VIS_REQUEST_SERVER**环境变量配置默认为**gpt-vis-api**服务地址本
    - 本地启动不需要修改如果是服务器部署**host.docker.internal**需要修改为实际IP地址
    - 安装完成后创建一个工具组并复制访问地址先保存一下
    - 后面配置**MCP_HUB_DATABASE_QA_GROUP_URL**变量时从这里取值
```angular2html
npx -y -y @antv/mcp-server-chart

VIS_REQUEST_SERVER: http://host.docker.internal:3100/generate
```
- 安装工具
![image](images/antv-mcp.png)

- 创建组
![image](images/antv-group.png)

- 获取访问链接
![image](images/antv-group-url.png)


- **12306火车票查询工具**
    - 安装完成后创建一个工具组并复制访问地址先保存一下
    - 后面配置**MCP_HUB_COMMON_QA_GROUP_URL**变量时从这里取值
```angular2html
npx -y 12306-mcp
```
- 安装工具
![image](images/12306.png)

- 创建组
![image](images/12306-group.png)

- 获取访问链接
![image](images/12306-group-url.png)


### 🌿 Noe4j
> Noe4j是一个开源的图数据库，用于存储和查询关系数据。
> Noe4j的安装和配置请参考[官方文档](https://neo4j.com/docs/operations-manual/current/installation/)
#### 启动
```angular2html
cd docker
docker compose up -d neo4j-apoc
```
#### 配置
- 登录http://localhost:7474/browser/ neo4j/neo4j123

![image](images/eno4j-db.png)
