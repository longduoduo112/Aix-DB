# ============================================================
# AIX-DB 应用镜像 (App Image)
# 基于基础镜像，构建前端 + 复制后端源代码
# 
# 构建时机：每次发版或修复 bug 时
# 构建命令：make build
# 构建时间：~1-2分钟（含前端构建）
# ============================================================

# 全局 ARG（必须在第一个 FROM 之前声明，才能在 FROM 中使用）
ARG BASE_IMAGE=apconw/aix-db-base:latest

# ============ 阶段1: 构建前端 ============
FROM node:18-alpine AS frontend-builder

WORKDIR /app/web

# 安装 pnpm
RUN npm install -g pnpm@latest --no-fund --no-audit && \
    npm cache clean --force

# 复制前端依赖文件并安装
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile --prod=false --shamefully-hoist

# 复制前端源代码并构建
COPY web/ ./
RUN pnpm run build

# ============ 阶段2: 应用镜像 ============
FROM ${BASE_IMAGE}

WORKDIR /aix-db

# ============ 复制前端构建产物（覆盖基础镜像中的） ============
COPY --from=frontend-builder /app/web/dist /usr/share/nginx/html

# ============ 复制后端源代码 ============
COPY common/ common/
COPY config/ config/
COPY constants/ constants/
COPY controllers/ controllers/
COPY model/ model/
COPY models/ models/
COPY services/ services/
COPY agent/ agent/
COPY serv.py ./

# 复制文档目录
COPY docs/ docs/

# 清理源代码中的缓存文件（不清理 .venv 目录）
RUN find . -path "./.venv" -prune -o -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find . -path "./.venv" -prune -o -type f -name "*.pyc" -delete 2>/dev/null || true && \
    find . -path "./.venv" -prune -o -type f -name "*.pyo" -delete 2>/dev/null || true && \
    # 清理 docs 目录中不必要的文件
    rm -rf docs/site docs/blog docs/docs docs/images 2>/dev/null || true

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ && \
    pg_isready -U aix_db -h localhost || exit 1

# 使用启动脚本启动服务
CMD ["/entrypoint.sh"]
