#!/bin/bash

# 解析命令行参数
ONLY_INSTALL=false
for arg in "$@"; do
  if [ "$arg" == "--only-install" ]; then
    ONLY_INSTALL=true
  fi
done

# 定义基础路径变量
USER_HOME="/users/Dingjie"
PROJECT_DIR="${USER_HOME}/muBench"  # 新增项目根目录变量

# 修改权限命令替换
chmod -R 777 "$PROJECT_DIR"

cd "$USER_HOME"
# 修复 pip 缓存目录权限
apt-get update
apt-get install -y dos2unix
sudo -H apt install -y python3.10-venv  # 添加 -H 参数
# 在USER_HOME目录下创建并激活虚拟环境
cd "$USER_HOME"
python -m venv "$USER_HOME/venv"
source "$USER_HOME/venv/bin/activate"

cd "$USER_HOME"  # 替换原绝对路径
# 添加缓存目录配置
export PIP_CACHE_DIR="${USER_HOME}/.cache/pip"
mkdir -p ${PIP_CACHE_DIR}
chmod -R 777 ${USER_HOME}/.cache

cd "$PROJECT_DIR"
apt-get install -y python3-dev cmake
python -m pip install "cython<3.0.0" wheel
python -m pip install --no-build-isolation PyYAML==5.4.1
sudo apt-get -y install libffi-dev libcairo2
python -m pip install --cache-dir=${PIP_CACHE_DIR} -r requirements.txt

# 检查是否指定了只安装选项
if [ "$ONLY_INSTALL" = true ]; then
  echo "检测到--only-install选项，完成安装后跳过节点标签添加并结束脚本执行"
  exit 0
fi

# 将monitoring-install.sh的换行符从CRLF转换为LF
cd "$PROJECT_DIR/Monitoring/kubernetes-full-monitoring"  # 使用组合路径变量
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

cd "$PROJECT_DIR"
kubectl apply -f Experiment/components.yaml