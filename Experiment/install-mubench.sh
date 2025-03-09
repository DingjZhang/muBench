#!/bin/bash

# 添加用户权限处理
USER_HOME="/users/Dingjie"

chmod 777 /users/Dingjie/mubench.zip
# unzip mubench.zip
# 解压缩mubench.zip文件
cd /users/Dingjie
# 将mubench.zip解压缩到mubench目录中
unzip -o mubench.zip -d mubench
chmod -R 777 /users/Dingjie/mubench
cd /users/Dingjie/mubench

# 修复 pip 缓存目录权限
sudo -H apt install -y python3.10-venv  # 添加 -H 参数
python -m venv venv
source venv/bin/activate

# 添加缓存目录配置
export PIP_CACHE_DIR="${USER_HOME}/.cache/pip"
mkdir -p ${PIP_CACHE_DIR}
chmod -R 777 ${USER_HOME}/.cache

apt install -y python3-dev cmake
python -m pip install "cython<3.0.0" wheel
python -m pip install --no-build-isolation PyYAML==5.4.1
sudo apt-get install libffi-dev libcairo2 -y
python -m pip install --cache-dir=${PIP_CACHE_DIR} -r requirements.txt

# 将monitoring-install.sh的换行符从CRLF转换为LF
cd /users/Dingjie/mubench/Monitoring/kubernetes-full-monitoring
sed -i 's/\r$//' monitoring-install.sh

sh monitoring-install.sh

# 为节点添加标签
echo "为Kubernetes节点添加标签..."
# 为node1和node2添加标签local
kubectl label nodes node1 location=local --overwrite
kubectl label nodes node2 location=local --overwrite
# 为node3和node4添加标签remote
kubectl label nodes node3 location=remote --overwrite
kubectl label nodes node4 location=remote --overwrite
echo "节点标签添加完成"

