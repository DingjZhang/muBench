#!/bin/bash

# 添加命令行选项处理
DELETE_ONLY=false

while getopts ":d" opt; do
  case ${opt} in
    d )
      DELETE_ONLY=true
      ;;
    \? )
      echo "Invalid option: -$OPTARG" 1>&2
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

MASTER_DOMAIN_NAME="pc65.cloudlab.umass.edu"
WORKER1_DOMAIN_NAME="pc89.cloudlab.umass.edu"
WORKER2_DOMAIN_NAME="pc64.cloudlab.umass.edu"
# WORKER3_DOMAIN_NAME="pc85.cloudlab.umass.edu"
# WORKER4_DOMAIN_NAME="pc83.cloudlab.umass.edu"
LOAD_GEN_DOMAIN_NAME="pc88.cloudlab.umass.edu"


MASTER_IP=$(getent hosts $MASTER_DOMAIN_NAME | awk '{print $1}')
WORKER1_IP=$(getent hosts $WORKER1_DOMAIN_NAME | awk '{print $1}')
WORKER2_IP=$(getent hosts $WORKER2_DOMAIN_NAME | awk '{print $1}')
# WORKER3_IP=$(getent hosts $WORKER3_DOMAIN_NAME | awk '{print $1}')
# WORKER4_IP=$(getent hosts $WORKER4_DOMAIN_NAME | awk '{print $1}')
LOAD_GEN_IP=$(getent hosts $LOAD_GEN_DOMAIN_NAME | awk '{print $1}')


NETWORK_INTERFACE="eno1"

# 获取当前网络接口的IP地址
CURRENT_IP=$(ip -4 addr show $NETWORK_INTERFACE | grep -oP '(?<=inet\s)\d+(\.\d+){3}')


# 如果指定-d选项，只执行删除操作
if [ "$DELETE_ONLY" = true ]; then
    echo "执行删除操作"
    tc qdisc del dev $NETWORK_INTERFACE root 2>/dev/null
    echo "tc删除命令执行完成"
    exit 0
fi

# if [ "$CURRENT_IP" = "$MASTER_IP" ] || [ "$CURRENT_IP" = "$WORKER1_IP" ] || [ "$CURRENT_IP" = "$WORKER2_IP" ] || [ "$CURRENT_IP" = "$LOAD_GEN_IP" ]; then
if [ "$CURRENT_IP" = "$MASTER_IP" ] || [ "$CURRENT_IP" = "$WORKER1_IP" ] || [ "$CURRENT_IP" = "$LOAD_GEN_IP" ]; then
    echo "执行命令"
    tc qdisc del dev $NETWORK_INTERFACE root 2>/dev/null
    tc qdisc add dev $NETWORK_INTERFACE root handle 1: prio
    tc qdisc add dev $NETWORK_INTERFACE parent 1:1 handle 10: netem delay 20ms 3ms distribution normal
    
    tc filter add dev $NETWORK_INTERFACE parent 1:0 protocol ip prio 1 u32 match ip dst $WORKER2_IP flowid 1:1
    # tc filter add dev $NETWORK_INTERFACE parent 1:0 protocol ip prio 1 u32 match ip dst $WORKER3_IP flowid 1:1
    # tc filter add dev $NETWORK_INTERFACE parent 1:0 protocol ip prio 1 u32 match ip dst $WORKER4_IP flowid 1:1
    
else
    echo "执行命令"
    tc qdisc del dev $NETWORK_INTERFACE root 2>/dev/null
    tc qdisc add dev $NETWORK_INTERFACE root handle 1: prio
    tc qdisc add dev $NETWORK_INTERFACE parent 1:1 handle 10: netem delay 20ms 3ms distribution normal
    
    tc filter add dev $NETWORK_INTERFACE parent 1:0 protocol ip prio 1 u32 match ip dst $MASTER_IP flowid 1:1
    tc filter add dev $NETWORK_INTERFACE parent 1:0 protocol ip prio 1 u32 match ip dst $WORKER1_IP flowid 1:1
    # tc filter add dev $NETWORK_INTERFACE parent 1:0 protocol ip prio 1 u32 match ip dst $WORKER2_IP flowid 1:1
    tc filter add dev $NETWORK_INTERFACE parent 1:0 protocol ip prio 1 u32 match ip dst $LOAD_GEN_IP flowid 1:1
fi

echo "tc命令执行完成"
