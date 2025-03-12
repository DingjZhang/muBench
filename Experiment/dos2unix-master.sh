#!/bin/bash

# 安装dos2unix工具
echo "正在安装dos2unix工具..."
apt-get update
apt-get install -y dos2unix
echo "dos2unix工具安装完成"

# 处理当前目录下的所有.sh文件
echo "正在处理当前目录下的所有.sh文件..."
find . -name "*.sh" -type f -exec dos2unix {} \;
echo "所有.sh文件处理完成"

# 执行master.sh脚本
echo "正在执行master.sh脚本..."
bash master.sh
echo "master.sh脚本执行完毕"

# 监控Kubernetes集
echo "正在监控Kubernetes集群节点数量..."
while true; do
    # 获取当前节点数量
    NODE_COUNT=$(kubectl get nodes | grep -v NAME | wc -l)
    echo "当前集群节点数: $NODE_COUNT"
    
    # 检查节点数量是否达到5个或更多
    if [ "$NODE_COUNT" -ge 3 ]; then
        echo "节点数量已达到3个或更多，开始执行install-mubench.sh脚本"
        break
    fi
    
    echo "等待更多节点加入集群..."
    # 读取join-command.sh文件内容
    JOIN_COMMAND=$(cat join-command.sh)
    echo "获取到的join命令:   sudo $JOIN_COMMAND"
    sleep 30  # 每30秒检查一次
done

# 执行install-mubench.sh脚本
echo "正在执行install-mubench.sh脚本..."
bash install-mubench.sh
echo "install-mubench.sh脚本执行完毕"

echo "所有操作已完成"