FROM python:3.8-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制调度器代码
COPY LocalFirst.py .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV SCHEDULER_NAME=local-first-scheduler
ENV REBALANCE_INTERVAL=30

# 运行调度器
CMD ["python", "LocalFirst.py"]