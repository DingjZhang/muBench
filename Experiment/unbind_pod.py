#!/usr/bin/env python3

import logging
import traceback
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('PodUnbinder')

def unbind_pod(pod_name: str, pod_namespace: str) -> bool:
    """
    解除Pod与节点的绑定关系
    
    Args:
        pod_name: Pod名称
        pod_namespace: Pod命名空间
        
    Returns:
        bool: 解除绑定是否成功
    """
    # 验证参数
    if not pod_name or not pod_namespace:
        logger.error(f"解除Pod绑定失败: 无效的Pod参数 (pod_name={pod_name}, pod_namespace={pod_namespace})")
        return False
        
    try:
        # 尝试加载集群内的配置
        try:
            config.load_incluster_config()
            logger.info("成功加载集群内配置")
        except:
            # 如果不在集群内，则加载本地配置
            config.load_kube_config()
            logger.info("成功加载本地配置")
        
        # 初始化Kubernetes API客户端
        core_v1 = client.CoreV1Api()
        
        # 获取Pod对象以确保它存在
        try:
            pod = core_v1.read_namespaced_pod(pod_name, pod_namespace)
            if not pod:
                logger.error(f"解除Pod绑定失败: 无法获取Pod对象 {pod_namespace}/{pod_name}")
                return False
        except ApiException as e:
            logger.error(f"解除Pod绑定失败: 无法获取Pod对象 {pod_namespace}/{pod_name}: {e}")
            return False
        
        # 检查Pod是否已经绑定到节点
        if not pod.spec.node_name:
            logger.info(f"Pod {pod_namespace}/{pod_name} 未绑定到任何节点，无需解除绑定")
            return True
        
        # 记录当前绑定的节点
        current_node = pod.spec.node_name
        logger.info(f"正在解除Pod {pod_namespace}/{pod_name} 与节点 {current_node} 的绑定")
        
        # 使用patch操作解除Pod与节点的绑定
        try:
            # 创建patch内容，将nodeName设置为None
            patch_body = {
                "spec": {
                    "nodeName": None
                }
            }
            
            # 执行patch操作
            core_v1.patch_namespaced_pod(
                name=pod_name,
                namespace=pod_namespace,
                body=patch_body
            )
            
            logger.info(f"成功解除Pod {pod_namespace}/{pod_name} 与节点 {current_node} 的绑定")
            return True
        except ApiException as e:
            logger.error(f"解除Pod绑定时API调用失败: {e}")
            return False
            
    except Exception as e:
        logger.error(f"解除Pod绑定过程中发生未预期的错误: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        return False

# 如果作为独立脚本运行，提供一个简单的命令行接口
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="解除Pod与节点的绑定关系")
    parser.add_argument("pod_name", help="Pod名称")
    parser.add_argument("pod_namespace", help="Pod命名空间", default="default", nargs="?")
    
    args = parser.parse_args()
    
    result = unbind_pod(args.pod_name, args.pod_namespace)
    if result:
        print(f"成功解除Pod {args.pod_namespace}/{args.pod_name} 的节点绑定")
    else:
        print(f"解除Pod {args.pod_namespace}/{args.pod_name} 的节点绑定失败")