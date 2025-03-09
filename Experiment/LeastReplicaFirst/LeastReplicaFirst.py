#!/usr/bin/env python3

import os
import time
import json
import logging
import random
from typing import Dict, List, Tuple, Optional

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('LeastReplicaFirstScheduler')

SCHEDULER_NAME = os.environ.get('SCHEDULER_NAME', 'least-replica-first-scheduler')

class LeastReplicaFirstScheduler:
    """自定义Kubernetes调度器，实现'最小副本数量优先'策略"""
    
    def __init__(self):
        """初始化调度器"""
        try:
            # 尝试加载集群内的配置
            config.load_incluster_config()
            logger.info("成功加载集群内配置")
        except:
            # 如果不在集群内，则加载本地配置
            config.load_kube_config()
            logger.info("成功加载本地配置")
        
        # 初始化Kubernetes API客户端
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_objects = client.CustomObjectsApi()
        
        # 初始化调度器状态
        self.scheduler_running = True
    
    def get_pod_owner_info(self, pod) -> Tuple[str, str, int]:
        """获取Pod所属的控制器信息
        
        Args:
            pod: Pod对象
            
        Returns:
            Tuple[str, str, int]: (控制器类型, 控制器名称, 副本数量)
        """
        owner_references = pod.metadata.owner_references
        if not owner_references:
            return "None", "None", 1
        
        owner = owner_references[0]
        kind = owner.kind
        name = owner.name
        namespace = pod.metadata.namespace
        
        # 获取控制器的副本数量
        replicas = 1  # 默认值
        try:
            if kind == "Deployment":
                deployment = self.apps_v1.read_namespaced_deployment(name, namespace)
                replicas = deployment.spec.replicas
            elif kind == "StatefulSet":
                stateful_set = self.apps_v1.read_namespaced_stateful_set(name, namespace)
                replicas = stateful_set.spec.replicas
            elif kind == "ReplicaSet":
                replica_set = self.apps_v1.read_namespaced_replica_set(name, namespace)
                replicas = replica_set.spec.replicas
            elif kind == "DaemonSet":
                # DaemonSet的副本数等于节点数
                replicas = len(self.core_v1.list_node().items)
        except ApiException as e:
            logger.error(f"获取控制器副本数量失败: {e}")
        
        return kind, name, replicas
    
    def get_nodes_by_label(self, label_selector: str) -> List[client.V1Node]:
        """获取带有特定标签的节点列表
        
        Args:
            label_selector: 标签选择器
            
        Returns:
            List[client.V1Node]: 节点列表
        """
        try:
            nodes = self.core_v1.list_node(label_selector=label_selector).items
            return nodes
        except ApiException as e:
            logger.error(f"获取节点列表失败: {e}")
            return []
    
    def get_pods_on_node(self, node_name: str) -> List[client.V1Pod]:
        """获取运行在特定节点上的所有Pod
        
        Args:
            node_name: 节点名称
            
        Returns:
            List[client.V1Pod]: Pod列表
        """
        try:
            field_selector = f'spec.nodeName={node_name},status.phase=Running'
            # 只获取default命名空间的Pod
            pods = self.core_v1.list_namespaced_pod(namespace="default", field_selector=field_selector).items
            return pods
        except ApiException as e:
            logger.error(f"获取节点上的Pod列表失败: {e}")
            return []
    
    def can_node_fit_pod(self, node: client.V1Node, pod: client.V1Pod) -> bool:
        """检查节点是否能够容纳Pod（简化版，仅检查CPU和内存）
        
        Args:
            node: 节点对象
            pod: Pod对象
            
        Returns:
            bool: 如果节点能够容纳Pod则返回True
        """
        try:
            # 验证节点和Pod对象
            if not node or not node.status or not node.status.allocatable:
                logger.error(f"无法检查节点适配性: 节点对象无效或缺少必要属性")
                return False
                
            if not pod or not pod.spec or not pod.spec.containers:
                logger.error(f"无法检查节点适配性: Pod对象无效或缺少必要属性")
                return False
                
            # 获取节点可分配资源
            allocatable = node.status.allocatable
            if not allocatable:
                logger.error(f"节点 {node.metadata.name} 没有可分配资源信息")
                return False
                
            # 统一将CPU转换为毫核(millicores)单位
            try:
                cpu_str = allocatable.get('cpu', '0')
                if 'm' in cpu_str:
                    node_cpu = int(cpu_str.replace('m', ''))
                else:
                    # 如果是整数核心数，转换为毫核
                    node_cpu = int(float(cpu_str) * 1000)
            except (ValueError, TypeError) as e:
                logger.error(f"解析节点 {node.metadata.name} 的CPU资源时出错: {e}")
                node_cpu = 0
                
            # 统一将内存转换为Ki单位
            try:
                mem_str = allocatable.get('memory', '0')
                if 'Ki' in mem_str:
                    node_memory = int(mem_str.replace('Ki', ''))
                elif 'Mi' in mem_str:
                    node_memory = int(mem_str.replace('Mi', '')) * 1024
                elif 'Gi' in mem_str:
                    node_memory = int(mem_str.replace('Gi', '')) * 1024 * 1024
                else:
                    # 假设是字节单位，转换为Ki
                    node_memory = int(mem_str) // 1024
            except (ValueError, TypeError) as e:
                logger.error(f"解析节点 {node.metadata.name} 的内存资源时出错: {e}")
                node_memory = 0
            
            # 获取节点上已使用的资源
            pods_on_node = self.get_pods_on_node(node.metadata.name)
            used_cpu = 0
            used_memory = 0
            
            for p in pods_on_node:
                if not p or not p.spec or not p.spec.containers:
                    continue
                    
                for container in p.spec.containers:
                    if not container or not container.resources or not container.resources.requests:
                        continue
                        
                    # 计算CPU使用量
                    if container.resources.requests.get('cpu'):
                        try:
                            cpu_str = container.resources.requests['cpu']
                            if 'm' in cpu_str:
                                used_cpu += int(cpu_str.replace('m', ''))
                            else:
                                # 如果是整数核心数，转换为毫核
                                used_cpu += int(float(cpu_str) * 1000)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"解析容器CPU请求时出错: {e}")
                    
                    # 计算内存使用量
                    if container.resources.requests.get('memory'):
                        try:
                            mem_str = container.resources.requests['memory']
                            if 'Ki' in mem_str:
                                used_memory += int(mem_str.replace('Ki', ''))
                            elif 'Mi' in mem_str:
                                used_memory += int(mem_str.replace('Mi', '')) * 1024
                            elif 'Gi' in mem_str:
                                used_memory += int(mem_str.replace('Gi', '')) * 1024 * 1024
                            else:
                                # 假设是字节单位，转换为Ki
                                used_memory += int(mem_str) // 1024
                        except (ValueError, TypeError) as e:
                            logger.warning(f"解析容器内存请求时出错: {e}")
            
            # 计算Pod需要的资源
            pod_cpu = 0
            pod_memory = 0
            
            for container in pod.spec.containers:
                if not container or not container.resources or not container.resources.requests:
                    continue
                    
                # 计算CPU需求
                if container.resources.requests.get('cpu'):
                    try:
                        cpu_str = container.resources.requests['cpu']
                        if 'm' in cpu_str:
                            pod_cpu += int(cpu_str.replace('m', ''))
                        else:
                            pod_cpu += int(float(cpu_str) * 1000)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"解析Pod {pod.metadata.name} 的CPU请求时出错: {e}")
                
                # 计算内存需求
                if container.resources.requests.get('memory'):
                    try:
                        mem_str = container.resources.requests['memory']
                        if 'Ki' in mem_str:
                            pod_memory += int(mem_str.replace('Ki', ''))
                        elif 'Mi' in mem_str:
                            pod_memory += int(mem_str.replace('Mi', '')) * 1024
                        elif 'Gi' in mem_str:
                            pod_memory += int(mem_str.replace('Gi', '')) * 1024 * 1024
                        else:
                            # 假设是字节单位，转换为Ki
                            pod_memory += int(mem_str) // 1024
                    except (ValueError, TypeError) as e:
                        logger.warning(f"解析Pod {pod.metadata.name} 的内存请求时出错: {e}")
            
            logger.info(f"Pod {pod.metadata.name} 需要 {pod_cpu} CPU 和 {pod_memory} 内存")
            logger.info(f"Node {node.metadata.name} 有 {node_cpu} CPU 和 {node_memory} 内存")
            logger.info(f"Node {node.metadata.name} 使用了 {used_cpu} CPU 和 {used_memory} 内存")
            logger.info(f"Node {node.metadata.name} 剩余 {node_cpu - used_cpu} CPU 和 {node_memory - used_memory} 内存")
            
            # 检查是否有足够的资源
            has_enough_cpu = node_cpu - used_cpu >= pod_cpu
            has_enough_memory = node_memory - used_memory >= pod_memory
            
            if not has_enough_cpu:
                logger.warning(f"节点 {node.metadata.name} 没有足够的CPU资源 (需要: {pod_cpu}, 可用: {node_cpu - used_cpu})")
            
            if not has_enough_memory:
                logger.warning(f"节点 {node.metadata.name} 没有足够的内存资源 (需要: {pod_memory}, 可用: {node_memory - used_memory})")
            
            return has_enough_cpu and has_enough_memory
            
        except Exception as e:
            logger.error(f"检查节点 {node.metadata.name if node and node.metadata else 'unknown'} 是否适合Pod {pod.metadata.name if pod and pod.metadata else 'unknown'} 时发生未预期的错误: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def find_pod_to_evict(self, local_nodes: List[client.V1Node], pod_to_schedule: client.V1Pod) -> Optional[client.V1Pod]:
        """
        查找可以从local节点驱逐到remote节点的Pod
        
        策略：优先驱逐来自副本数更少的控制器的Pod
        
        Args:
            local_nodes: local标签的节点列表
            pod_to_schedule: 需要调度的Pod
            
        Returns:
            Optional[client.V1Pod]: 可以驱逐的Pod，如果没有则返回None
        """
        # 获取待调度Pod的控制器信息
        _, _, target_replicas = self.get_pod_owner_info(pod_to_schedule)
        
        candidate_pods = []
        
        # 遍历所有local节点上的Pod
        for node in local_nodes:
            pods = self.get_pods_on_node(node.metadata.name)
            for pod in pods:
                # 只考虑default命名空间的Pod
                if pod.metadata.namespace != 'default':
                    continue
                
                owner_kind, _, replicas = self.get_pod_owner_info(pod)
                if owner_kind == 'DaemonSet':
                    continue
                
                # 如果找到副本数量更多的控制器的Pod，添加到候选列表
                if replicas > target_replicas:
                    candidate_pods.append((pod, replicas))
        
        # 按副本数量降序排序
        candidate_pods.sort(key=lambda x: x[1], reverse=True)
        
        # 返回副本数量最多的Pod
        return candidate_pods[0][0] if candidate_pods else None
    
    def find_pod_to_move_back(self, remote_nodes: List[client.V1Node], local_nodes: List[client.V1Node]) -> Optional[Tuple[client.V1Pod, client.V1Node]]:
        """
        查找可以从remote节点移回local节点的Pod
        
        策略：优先移回来自副本数量更多的控制器的Pod
        
        Args:
            remote_nodes: remote标签的节点列表
            local_nodes: local标签的节点列表
            
        Returns:
            Optional[Tuple[client.V1Pod, client.V1Node]]: (可以移回的Pod, 目标local节点)，如果没有则返回None
        """
        candidate_pods = []
        
        # 遍历所有remote节点上的Pod
        for node in remote_nodes:
            pods = self.get_pods_on_node(node.metadata.name)
            for pod in pods:
                # 只考虑default命名空间的Pod
                if pod.metadata.namespace != 'default':
                    continue
                
                owner_kind, _, replicas = self.get_pod_owner_info(pod)
                if owner_kind == 'DaemonSet':
                    continue
                
                # 添加到候选列表
                candidate_pods.append((pod, replicas))
        
        # 按副本数量降序排序
        candidate_pods.sort(key=lambda x: x[1], reverse=True)
        
        # 检查是否有local节点可以容纳这些Pod
        for pod, _ in candidate_pods:
            for node in local_nodes:
                if self.can_node_fit_pod(node, pod):
                    return pod, node
        
        return None
    
    def bind_pod(self, pod_name: str, pod_namespace: str, node_name: str) -> bool:
        """将Pod绑定到指定节点
        
        Args:
            pod_name: Pod名称
            pod_namespace: Pod命名空间
            node_name: 节点名称
            
        Returns:
            bool: 绑定是否成功
        """
        # 验证参数
        if not pod_name or not pod_namespace:
            logger.error(f"绑定Pod失败: 无效的Pod参数 (pod_name={pod_name}, pod_namespace={pod_namespace})")
            return False
            
        if not node_name or node_name.strip() == "":
            logger.error(f"绑定Pod失败: 节点名称为空 (pod={pod_namespace}/{pod_name}, node_name={node_name})")
            return False
            
        try:
            logger.info(f"正在将Pod {pod_namespace}/{pod_name} 绑定到节点 {node_name}")
            
            # 获取Pod对象以确保它存在
            try:
                pod = self.core_v1.read_namespaced_pod(pod_name, pod_namespace)
                if not pod:
                    logger.error(f"绑定Pod失败: 无法获取Pod对象 {pod_namespace}/{pod_name}")
                    return False
            except ApiException as e:
                logger.error(f"绑定Pod失败: 无法获取Pod对象 {pod_namespace}/{pod_name}: {e}")
                return False
            
            # 创建绑定对象
            # target_ref = client.V1ObjectReference(
            #     api_version="v1",
            #     kind="Node",
            #     name=node_name
            # )
            
            # # 验证target_ref对象
            # if not target_ref or not target_ref.name or target_ref.name.strip() == "":
            #     logger.error(f"绑定Pod失败: 创建的target对象无效 (pod={pod_namespace}/{pod_name}, node_name={node_name})")
            #     return False
            
            # 使用直接的JSON结构创建绑定请求
            # 创建正式的V1Binding对象
            binding = client.V1Binding(
                metadata=client.V1ObjectMeta(name=pod_name),
                target=client.V1ObjectReference(
                    kind="Node",
                    name=node_name,
                    api_version="v1"
                )
            )
            
            # 验证binding对象有效性
            if not binding.target or not binding.target.name:
                logger.error(f"创建的Binding对象无效: {binding}")
                return False
            
            logger.info(f"创建的绑定对象: {binding.to_dict()}")
            
            # 执行绑定操作
            logger.info(f"开始将Pod {pod_namespace}/{pod_name} 绑定到节点 {node_name}")
            # 使用官方推荐的方法创建绑定
            if not node_name:
                logger.error("无效的node_name参数，无法执行绑定")
                return False
            
            try:
                self.core_v1.create_namespaced_binding(
                    namespace=pod_namespace,
                    body=binding,
                    _preload_content=False
                )
                logger.info(f"成功将Pod {pod_namespace}/{pod_name} 绑定到节点 {node_name}")
                return True
            except ApiException as e:
                logger.error(f"API调用失败: {json.loads(e.body)['message']}")
                return False
            
            logger.info(f"成功将Pod {pod_namespace}/{pod_name} 绑定到节点 {node_name}")
            return True
        except ApiException as e:
            logger.error(f"绑定Pod {pod_namespace}/{pod_name} 到节点 {node_name} 失败: {e}")
            return False
        except Exception as e:
            logger.error(f"绑定Pod过程中发生未预期的错误: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def evict_pod(self, pod: client.V1Pod) -> bool:
        """驱逐指定的Pod
        
        Args:
            pod: 要驱逐的Pod对象
            
        Returns:
            bool: 驱逐是否成功
        """
        try:
            body = client.V1Eviction(
                metadata=client.V1ObjectMeta(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace
                )
            )
            
            self.core_v1.create_namespaced_pod_eviction(
                pod.metadata.name, pod.metadata.namespace, body
            )
            
            logger.info(f"成功驱逐Pod {pod.metadata.namespace}/{pod.metadata.name}")
            return True
        except ApiException as e:
            logger.error(f"驱逐Pod失败: {e}")
            return False
    
    def schedule_pod(self, pod: client.V1Pod) -> bool:
        """为Pod选择合适的节点并进行调度
        
        Args:
            pod: 需要调度的Pod对象
            
        Returns:
            bool: 调度是否成功
        """
        # 验证Pod对象
        if not pod or not pod.metadata or not pod.metadata.name or not pod.metadata.namespace:
            logger.error("调度Pod失败: Pod对象无效或缺少必要属性")
            return False
            
        pod_name = pod.metadata.name
        pod_namespace = pod.metadata.namespace
        logger.info(f"开始为Pod {pod_namespace}/{pod_name} 寻找合适的节点")
            
        # 获取local和remote节点
        local_nodes = self.get_nodes_by_label('node-type=local')
        remote_nodes = self.get_nodes_by_label('node-type=remote')
        
        logger.info(f"找到 {len(local_nodes)} 个local节点和 {len(remote_nodes)} 个remote节点")
        
        # 检查是否有可用节点
        if not local_nodes and not remote_nodes:
            logger.warning(f"没有可用的节点来调度Pod {pod_namespace}/{pod_name}")
            return False
        
        # 过滤掉无效的节点
        valid_local_nodes = []
        for node in local_nodes:
            if node and node.metadata and node.metadata.name and node.status and node.status.allocatable:
                valid_local_nodes.append(node)
            else:
                logger.warning(f"跳过无效的local节点对象: {node.metadata.name if node and node.metadata else 'unknown'}")
        
        valid_remote_nodes = []
        for node in remote_nodes:
            if node and node.metadata and node.metadata.name and node.status and node.status.allocatable:
                valid_remote_nodes.append(node)
            else:
                logger.warning(f"跳过无效的remote节点对象: {node.metadata.name if node and node.metadata else 'unknown'}")
        
        logger.info(f"有效节点数量: {len(valid_local_nodes)} 个local节点和 {len(valid_remote_nodes)} 个remote节点")
        
        # 首先尝试调度到local节点
        for node in valid_local_nodes:
            try:
                if self.can_node_fit_pod(node, pod):
                    # 确保节点名称有效
                    node_name = node.metadata.name
                    if not node_name or not isinstance(node_name, str) or node_name.strip() == "":
                        logger.error(f"无法调度Pod {pod_namespace}/{pod_name}: 节点名称无效 {node_name}")
                        continue
                        
                    logger.info(f"尝试将Pod {pod_namespace}/{pod_name} 绑定到local节点 {node_name}")
                    if self.bind_pod(pod_name, pod_namespace, node_name):
                        return True
            except Exception as e:
                logger.error(f"检查节点 {node.metadata.name} 是否适合Pod时出错: {e}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
        
        # 如果local节点无法容纳，尝试驱逐一个Pod
        try:
            pod_to_evict = self.find_pod_to_evict(valid_local_nodes, pod)
            if pod_to_evict:
                logger.info(f"尝试驱逐Pod {pod_to_evict.metadata.namespace}/{pod_to_evict.metadata.name} 以腾出空间")
                if self.evict_pod(pod_to_evict):
                    # 等待Pod被驱逐
                    time.sleep(5)
                    # 重新尝试调度
                    return self.schedule_pod(pod)
        except Exception as e:
            logger.error(f"尝试驱逐Pod时出错: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
        
        # 如果无法在local节点调度，尝试调度到remote节点
        for node in valid_remote_nodes:
            try:
                if self.can_node_fit_pod(node, pod):
                    # 确保节点名称有效
                    node_name = node.metadata.name
                    if not node_name or not isinstance(node_name, str) or node_name.strip() == "":
                        logger.error(f"无法调度Pod {pod_namespace}/{pod_name}: 节点名称无效 {node_name}")
                        continue
                        
                    logger.info(f"尝试将Pod {pod_namespace}/{pod_name} 绑定到remote节点 {node_name}")
                    if self.bind_pod(pod_name, pod_namespace, node_name):
                        return True
            except Exception as e:
                logger.error(f"检查节点 {node.metadata.name} 是否适合Pod时出错: {e}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
        
        logger.warning(f"无法为Pod {pod_namespace}/{pod_name} 找到合适的节点")
        return False
    
    def balance_pods(self) -> None:
        """平衡集群中的Pod分布，尝试将remote节点上的Pod移回local节点"""
        local_nodes = self.get_nodes_by_label('node-type=local')
        remote_nodes = self.get_nodes_by_label('node-type=remote')
        
        if not remote_nodes or not local_nodes:
            return
        
        result = self.find_pod_to_move_back(remote_nodes, local_nodes)
        if result:
            pod, target_node = result
            logger.info(f"尝试将Pod {pod.metadata.namespace}/{pod.metadata.name} 从remote节点移回local节点 {target_node.metadata.name}")
            if self.evict_pod(pod):
                # Pod被驱逐后会重新创建，Kubernetes会重新调度它
                # 由于我们的调度器会优先选择local节点，所以它应该会被调度到local节点
                logger.info(f"成功驱逐Pod，等待重新调度")
    
    def run(self) -> None:
        """运行调度器主循环"""
        logger.info(f"启动 {SCHEDULER_NAME} 调度器，只管理default命名空间的Pod")
        
        w = watch.Watch()
        
        while self.scheduler_running:
            try:
                # 监视default命名空间中pending状态的Pod
                for event in w.stream(self.core_v1.list_namespaced_pod, namespace="default", timeout_seconds=10):
                    pod = event['object']
                    
                    # 只处理pending状态且指定了我们的调度器的Pod
                    if (pod.status.phase == 'Pending' and 
                        not pod.spec.node_name and 
                        pod.spec.scheduler_name == SCHEDULER_NAME):
                        
                        logger.info(f"发现待调度的Pod: {pod.metadata.namespace}/{pod.metadata.name}")
                        try:
                            # 验证Pod对象的完整性
                            if not pod or not pod.metadata or not pod.metadata.name or not pod.metadata.namespace:
                                logger.error(f"无法调度Pod: Pod对象无效或缺少必要属性")
                                continue
                                
                            success = self.schedule_pod(pod)
                            if not success:
                                logger.warning(f"Pod {pod.metadata.namespace}/{pod.metadata.name} 调度失败，无法找到合适的节点")
                        except Exception as e:
                            logger.error(f"调度Pod {pod.metadata.namespace}/{pod.metadata.name} 时发生错误: {e}")
                            # 记录更详细的错误信息
                            import traceback
                            logger.error(f"错误详情: {traceback.format_exc()}")
                
                # 定期尝试平衡Pod分布
                try:
                    self.balance_pods()
                except Exception as e:
                    logger.error(f"平衡Pod分布时发生错误: {e}")
                    import traceback
                    logger.error(f"错误详情: {traceback.format_exc()}")
                
                # 短暂休眠，避免CPU使用率过高
                time.sleep(15)
                
            except Exception as e:
                logger.error(f"调度器运行时发生错误: {e}")
                # 记录更详细的错误信息
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
                time.sleep(5)  # 出错后等待一段时间再继续

def main():
    """主函数"""
    scheduler = LeastReplicaFirstScheduler()
    scheduler.run()

if __name__ == "__main__":
    main()