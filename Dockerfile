# 使用更小、更精简的 Ubuntu 基础镜像
FROM ubuntu:22.04

# 设置环境变量，避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# --- 优化点 1: 将所有 apt 操作合并为一层，并最后清理 ---
# 这可以显著减小镜像体积
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    wget \
    python3 \
    python3-pip \
    ca-certificates \
    xvfb && \
    # 下载 Chrome
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    # 安装 Chrome 并让 apt 自动处理依赖。--fix-broken 可以在依赖出问题时尝试修复
    apt-get install -y --no-install-recommends --fix-broken ./google-chrome-stable_current_amd64.deb && \
    # --- 优化点 2: 在同一层 RUN 命令中进行清理 ---
    # 这样可以确保下载的临时文件不会被保留在最终的镜像层中
    rm ./google-chrome-stable_current_amd64.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# --- 优化点 3: 分离代码复制和依赖安装 ---
# 这样如果你的代码变了，但依赖没变，就不用重新安装所有依赖，利用 Docker 缓存加速构建

# 先只复制依赖文件
WORKDIR /app
COPY requirements.txt .

# 安装 Python 依赖
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# 下载 Camoufox 浏览器
RUN python3 -m camoufox fetch

# 最后再复制所有项目代码
COPY . .

# 暴露 API 端口
EXPOSE 5000

# 最终启动命令
# 建议使用 CMD 而不是 ENTRYPOINT，除非你想让容器像一个可执行文件
# CMD ["python3", "api_solver.py", "--host", "0.0.0.0"]
# 如果你还是想手动启动，保留 tail 也可以
ENTRYPOINT ["tail", "-f", "/dev/null"]# 暴露API端口
EXPOSE 5000

# 最终启动命令
ENTRYPOINT ["tail", "-f", "/dev/null"]
