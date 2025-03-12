#!/bin/bash

# 添加用户权限处理
USER_HOME="/users/Dingjie"

# chmod 777 /users/Dingjie/mubench.zip
# # unzip mubench.zip
# # 解压缩mubench.zip文件
# cd /users/Dingjie
# # 将mubench.zip解压缩到mubench目录中
# unzip -o mubench.zip -d mubench
chmod -R 777 /users/Dingjie/muBench
cd /users/Dingjie

# 修复 pip 缓存目录权限
apt-get update
apt-get install -y dos2unix
sudo -H apt install -y python3.10-venv  # 添加 -H 参数
python -m venv venv
source venv/bin/activate

cd /users/Dingjie/muBench
# 添加缓存目录配置
export PIP_CACHE_DIR="${USER_HOME}/.cache/pip"
mkdir -p ${PIP_CACHE_DIR}
chmod -R 777 ${USER_HOME}/.cache

apt-get install -y python3-dev cmake
python -m pip install "cython<3.0.0" wheel
python -m pip install --no-build-isolation PyYAML==5.4.1
sudo apt-get -y install libffi-dev libcairo2
python -m pip install --cache-dir=${PIP_CACHE_DIR} -r requirements.txt

# 检查节点名是否包含node5
if hostname | grep -q "node3"; then
  echo "检测到节点名包含node3，跳过节点标签添加并结束脚本执行"
  exit 0
fi

# 将monitoring-install.sh的换行符从CRLF转换为LF
cd /users/Dingjie/muBench/Monitoring/kubernetes-full-monitoring
dos2unix monitoring-install.sh

sh monitoring-install.sh


# 为节点添加标签
echo "为Kubernetes节点添加标签..."
# 为node1和node2添加标签local
kubectl label nodes node1 node-type=local --overwrite
kubectl label nodes node2 node-type=remote --overwrite
# 为node3和node4添加标签remote
# kubectl label nodes node3 node-type=remote --overwrite
# kubectl label nodes node4 node-type=remote --overwrite
echo "节点标签添加完成"

kubectl apply -f Experiment/components.yaml