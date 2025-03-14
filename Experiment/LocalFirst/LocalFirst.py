#!/usr/bin/env python3

import os
import time
import json
import logging
from typing import Dict, List, Tuple, Optional
import traceback

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

import datetime
import pytz

# 配置日志
tz = pytz.timezone('Asia/Shanghai')
logging.Formatter.converter = lambda *args: datetime.datetime.now(tz).timetuple()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(filename)s:%(lineno)d - %(message)s')
logger = logging.getLogger('LocalFirstScheduler')

SCHEDULER_NAME = os.environ.get('SCHEDULER_NAME', 'local-first-scheduler')
# 设置重平衡间隔时间（秒）
REBALANCE_INTERVAL = int(os.environ.get('REBALANCE_INTERVAL', '30'))

class LocalFirstScheduler:
    """自定义Kubernetes调度器，实现'本地节点优先'策略"""
    
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
        
        # 初始化调度器状态
        self.scheduler_running = True
        # 添加重平衡计时器
        self.last_rebalance_time = time.time()
        # self.evict_pod_flag = True # 表示在bind_pod中是否执行了evict_pod
        self.binded_pod_name = [] # 记录已经绑定的pod_name
    
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
        """检查节点是否能够容纳Pod（检查CPU和内存资源）
        
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
            
            
            # node_cpu = int(node_cpu * 0.9)
            # node_memory = int(node_memory * 0.9)

            logger.info(f"Pod {pod.metadata.name} 需要 {pod_cpu}m CPU 和 {pod_memory}Ki 内存")
            logger.info(f"Node {node.metadata.name} 有 {node_cpu}m CPU 和 {node_memory}Ki 内存 Pod {pod.metadata.name}")
            logger.info(f"Node {node.metadata.name} 使用了 {used_cpu}m CPU 和 {used_memory}Ki 内存 Pod {pod.metadata.name}")
            logger.info(f"Node {node.metadata.name} 剩余 {node_cpu - used_cpu}m CPU 和 {node_memory - used_memory}Ki 内存 Pod {pod.metadata.name}")
            
            # 检查是否有足够的资源
            
            has_enough_cpu = node_cpu - used_cpu >= pod_cpu
            has_enough_memory = node_memory - used_memory >= pod_memory
            
            if not has_enough_cpu:
                logger.warning(f"节点 {node.metadata.name} 没有足够的CPU资源 (需要: {pod_cpu}m, 可用: {node_cpu - used_cpu}m)")
            
            if not has_enough_memory:
                logger.warning(f"节点 {node.metadata.name} 没有足够的内存资源 (需要: {pod_memory}Ki, 可用: {node_memory - used_memory}Ki)")
            
            return has_enough_cpu and has_enough_memory
            
        except Exception as e:
            logger.error(f"检查节点 {node.metadata.name if node and node.metadata else 'unknown'} 是否适合Pod {pod.metadata.name if pod and pod.metadata else 'unknown'} 时发生未预期的错误: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def bind_pod(self, pod_name: str, pod_namespace: str, node_name: str):
        """将Pod绑定到指定节点
        
        Args:
            pod_name: Pod名称
            pod_namespace: Pod命名空间
            node_name: 节点名称
            
        Returns:
            bool: 绑定是否成功
        """
        try:
            logger.info(f"正在将Pod {pod_namespace}/{pod_name} 绑定到节点 {node_name}")
            
            # 创建绑定对象
            binding = client.V1Binding(
                metadata=client.V1ObjectMeta(name=pod_name),
                target=client.V1ObjectReference(
                    kind="Node",
                    name=node_name,
                    api_version="v1"
                )
            )
            logger.info(f"创建绑定对象成功，正在执行绑定操作 Pod {pod_namespace}/{pod_name}")
            
            # 执行绑定操作
            self.core_v1.create_namespaced_binding(
                namespace=pod_namespace,
                body=binding,
                _preload_content=False
            )
            logger.info(f"绑定操作执行成功 Pod {pod_namespace}/{pod_name}")

            # 等待Pod进入Running状态
            max_retries = 30  # 最大重试次数
            retry_interval = 2  # 重试间隔（秒）
            
            for _ in range(max_retries):
                try:
                    pod_status = self.core_v1.read_namespaced_pod_status(
                        name=pod_name,
                        namespace=pod_namespace
                    )
                    if pod_status.status.phase == 'Running':
                        logger.info(f"Pod {pod_namespace}/{pod_name} 已成功进入Running状态 {node_name}")
                        return True
                    elif pod_status.status.phase in ['Failed', 'Unknown']:
                        # 获取Pod的Events信息
                        try:
                            events = self.core_v1.list_namespaced_event(
                                namespace=pod_namespace,
                                field_selector=f'involvedObject.name={pod_name}'
                            ).items
                            if events:
                                logger.error(f"Pod相关事件 {pod_name}:")
                                for event in events:
                                    logger.error(f"{pod_name}  - {event.last_timestamp}: {event.reason} - {event.message}")
                            else:
                                logger.error("未找到Pod相关事件")
                        except ApiException as e:
                            logger.error(f"获取Pod事件信息失败: {e}")
                        # 尝试解除Pod的节点绑定
                        self.evict_pod_by_name(pod_name, pod_namespace)
                        logger.error(f"Pod {pod_namespace}/{pod_name} 进入异常状态: {pod_status.status.phase}")
                        # self.evict_pod_flag = True
                        return False
                    
                    logger.info(f"等待Pod {pod_namespace}/{pod_name} 进入Running状态，当前状态: {pod_status.status.phase}")
                    time.sleep(retry_interval)
                except ApiException as e:
                    logger.error(f"Pod: {pod_namespace}/{pod_name} 获取Pod状态失败: {e}")
                    # self.evict_pod_by_name(pod_name, pod_namespace)
                    # return False
                except Exception as e:
                    logger.error(f"Pod: {pod_namespace}/{pod_name} 获取Pod状态时发生未预期的错误: {e}")
                    # self.evict_pod_by_name(pod_name, pod_namespace)
                    # return False
                    
            
            logger.error(f"等待Pod {pod_namespace}/{pod_name} 进入Running状态超时")
            self.evict_pod_by_name(pod_name, pod_namespace)
            # self.evict_pod_flag = True
            return False
            
            # logger.info(f"成功将Pod {pod_namespace}/{pod_name} 绑定到节点 {node_name}")
            # return True
        except ApiException as e:
            logger.error(f"绑定Pod {pod_namespace}/{pod_name} 到节点 {node_name} 失败: {e}")
            if self.evict_pod_by_name(pod_name, pod_namespace):
                logger.error(f"已解除Pod {pod_namespace}/{pod_name} 的节点绑定")
            else:
                logger.error(f"解除Pod {pod_namespace}/{pod_name} 的节点绑定失败")
            return False
        except Exception as e:
            logger.error(f"绑定Pod过程中发生未预期的错误: {e}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            if self.evict_pod_by_name(pod_name, pod_namespace):
                logger.error(f"已解除Pod {pod_namespace}/{pod_name} 的节点绑定")
            else:
                logger.error(f"解除Pod {pod_namespace}/{pod_name} 的节点绑定失败")
            return False

    def evict_pod_by_name(self, pod_name: str, pod_namespace: str="default") -> bool:
        """
        驱逐Pod

        Args:
            pod_name: Pod名称
            pod_namespace: Pod命名空间

        Returns:
            bool: 驱逐是否成功
        """
        # 验证参数
        if not pod_name or not pod_namespace:
            logger.error("Pod名称和命名空间不能为空")
            return False

        try:
            body = client.V1Eviction(
                metadata=client.V1ObjectMeta(
                    name=pod_name,
                    namespace=pod_namespace
                )
            )

            self.core_v1.create_namespaced_pod_eviction(
                name=pod_name,
                namespace=pod_namespace,
                body=body
            )

            logger.info(f"成功驱逐Pod {pod_namespace}/{pod_name}")
            return True
        except ApiException as e:
            if e.status == 404:
                # Pod不存在，说明已经被成功删除
                logger.info(f"Pod {pod_namespace}/{pod_name} 已不存在，视为驱逐成功")
                return True
            logger.error(f"无法驱逐Pod {pod_namespace}/{pod_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"驱逐Pod时发生错误: {e}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def evict_pod(self, pod: client.V1Pod) -> bool:
        """驱逐指定的Pod
        
        Args:
            pod: 要驱逐的Pod对象
            
        Returns:
            bool: 驱逐是否成功
        """
        pod_name = pod.metadata.name
        pod_namespace = pod.metadata.namespace
        return self.evict_pod_by_name(pod_name, pod_namespace)
    
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
        
        # 只处理default命名空间的Pod
        if pod_namespace != 'default':
            logger.info(f"跳过非default命名空间的Pod: {pod_namespace}/{pod_name}")
            return False
            
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
        fit_node = None
        for node in valid_local_nodes:
            try:
                if self.can_node_fit_pod(node, pod):
                    fit_node = node
                    break
            except Exception as e:
                logger.error(f"检查节点 {node.metadata.name} {pod_namespace}/{pod_name} 是否适合Pod时出错: {e}")
                
        bind_result = self.bind_pod(pod_name, pod_namespace, fit_node.metadata.name) if fit_node else False
        if bind_result:
            return True
        
        if not fit_node:
            logger.info(f"没有合适的local节点来调度Pod {pod_namespace}/{pod_name}，尝试调度到remote节点")
            for node in valid_remote_nodes:
                try:
                    if self.can_node_fit_pod(node, pod):
                        fit_node = node
                        break
                except Exception as e:
                    logger.error(f"检查节点 {node.metadata.name} {pod_namespace}/{pod_name} 是否适合Pod时出错: {e}")
            bind_result = self.bind_pod(pod_name, pod_namespace, fit_node.metadata.name) if fit_node else False
        return bind_result

        # for node in valid_local_nodes:
        #     try:
        #         if self.can_node_fit_pod(node, pod):
        #             # 确保节点名称有效
        #             node_name = node.metadata.name
        #             if not node_name or not isinstance(node_name, str) or node_name.strip() == "":
        #                 logger.error(f"无法调度Pod {pod_namespace}/{pod_name}: 节点名称无效 {node_name}")
        #                 continue
                        
        #             logger.info(f"尝试将Pod {pod_namespace}/{pod_name} 绑定到local节点 {node_name}")
        #             if self.bind_pod(pod_name, pod_namespace, node_name):
        #                 return True
        #     except Exception as e:
        #         logger.error(f"检查节点 {node.metadata.name} {pod_namespace}/{pod_name} 是否适合Pod时出错: {e}")
        #         logger.error(f"错误详情: {traceback.format_exc()}")
        
        
        # 如果无法在local节点调度，尝试调度到remote节点
        # 如果pod不是未定义变量
        
        # if self.evict_pod_flag:
        #     logger.info(f"Pod {pod_namespace}/{pod_name} 已被移除，无需再调度")
        #     self.evict_pod_flag = False
        #     return False

        # for node in valid_remote_nodes:
        #     try:
        #         if self.can_node_fit_pod(node, pod):
        #             # 确保节点名称有效
        #             node_name = node.metadata.name
        #             if not node_name or not isinstance(node_name, str) or node_name.strip() == "":
        #                 logger.error(f"无法调度Pod {pod_namespace}/{pod_name}: 节点名称无效 {node_name}")
        #                 continue
        #             logger.info(f"尝试将Pod {pod_namespace}/{pod_name} 绑定到remote节点 {node_name}")
        #             if self.bind_pod(pod_name, pod_namespace, node_name):
        #                 return True
        #     except Exception as e:
        #         logger.error(f"检查节点 {node.metadata.name} {pod_namespace}/{pod_name} 是否适合Pod时出错: {e}")
        #         import traceback
        #         logger.error(f"错误详情: {traceback.format_exc()}")
        
        # logger.warning(f"无法为Pod {pod_namespace}/{pod_name} 找到合适的节点")
        # return False
    
    def find_pods_to_rebalance(self) -> List[Tuple[client.V1Pod, client.V1Node]]:
        """查找可以从remote节点迁移到local节点的Pod
        
        Returns:
            List[Tuple[client.V1Pod, client.V1Node]]: 可迁移的Pod和目标节点列表
        """
        # 获取local和remote节点
        local_nodes = self.get_nodes_by_label('node-type=local')
        remote_nodes = self.get_nodes_by_label('node-type=remote')
        
        if not local_nodes or not remote_nodes:
            return []
        
        # 过滤掉无效的节点
        valid_local_nodes = []
        for node in local_nodes:
            if node and node.metadata and node.metadata.name and node.status and node.status.allocatable:
                valid_local_nodes.append(node)
        
        valid_remote_nodes = []
        for node in remote_nodes:
            if node and node.metadata and node.metadata.name and node.status and node.status.allocatable:
                valid_remote_nodes.append(node)
        
        if not valid_local_nodes or not valid_remote_nodes:
            return []
        
        # 查找运行在remote节点上的Pod
        pod_lst = []
        candidates = []
        for node in valid_remote_nodes:
            pods = self.get_pods_on_node(node.metadata.name)
            pod_lst.extend(pods)
        for pod in pod_lst:
            # 只考虑default命名空间的Pod，跳过DaemonSet Pod
            if pod.metadata.namespace != 'default':
                continue
            if pod.metadata.owner_references and pod.metadata.owner_references[0].kind == 'DaemonSet':
                continue
            
            # 检查是否有local节点可以容纳这个Pod
            for local_node in valid_local_nodes:
                if self.can_node_fit_pod(local_node, pod):
                    candidates.append((pod, local_node))
                    return candidates
        
        return candidates
    
    def rebalance_pods(self) -> None:
        """重平衡集群中的Pod分布，尝试将remote节点上的Pod迁移到local节点"""
        logger.info("开始执行Pod重平衡操作")
        
        # 检查default命名空间中所有Pod的状态
        try:
            pods = self.core_v1.list_namespaced_pod(namespace="default").items
            for pod in pods:
                if pod.status.phase != 'Running':
                    logger.info(f"跳过重平衡操作：存在非Running状态的Pod {pod.metadata.name}，状态：{pod.status.phase}")
                    return
        except Exception as e:
            logger.error(f"检查Pod状态时发生错误: {e}")
            return
        
        # 查找可以迁移的Pod
        candidates = self.find_pods_to_rebalance()
        
        if not candidates:
            logger.info("没有找到可以迁移的Pod")
            return
        
        # 最多迁移3个Pod，避免一次性迁移过多
        for pod, target_node in candidates[:3]:
            logger.info(f"尝试将Pod {pod.metadata.namespace}/{pod.metadata.name} 从remote节点迁移到local节点 {target_node.metadata.name}")
            if self.evict_pod(pod):
                logger.info(f"成功驱逐Pod {pod.metadata.namespace}/{pod.metadata.name}，等待重新调度")
                # 短暂等待，避免立即重新调度
                time.sleep(2)
    
    def run(self) -> None:
        """运行调度器主循环"""
        logger.info(f"启动 {SCHEDULER_NAME} 调度器")
        
        w = watch.Watch()
        
        while self.scheduler_running:
            try:
                # 只监视default命名空间中pending状态的Pod
                for event in w.stream(self.core_v1.list_namespaced_pod, namespace="default", timeout_seconds=10):
                    pod = event['object']
                    
                    # 只处理pending状态且指定了我们的调度器的Pod
                    if (pod.status.phase == 'Pending' and 
                        not pod.spec.node_name and 
                        pod.spec.scheduler_name == SCHEDULER_NAME):
                        
                        logger.info(f"发现待调度的Pod: {pod.metadata.namespace}/{pod.metadata.name}")
                        try:
                            success = self.schedule_pod(pod)
                            if not success:
                                logger.warning(f"Pod {pod.metadata.namespace}/{pod.metadata.name} 调度失败，无法找到合适的节点")
                        except Exception as e:
                            logger.error(f"调度Pod {pod.metadata.namespace}/{pod.metadata.name} 时发生错误: {e}")
                            logger.error(f"错误详情: {traceback.format_exc()}")
                    elif (pod.status.phase != 'Running' and
                        pod.status.phase != 'Succeeded' and
                        pod.status.phase != 'Pending' and
                        pod.spec.scheduler_name == SCHEDULER_NAME):
                        # delete the pod
                        try:
                            logger.info(f"发现异常状态的Pod: {pod.metadata.namespace}/{pod.metadata.name}, 状态: {pod.status.phase}")
                            # 删除处于非正常状态的Pod
                            self.evict_pod(pod)
                            logger.info(f"已删除异常状态的Pod: {pod.metadata.namespace}/{pod.metadata.name}")
                        except ApiException as e:
                            logger.error(f"删除Pod {pod.metadata.namespace}/{pod.metadata.name} 时发生错误: {e}")
                        
                
                # 定期执行重平衡操作
                current_time = time.time()
                if current_time - self.last_rebalance_time > REBALANCE_INTERVAL:
                    try:
                        self.rebalance_pods()
                        self.last_rebalance_time = current_time  # 更新最后执行时间
                    except Exception as e:
                        logger.error(f"重平衡Pod分布时发生错误: {e}")
                        import traceback
                        logger.error(f"错误详情: {traceback.format_exc()}")
                
                # 短暂休眠，避免CPU使用率过高
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"调度器运行时发生错误: {e}")
                import traceback
                logger.error(f"错误详情: {traceback.format_exc()}")
                time.sleep(5)  # 出错后等待一段时间再继续

def main():
    """主函数"""
    scheduler = LocalFirstScheduler()
    scheduler.run()

if __name__ == "__main__":
    main()