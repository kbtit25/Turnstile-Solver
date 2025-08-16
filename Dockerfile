# 使用Ubuntu 22.04作为基础镜像
FROM ubuntu:22.04

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive

# 第一步：安装系统核心依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    wget \
    python3 \
    python3-pip \
    ca-certificates \
    xvfb

# 第二步：安装Google Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb && \
    rm ./google-chrome-stable_current_amd64.deb && \
    rm -rf /var/cache/apt /var/lib/apt/lists/*

# 将项目代码克隆到镜像里
RUN git clone https://github.com/Theyka/Turnstile-Solver.git /app

# 设置工作目录
WORKDIR /app

# 第三步：升级pip本身，然后安装Python依赖
# 这是关键修正：先升级pip，然后安装依赖时不再需要--break-system-packages
RUN pip3 install --upgrade pip && \
    pip3 install -r requirements.txt

# 下载Camoufox浏览器
RUN python3 -m camoufox fetch

# 暴露API端口
EXPOSE 5000

# 最终启动命令
ENTRYPOINT ["tail", "-f", "/dev/null"]
