#!/bin/bash
# 这个脚本用于在worker节点设置Kubernetes并加入集群
# 请在Ubuntu 22.04系统上以root或sudo权限运行

set -e

# 设置颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}开始配置Kubernetes工作节点...${NC}"

# 设置主机
#echo -e "${GREEN}设置主机名为worker-node...${NC}"
#hostnamectl set-hostname worker-node

# 提示用户输入IP地址
#read -p "请输入master节点IP地址: " MASTER_IP
#read -p "请输入worker节点IP地址: " WORKER_IP
MASTER_DOMAIN_NAME="c220g5-111030.wisc.cloudlab.us"
WORKER1_DOMAIN_NAME="c220g5-111032.wisc.cloudlab.us"
WORKER2_DOMAIN_NAME="clnode251.clemson.cloudlab.us"
# WORKER3_DOMAIN_NAME="pc85.cloudlab.umass.edu"
# WORKER4_DOMAIN_NAME="pc83.cloudlab.umass.edu"
LOAD_GEN_DOMAIN_NAME="c220g5-111012.wisc.cloudlab.us"


# 通过域名获取WORKER1_IP
MASTER_IP=$(getent hosts $MASTER_DOMAIN_NAME | awk '{print $1}')
WORKER1_IP=$(getent hosts $WORKER1_DOMAIN_NAME | awk '{print $1}')
WORKER2_IP=$(getent hosts $WORKER2_DOMAIN_NAME | awk '{print $1}')
# WORKER3_IP=$(getent hosts $WORKER3_DOMAIN_NAME | awk '{print $1}')
# WORKER4_IP=$(getent hosts $WORKER4_DOMAIN_NAME | awk '{print $1}')
LOAD_GEN_IP=$(getent hosts $LOAD_GEN_DOMAIN_NAME | awk '{print $1}')

# 更新hosts文件, 不保留原来的内容
echo -e "${GREEN}更新hosts文件...${NC}"
cat <<EOF > /etc/hosts
$MASTER_IP node0
$WORKER1_IP node1
$WORKER2_IP node2
$LOAD_GEN_IP node3
EOF

# 根据IP地址设置主机名
# 获取本机所有IP地址
HOST_IPS=$(hostname -I)

if echo "$HOST_IPS" | grep -q "$WORKER1_IP"; then
    hostnamectl set-hostname node1
elif echo "$HOST_IPS" | grep -q "$WORKER2_IP"; then
    hostnamectl set-hostname node2
elif echo "$HOST_IPS" | grep -q "$WORKER3_IP"; then
    hostnamectl set-hostname node3
elif echo "$HOST_IPS" | grep -q "$WORKER4_IP"; then
    hostnamectl set-hostname node4
fi


# echo -e "${GREEN}更新hosts文件...${NC}"
# cat <<EOF >> /etc/hosts
# $MASTER_IP node0
# $WORKER1_IP node1
# $WORKER2_IP node2
# $WORKER3_IP node3
# $WORKER4_IP node4
# EOF

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
swapoff -a
# 安装kubeadm、kubelet和kubectl
echo -e "${GREEN}安装kubeadm、kubelet和kubectl...${NC}"
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | gpg --dearmor -o /usr/share/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list
apt update
apt install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

# echo -e "${GREEN}执行tc.sh${NC}"
# bash tc.sh
# master 节点/users/Dingjie文件夹拉取join-command.sh文件
# echo -e "${GREEN}master 节点/users/Dingjie文件夹拉取join-command.sh文件...${NC}"
# scp Dingjie@$MASTER_IP:/users/Dingjie/Experiment/join-command.sh .

# 执行join-command.sh文件
# echo -e "${GREEN}执行join-command.sh文件...${NC}"
# bash join-command.sh
# 提示用户输入join-command

# edit ~/.tmux.conf file
echo -e "${GREEN}设置~/.tmux.conf文件...${NC}"
cat <<EOF > ~/.tmux.conf
set -g mouse on
set -g default-terminal "screen-256color"
set -g history-limit 10000
set -g status-position bottom
set -g status-justify left
set -g status-left-length 100
set -g status-right-length 100
EOF
# install tmux
echo -e "${GREEN}安装tmux...${NC}"
apt-get install -y tmux
# tmux source-file ~/.tmux.conf

echo -e "${GREEN}设置inotify参数...${NC}"
sysctl -w fs.inotify.max_user_watches=2099999999
sysctl -w fs.inotify.max_user_instances=2099999999
sysctl -w fs.inotify.max_queued_events=2099999999

echo -e "${GREEN}请输入join-command:${NC}"

# echo -e "${GREEN}工作节点设置完成${NC}"
