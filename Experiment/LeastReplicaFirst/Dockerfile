FROM python:3.8-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制调度器代码
COPY LeastReplicaFirst.py .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV SCHEDULER_NAME=least-replica-first-scheduler

# 运行调度器
CMD ["python", "LeastReplicaFirst.py"]