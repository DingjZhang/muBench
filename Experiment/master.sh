#!/usr/bin/bash
# 这个脚本用于在master节点设置Kubernetes集群
# 请在Ubuntu 22.04系统上以root或sudo权限运行

set -e

# 设置颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 添加命令行选项处理
SKIP_SETUP=false

while getopts ":s" opt; do
  case ${opt} in
    s )
      SKIP_SETUP=true
      ;;
    \? )
      echo "Invalid option: -$OPTARG" 1>&2
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

echo -e "${GREEN}开始配置Kubernetes主节点..${NC}"

# 设置主机
# echo -e "${GREEN}设置主机名为master-node...${NC}"
hostnamectl set-hostname node0

# 提示用户输入IP地址
# read -p "请输入master节点IP地址: " MASTER_IP
# read -p "请输入worker节点IP地址: " WORKER_IP

MASTER_DOMAIN_NAME="pc63.cloudlab.umass.edu"
WORKER1_DOMAIN_NAME="pc84.cloudlab.umass.edu"
WORKER2_DOMAIN_NAME="pc70.cloudlab.umass.edu"
# WORKER3_DOMAIN_NAME="pc85.cloudlab.umass.edu"
# WORKER4_DOMAIN_NAME="pc83.cloudlab.umass.edu"
LOAD_GEN_DOMAIN_NAME="pc94.cloudlab.umass.edu"



# 通过域名获取WORKER1_IP
WORKER1_IP=$(getent hosts $WORKER1_DOMAIN_NAME | awk '{print $1}')
WORKER2_IP=$(getent hosts $WORKER2_DOMAIN_NAME | awk '{print $1}')
# WORKER3_IP=$(getent hosts $WORKER3_DOMAIN_NAME | awk '{print $1}')
# WORKER4_IP=$(getent hosts $WORKER4_DOMAIN_NAME | awk '{print $1}')
LOAD_GEN_IP=$(getent hosts $LOAD_GEN_DOMAIN_NAME | awk '{print $1}')

# 使用ifconifg获取eno1接口的IP作为MASTER_IP
MASTER_IP=$(ip addr show eno1 | grep "inet\b" | awk '{print $2}' | cut -d/ -f1)
echo -e "${GREEN}MASTER_IP: $MASTER_IP${NC}"

# MASTER_IP="128.105.145.67"
# WORKER_IP="128.105.145.65"

# # 更新hosts文件
if [ "$SKIP_SETUP" = false ]; then

echo -e "${GREEN}更新hosts文件...${NC}"
cat <<EOF > /etc/hosts
$MASTER_IP node0
$WORKER1_IP node1
$WORKER2_IP node2
$LOAD_GEN_IP node3
EOF

# 更新系统
echo -e "${GREEN}更新系统...${NC}"
apt update && apt upgrade -y

# 禁用swap
echo -e "${GREEN}禁用swap...${NC}"
swapoff -a
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

# 配置网络参数
echo -e "${GREEN}配置网络参数...${NC}"
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

sysctl --system

# 安装Docker
echo -e "${GREEN}安装Docker...${NC}"
apt install -y apt-transport-https ca-certificates curl software-properties-common gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update
apt install -y docker-ce docker-ce-cli containerd.io

# 启动Docker服务
systemctl enable docker
systemctl start docker

# 配置Docker守护进程
cat <<EOF | tee /etc/docker/daemon.json
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m"
  },
  "storage-driver": "overlay2"
}
EOF

# 重启Docker
systemctl daemon-reload
systemctl restart docker

# 安装cri-dockerd
echo -e "${GREEN}安装cri-dockerd...${NC}"
wget https://github.com/Mirantis/cri-dockerd/releases/download/v0.3.16/cri-dockerd_0.3.16.3-0.ubuntu-jammy_amd64.deb
dpkg -i cri-dockerd_0.3.16.3-0.ubuntu-jammy_amd64.deb
systemctl daemon-reload
systemctl enable --now cri-docker.socket

# 安装kubeadm、kubelet和kubectl
echo -e "${GREEN}安装kubeadm、kubelet和kubectl...${NC}"
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | gpg --dearmor -o /usr/share/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list
apt-get update
apt-get install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl
fi

# 禁用swap
echo -e "${GREEN}禁用swap...${NC}"
swapoff -a
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

# 初始化Kubernetes集群
echo -e "${GREEN}初始化Kubernetes集群...${NC}"
kubeadm init --pod-network-cidr=10.244.0.0/16 --cri-socket=unix:///var/run/cri-dockerd.sock --apiserver-advertise-address=$MASTER_IP

# 设置kubectl配置文件
echo -e "${GREEN}设置kubectl配置...${NC}"
mkdir -p $HOME/.kube
cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
chown $(id -u):$(id -g) $HOME/.kube/config

# 安装Calico网络插件
# echo -e "${GREEN}安装Calico网络插件...${NC}"
# kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml

# 安装Flannel网络插件
echo -e "${GREEN}安装Flannel网络插件...${NC}"
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
# 等待节点状态变为Ready
echo -e "${GREEN}等待节点状态变为Ready...${NC}"
# kubectl wait --for=condition=Ready node/node0
# get node name
NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
# 等待节点状态变为Ready
echo -e "${GREEN}等待节点状态变为Ready...${NC}"
kubectl wait --for=condition=Ready node/$NODE_NAME

# 生成加入命令
echo -e "${GREEN}生成加入命令...${NC}"
JOIN_COMMAND=$(kubeadm token create --print-join-command)
echo "worker节点加入命令: sudo $JOIN_COMMAND --cri-socket=unix:///var/run/cri-dockerd.sock"

# 保存加入命令到文件
echo "$JOIN_COMMAND --cri-socket=unix:///var/run/cri-dockerd.sock" > join-command.sh
chmod +x join-command.sh
# show join command
# echo "${GREEN}请在worker节点上执行以下命令加入集?${NC}"
# echo "${RED}$JOIN_COMMAND --cri-socket=unix:///var/run/cri-dockerd.sock${NC}"

echo -e "${GREEN}Master节点设置完成${NC}"
# echo -e "${GREEN}请在worker节点上执行以下命令加入集?${NC}"
# echo -e "${RED}$JOIN_COMMAND --cri-socket=unix:///var/run/cri-dockerd.sock${NC}"
# echo -e "${GREEN}或者将生成的join-command.sh文件复制到worker节点执行${NC}"

# 设置在普通用户模式下也可以使用kubectl
echo -e "${GREEN}设置在普通用户模式下也可以使用kubectl...${NC}"
mkdir -p /users/Dingjie/.kube
cp -i /etc/kubernetes/admin.conf /users/Dingjie/.kube/config
chown $(id -u):$(id -g) /users/Dingjie/.kube/config
chmod -R 777 /users/Dingjie/.kube

# set kubectl auto completion
echo -e "${GREEN}设置kubectl自动补全...${NC}"
apt-get install -y bash-completion
echo 'source <(kubectl completion bash)' >>~/.bashrc
echo 'alias k=kubectl' >>~/.bashrc
echo 'complete -o default -F __start_kubectl k' >>~/.bashrc
. ~/.bashrc
# 安装helm
echo -e "${GREEN}安装helm...${NC}"
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 设置节点的ssh配置，让其他节点可以从master节点使用scp命令复制文件
# echo -e "${GREEN}设置节点的ssh配置...${NC}"
# # 生成ssh密钥，无需输入yes
# ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -q -N ""
# # 修改id_rsa.pub文件的权限和id_rsa文件的权?# chmod 644 ~/.ssh/id_rsa.pub
# chmod 644 ~/.ssh/id_rsa
# ssh-copy-id -i ~/.ssh/id_rsa.pub Dingjie@$WORKER1_DOMAIN_NAME
# ssh-copy-id -i ~/.ssh/id_rsa.pub Dingjie@$WORKER2_DOMAIN_NAME
# ssh-copy-id -i ~/.ssh/id_rsa.pub Dingjie@$WORKER3_DOMAIN_NAME
# ssh-copy-id -i ~/.ssh/id_rsa.pub Dingjie@$WORKER4_DOMAIN_NAME
# # 复制join-command.sh文件到其他节?# echo -e "${GREEN}复制join-command.sh文件到其他节?..${NC}"
# scp -o StrictHostKeyChecking=no join-command.sh Dingjie@$WORKER1_DOMAIN_NAME:/users/Dingjie/Experiment/
# scp -o StrictHostKeyChecking=no join-command.sh Dingjie@$WORKER2_DOMAIN_NAME:/users/Dingjie/Experiment/
# scp -o StrictHostKeyChecking=no join-command.sh Dingjie@$WORKER3_DOMAIN_NAME:/users/Dingjie/Experiment/
# scp -o StrictHostKeyChecking=no join-command.sh Dingjie@$WORKER4_DOMAIN_NAME:/users/Dingjie/Experiment/

# edit ~/.inputrc file
echo -e "${GREEN}设置~/.inputrc文件...${NC}"
cat <<EOF > ~/.inputrc
"\e[A": history-search-backward
"\e[B": history-search-forward
set show-all-if-ambiguous on
set completion-ignore-case on
EOF
# execute bind ~/.inputrc
bind -f ~/.inputrc

# add /users/Dingjie/.local/bin to PATH
echo -e "${GREEN}添加/users/Dingjie/.local/bin到PATH...${NC}"
cat <<EOF >> ~/.bashrc
export PATH=\$PATH:/users/Dingjie/.local/bin
EOF
. ~/.bashrc

# 验证节点状态
echo -e "${GREEN}集群当前状${NC}"
kubectl get nodes

echo -e "${GREEN}执行tc.sh${NC}"
bash tc.sh
echo -e "${GREEN}Master节点设置完成${NC}"




