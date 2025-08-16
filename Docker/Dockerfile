# 依然使用Ubuntu作为基础
FROM ubuntu:latest

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/New_York

# 更新系统并安装核心依赖
# 我们删除了所有xrdp和xfce4相关的包，只保留最精简的组件
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    wget \
    python3-pip \
    python3-venv \
    ca-certificates \
    xvfb \
    google-chrome-stable && \
    # 清理缓存
    rm -rf /var/cache/apt /var/lib/apt/lists/*

# === 核心改动开始 ===

# 我们不再复制和使用那个复杂的run.sh脚本
# 而是直接把项目代码克隆到镜像里
RUN git clone https://github.com/Theyka/Turnstile-Solver.git /app
WORKDIR /app
RUN pip3 install -r requirements.txt --break-system-packages
RUN python3 -m camoufox fetch

# 暴露API端口
EXPOSE 5000

# 用一个简单命令让容器保持运行，而不是启动一堆服务
# tail -f /dev/null 是一个标准技巧，能让容器启动后什么也不做，只安静地“挂起”，等待我们的指令
ENTRYPOINT ["tail", "-f", "/dev/null"]
