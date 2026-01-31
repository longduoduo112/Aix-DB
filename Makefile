# AIX-DB 镜像构建配置
# 包含：基础镜像 + 应用镜像

# ============ 版本配置 ============

# 项目名称和应用版本
PROJECT_NAME = aix-db
VERSION = 1.2.2

# 基础镜像版本（依赖变更时更新此版本号）
BASE_VERSION = 1.0.0

# ============ 镜像名称配置 ============

# Docker Hub 镜像
DOCKER_IMAGE = apconw/$(PROJECT_NAME):$(VERSION)
BASE_IMAGE = apconw/$(PROJECT_NAME)-base:$(BASE_VERSION)
BASE_IMAGE_LATEST = apconw/$(PROJECT_NAME)-base:latest

# 阿里云镜像仓库
ALIYUN_REGISTRY = crpi-7xkxsdc0iki61l0q.cn-hangzhou.personal.cr.aliyuncs.com
ALIYUN_NAMESPACE = apconw
ALIYUN_IMAGE = $(ALIYUN_REGISTRY)/$(ALIYUN_NAMESPACE)/$(PROJECT_NAME):$(VERSION)
ALIYUN_BASE_IMAGE = $(ALIYUN_REGISTRY)/$(ALIYUN_NAMESPACE)/$(PROJECT_NAME)-base:$(BASE_VERSION)
ALIYUN_BASE_IMAGE_LATEST = $(ALIYUN_REGISTRY)/$(ALIYUN_NAMESPACE)/$(PROJECT_NAME)-base:latest

# Dockerfile 路径
DOCKERFILE = ./docker/Dockerfile
DOCKERFILE_BASE = ./docker/Dockerfile.base

# ============ 基础镜像构建（依赖变更时执行） ============

# 构建基础镜像（本地，当前架构）
# 使用场景：pyproject.toml、uv.lock、package.json、pnpm-lock.yaml 变更时
build-base:
	@echo "🔨 构建基础镜像 $(BASE_IMAGE)..."
	docker build --no-cache -t $(BASE_IMAGE) -t $(BASE_IMAGE_LATEST) -f $(DOCKERFILE_BASE) .
	@echo "✅ 基础镜像构建完成"

# 构建基础镜像（使用缓存）
build-base-cache:
	@echo "🔨 构建基础镜像 $(BASE_IMAGE)（使用缓存）..."
	docker build -t $(BASE_IMAGE) -t $(BASE_IMAGE_LATEST) -f $(DOCKERFILE_BASE) .
	@echo "✅ 基础镜像构建完成"

# 推送基础镜像至 Docker Hub（多架构）
push-base:
	@echo "📤 推送基础镜像至 Docker Hub..."
	docker buildx build --platform linux/amd64,linux/arm64 --push \
		-t $(BASE_IMAGE) \
		-t $(BASE_IMAGE_LATEST) \
		-f $(DOCKERFILE_BASE) .
	@echo "✅ 基础镜像推送完成"

# 推送基础镜像至阿里云（多架构）
push-base-aliyun:
	@echo "📤 推送基础镜像至阿里云..."
	docker buildx build --platform linux/amd64,linux/arm64 --push \
		-t $(ALIYUN_BASE_IMAGE) \
		-t $(ALIYUN_BASE_IMAGE_LATEST) \
		-f $(DOCKERFILE_BASE) .
	@echo "✅ 基础镜像推送完成"

# 推送基础镜像至所有仓库
push-base-all:
	@echo "📤 推送基础镜像至所有仓库..."
	docker buildx build --platform linux/amd64,linux/arm64 --push \
		-t $(BASE_IMAGE) \
		-t $(BASE_IMAGE_LATEST) \
		-t $(ALIYUN_BASE_IMAGE) \
		-t $(ALIYUN_BASE_IMAGE_LATEST) \
		-f $(DOCKERFILE_BASE) .
	@echo "✅ 基础镜像推送完成"

# ============ 应用镜像构建（日常发版使用） ============

# 快速构建应用镜像（基于基础镜像，仅复制源码）
# 构建时间：~30秒
build:
	@echo "🚀 快速构建应用镜像 $(DOCKER_IMAGE)..."
	docker build -t $(DOCKER_IMAGE) \
		--build-arg BASE_IMAGE=$(BASE_IMAGE_LATEST) \
		-f $(DOCKERFILE) .
	@echo "✅ 应用镜像构建完成"

# 构建应用镜像（指定基础镜像版本）
build-with-base-version:
	@echo "🚀 构建应用镜像（基础镜像: $(BASE_IMAGE)）..."
	docker build -t $(DOCKER_IMAGE) \
		--build-arg BASE_IMAGE=$(BASE_IMAGE) \
		-f $(DOCKERFILE) .
	@echo "✅ 应用镜像构建完成"

# ============ 多架构构建并推送（应用镜像） ============

# 构建多架构镜像并推送至 Docker Hub
push-dockerhub:
	@echo "📤 推送应用镜像至 Docker Hub..."
	docker buildx build --platform linux/amd64,linux/arm64 --push \
		--build-arg BASE_IMAGE=$(BASE_IMAGE_LATEST) \
		-t $(DOCKER_IMAGE) \
		-f $(DOCKERFILE) .
	@echo "✅ 应用镜像推送完成"

# 构建多架构镜像并推送至阿里云
push-aliyun:
	@echo "📤 推送应用镜像至阿里云..."
	docker buildx build --platform linux/amd64,linux/arm64 --push \
		--build-arg BASE_IMAGE=$(ALIYUN_BASE_IMAGE_LATEST) \
		-t $(ALIYUN_IMAGE) \
		-f $(DOCKERFILE) .
	@echo "✅ 应用镜像推送完成"

# 同时推送至 Docker Hub 和阿里云
push-all:
	@echo "📤 推送应用镜像至所有仓库..."
	docker buildx build --platform linux/amd64,linux/arm64 --push \
		--build-arg BASE_IMAGE=$(BASE_IMAGE_LATEST) \
		-t $(DOCKER_IMAGE) \
		-t $(ALIYUN_IMAGE) \
		-f $(DOCKERFILE) .
	@echo "✅ 应用镜像推送完成"

# ============ Docker Compose 操作 ============

# 启动服务
up:
	cd docker && docker-compose up -d

# 停止服务
down:
	cd docker && docker-compose down

# 查看日志
logs:
	cd docker && docker-compose logs -f

# 重启服务
restart:
	cd docker && docker-compose restart

# ============ 清理 ============

# 清理本地应用镜像
clean:
	docker rmi $(DOCKER_IMAGE) 2>/dev/null || true

# 清理本地基础镜像
clean-base:
	docker rmi $(BASE_IMAGE) $(BASE_IMAGE_LATEST) 2>/dev/null || true

# 清理所有本地镜像和构建缓存
clean-all:
	docker rmi $(DOCKER_IMAGE) 2>/dev/null || true
	docker rmi $(BASE_IMAGE) $(BASE_IMAGE_LATEST) 2>/dev/null || true
	docker builder prune -f

# ============ 帮助信息 ============

help:
	@echo ""
	@echo "AIX-DB Docker 镜像构建命令"
	@echo "=========================="
	@echo ""
	@echo "📦 基础镜像（依赖变更时执行）:"
	@echo "  make build-base        - 构建基础镜像（本地）"
	@echo "  make build-base-cache  - 构建基础镜像（使用缓存）"
	@echo "  make push-base         - 推送基础镜像至 Docker Hub"
	@echo "  make push-base-aliyun  - 推送基础镜像至阿里云"
	@echo "  make push-base-all     - 推送基础镜像至所有仓库"
	@echo ""
	@echo "🚀 应用镜像（日常发版）:"
	@echo "  make build             - 快速构建应用镜像（~30秒）"
	@echo "  make push-dockerhub    - 推送至 Docker Hub"
	@echo "  make push-aliyun       - 推送至阿里云"
	@echo "  make push-all          - 推送至所有仓库"
	@echo ""
	@echo "🐳 Docker Compose:"
	@echo "  make up                - 启动服务"
	@echo "  make down              - 停止服务"
	@echo "  make logs              - 查看日志"
	@echo "  make restart           - 重启服务"
	@echo ""
	@echo "🧹 清理:"
	@echo "  make clean             - 清理应用镜像"
	@echo "  make clean-base        - 清理基础镜像"
	@echo "  make clean-all         - 清理所有镜像和缓存"
	@echo ""

.PHONY: build-base build-base-cache push-base push-base-aliyun push-base-all \
        build build-with-base-version push-dockerhub push-aliyun push-all \
        up down logs restart clean clean-base clean-all help
