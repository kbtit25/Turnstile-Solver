# 使用一个更精简的Ubuntu基础镜像
FROM ubuntu:22.04

# 设置环境变量，避免安装过程中的交互提示
ENV DEBIAN_FRONTEND=noninteractive

# 更新系统并安装最核心的依赖
# 我们删除了所有xrdp和xfce4相关的包，只保留xvfb
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    python3-pip \
    python3-venv \
    ca-certificates \
    xvfb \
    google-chrome-stable && \
    # 清理缓存
    rm -rf /var/cache/apt /var/lib/apt/lists/*

# 将项目代码克隆到镜像里
RUN git clone https://github.com/Theyka/Turnstile-Solver.git /app

# 设置工作目录
WORKDIR /app

# 安装Python依赖
RUN pip3 install -r requirements.txt --break-system-packages

# 下载Camoufox浏览器
RUN python3 -m camoufox fetch

# 暴露API端口
EXPOSE 5000

# 最终的、完美的启动命令！
# 使用xvfb-run来包裹python3命令，并接收外部传入的参数
ENTRYPOINT ["xvfb-run", "-a", "python3", "api_solver.py", "--host", "0.0.0.0"]
CMD ["--browser_type", "camoufox", "--thread", "4"]
