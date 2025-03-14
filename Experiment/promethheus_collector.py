import requests
import pandas as pd
import time
import os
import sys
import signal
from datetime import datetime, timedelta
from kubernetes import client, config

query_step = "30s"
query_command = f"sum by (s0) (increase(mub_request_processing_latency_milliseconds_sum{{}}[{query_step}])) / sum by (s0) (increase(mub_request_processing_latency_milliseconds_count{{}}[{query_step}]))"
prometheus_url = "http://localhost:30000"

# 全局变量，用于控制数据收集循环
STOP_COLLECTION = False
COLLECTION_INTERVAL = 15  # 数据收集间隔，单位为秒
result_dict = {'latency': [], 'node1': [], 'node2': [], 'node1_pod_num': [], 'node2_pod_num': [], 'timestamp': []}
output_dir = 'collected_data'
output_file = f'prometheus_data_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'  # 默认输出文件名

def query_latency():
    # 执行一次query_command查询
    # 构建API请求URL - 使用query而不是query_range
    query_url = f"{prometheus_url}/api/v1/query"
    params = {
        'query': query_command
    }
    
    try:
        # 发送请求获取数据
        response = requests.get(query_url, params=params)
        response.raise_for_status()  # 如果请求失败则抛出异常
        
        data = response.json()
        
        # 检查响应状态
        if data['status'] != 'success':
            raise Exception(f"Prometheus API返回错误: {data.get('error', '未知错误')}")
            
        # 提取结果数据
        result_data = data['data']['result']
        
        if not result_data:
            print("警告: 查询没有返回任何数据")
            return None
            
        # 返回第一个结果的值
        return float(result_data[0]['value'][1])
        
    except requests.exceptions.RequestException as e:
        print(f"请求Prometheus API时出错: {e}")
        return None
    except Exception as e:
        print(f"处理数据时出错: {e}")
        return None

def query_pod_list(node_name, ns='default'):
    """
    查询指定节点上特定命名空间的Pod名称列表
    
    参数:
        node_name (str): 节点名称
        ns (str): 命名空间名称
    
    返回:
        List[str]: Pod名称列表
    """
    try:
        # 加载Kubernetes配置
        config.load_kube_config()
        v1 = client.CoreV1Api()
        
        # 使用field_selector筛选出指定节点上的Pod名称
        field_selector = f'spec.nodeName={node_name},status.phase=Running'
        pods = v1.list_namespaced_pod(namespace=ns, field_selector=field_selector).items
        # 只返回Pod名称列表
        pod_names = [pod.metadata.name for pod in pods]
        return pod_names
    except client.rest.ApiException as e:
        print(f"获取节点上的Pod列表失败: {e}")
        return []
    except Exception as e:
        print(f"查询Pod列表时出错: {e}")
        return []

def collect_data_loop():
    """持续收集数据的循环函数，直到收到停止信号"""
    global STOP_COLLECTION, result_dict
    
    print("开始收集Prometheus数据...")
    index = 0
    
    counter = 0  # 连续无效结果计数器
    while not STOP_COLLECTION:
        timestamp = datetime.now()
        timestamp = timestamp.strftime("%Y%m%d_%H%M%S")
        result_dict['timestamp'].append(timestamp)
        
        # 收集延迟数据
        latency = query_latency()
        
        # 检查latency类型并更新计数器
        if latency is not None:
            if pd.isna(latency):
                counter += 1
                print(f"警告: 第{index}次获取到非浮点数延迟值，连续无效次数: {counter}")
                if counter >= 4:
                    print("连续4次获取无效延迟，停止数据收集")
                    STOP_COLLECTION = True
                    break
            else:
                counter = 0  # 重置计数器
                print(f"第{index}次查询的延迟为: {latency:.2f}")
                result_dict['latency'].append(round(latency, 2))
        else:
            result_dict['latency'].append(None)
        
        # 收集node1上的Pod信息
        node1_pods = query_pod_list('node1')
        result_dict['node1'].append(node1_pods)
        node_num = len(node1_pods) if node1_pods else 0
        result_dict['node1_pod_num'].append(len(node1_pods) if node1_pods else 0)
        print(f"node1上Pod数量为: {node_num}")
        
        # 收集node2上的Pod信息
        node2_pods = query_pod_list('node2')
        result_dict['node2'].append(node2_pods)
        node_num = len(node2_pods) if node2_pods else 0
        result_dict['node2_pod_num'].append(node_num)
        print(f"node2上Pod数量为: {node_num}")
        
        # print(f"数据收集循环 #{index} 完成")
        index += 1
        
        # 等待下一个收集间隔
        time.sleep(COLLECTION_INTERVAL)
    
    # 收到停止信号后，保存数据
    save_collected_data()
    print("数据收集已停止并保存")

def save_collected_data(filename=None):
    """将收集的数据保存为CSV文件"""
    global result_dict
    
    if filename is None:
        filename = output_file
    
    # 创建DataFrame
    df_data = {
        'timestamp': result_dict['timestamp'],
        'latency': result_dict['latency'],
        'node1_pod_count': [int(r) for r in result_dict['node1_pod_num']],
        'node2_pod_count': [int(r) for r in result_dict['node2_pod_num']],
        'node1_pods': result_dict['node1'],
        'node2_pods': result_dict['node2']
    }
    
    # 确保所有列的长度一致
    max_length = max(len(v) for v in df_data.values())
    for k in df_data:
        if len(df_data[k]) < max_length:
            df_data[k].extend([None] * (max_length - len(df_data[k])))
    
    df = pd.DataFrame(df_data)
    
    # 保存到CSV
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, filename)
    df.to_csv(save_path, index=False)
    print(f"数据已保存到: {save_path}")
    return save_path

def handle_stop_signal(signum, frame):
    """处理停止信号"""
    global STOP_COLLECTION
    print("收到停止信号，准备结束数据收集...")
    STOP_COLLECTION = True

def main():
    """主函数，用于直接运行脚本时"""
    # 注册信号处理函数
    # signal.signal(signal.SIGTERM, handle_stop_signal)
    # signal.signal(signal.SIGINT, handle_stop_signal)
    
    # 如果有命令行参数，可以设置输出文件名
    if len(sys.argv) > 1:
        global output_file
        output_file = sys.argv[1]
    
    try:
        collect_data_loop()
    except KeyboardInterrupt:
        print("收到键盘中断，停止数据收集...")
        STOP_COLLECTION = True
        save_collected_data()




def query_prometheus(query, start_time=None, end_time=None, step='1m'):
    """
    查询Prometheus并返回过去一段时间的结果，默认为过去一小时
    
    参数:
        query (str): 查询表达式
        start_time (datetime, optional): 开始时间，默认为1小时前
        end_time (datetime, optional): 结束时间，默认为当前时间
        step (str, optional): 采样步长，默认为1分钟
    
    返回:
        str: 保存的CSV文件路径
    """
    # 设置默认时间范围
    if end_time is None:
        end_time = datetime.now()
    if start_time is None:
        start_time = end_time - timedelta(minutes=15)
    
    # 转换为Prometheus API所需的时间格式
    start_time_str = start_time.isoformat("T") + "Z"
    end_time_str = end_time.isoformat("T") + "Z"
    print(start_time_str)
    print(end_time_str)
    
    # 构建API请求URL - 使用query_range而不是query
    query_url = f"{prometheus_url}/api/v1/query_range"
    params = {
        'query': query,
        'start': start_time_str,
        'end': end_time_str,
        'step': step
    }

    
    try:
        # 发送请求获取数据
        response = requests.get(query_url, params=params)
        response.raise_for_status()  # 如果请求失败则抛出异常
        
        data = response.json()
        
        # 检查响应状态
        if data['status'] != 'success':
            raise Exception(f"Prometheus API返回错误: {data.get('error', '未知错误')}")
        
        print(data)
        # 提取结果数据
        result_data = data['data']['result']
        
        if not result_data:
            print(f"警告: 查询 '{query}' 没有返回任何数据")
            return None
        
        # 创建保存目录
        save_dir = 'prometheus_data'
        os.makedirs(save_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = query.replace("{", "_").replace("}", "_").replace(":", "_").replace(" ", "_").replace("(", "_").replace(")", "_").replace("/", "_")
        # 限制文件名长度
        if len(safe_query) > 50:
            safe_query = safe_query[:50]
        filename = f"{save_dir}/{safe_query}_{timestamp}.csv"
        
        # 将数据转换为DataFrame并保存
        all_dfs = []
        for result in result_data:
            # 提取标签信息
            metric_labels = result['metric']
            
            # 提取时间序列数据
            values = result['values']  # 格式为 [timestamp, value]
            
            # 创建DataFrame
            df = pd.DataFrame(values, columns=['timestamp', 'value'])
            
            # 转换时间戳为可读格式
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            
            # 转换值为数值类型
            df['value'] = pd.to_numeric(df['value'])
            
            # 添加标签列
            for label_key, label_value in metric_labels.items():
                df[label_key] = label_value
                
            all_dfs.append(df)
        
        # 合并所有结果
        if len(all_dfs) > 1:
            final_df = pd.concat(all_dfs, ignore_index=True)
        else:
            final_df = all_dfs[0]
        
        # 保存到CSV文件
        final_df.to_csv(filename, index=False)
        print(f"数据已保存到: {filename}")
        
        return filename
        
    except requests.exceptions.RequestException as e:
        print(f"请求Prometheus API时出错: {e}")
    except Exception as e:
        print(f"处理数据时出错: {e}")
        
        return None


def collect_prometheus_metrics(metric_name, start_time=None, end_time=None, step='1m', prometheus_url='http://localhost:9090'):
    """
    从Prometheus采集指定指标的历史数据并保存到硬盘
    
    参数:
        metric_name (str): 要采集的指标名称
        start_time (datetime, optional): 开始时间，默认为1小时前
        end_time (datetime, optional): 结束时间，默认为当前时间
        step (str, optional): 采样步长，默认为1分钟
        prometheus_url (str, optional): Prometheus服务器URL
    
    返回:
        str: 保存的文件路径
    """
    # 设置默认时间范围
    if end_time is None:
        end_time = datetime.now()
    if start_time is None:
        start_time = end_time - timedelta(hours=1)
    
    # 转换为Prometheus API所需的时间格式
    start_time_str = start_time.isoformat("T") + "Z"
    end_time_str = end_time.isoformat("T") + "Z"
    
    # 构建API请求URL
    query_url = f"{prometheus_url}/api/v1/query_range"
    params = {
        'query': metric_name,
        'start': start_time_str,
        'end': end_time_str,
        'step': step
    }
    
    try:
        # 发送请求获取数据
        response = requests.get(query_url, params=params)
        response.raise_for_status()  # 如果请求失败则抛出异常
        
        data = response.json()
        
        # 检查响应状态
        if data['status'] != 'success':
            raise Exception(f"Prometheus API返回错误: {data.get('error', '未知错误')}")
        
        # 提取结果数据
        result_data = data['data']['result']
        
        if not result_data:
            print(f"警告: 指标 '{metric_name}' 没有返回任何数据")
            return None
        
        # 创建保存目录
        save_dir = 'prometheus_data'
        os.makedirs(save_dir, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_metric_name = metric_name.replace("{", "_").replace("}", "_").replace(":", "_")
        filename = f"{save_dir}/{safe_metric_name}_{timestamp}.csv"
        
        # 将数据转换为DataFrame并保存
        all_dfs = []
        for result in result_data:
            # 提取标签信息
            metric_labels = result['metric']
            
            # 提取时间序列数据
            values = result['values']  # 格式为 [timestamp, value]
            
            # 创建DataFrame
            df = pd.DataFrame(values, columns=['timestamp', 'value'])
            
            # 转换时间戳为可读格式
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            
            # 转换值为数值类型
            df['value'] = pd.to_numeric(df['value'])
            
            # 添加标签列
            for label_key, label_value in metric_labels.items():
                df[label_key] = label_value
                
            all_dfs.append(df)
        
        # 合并所有结果
        if len(all_dfs) > 1:
            final_df = pd.concat(all_dfs, ignore_index=True)
        else:
            final_df = all_dfs[0]
        
        # 保存到CSV文件
        final_df.to_csv(filename, index=False)
        print(f"数据已保存到: {filename}")
        
        return filename
        
    except requests.exceptions.RequestException as e:
        print(f"请求Prometheus API时出错: {e}")
    except Exception as e:
        print(f"处理数据时出错: {e}")
    
    return None

# 使用示例
# if __name__ == "__main__":
#     # 采集过去一小时的查询命令数据
#     # end_time = datetime.now()
#     # start_time = end_time - timedelta(hours=1)
#     # query_prometheus(
#     #     query=query_command,
#     #     start_time=start_time,
#     #     end_time=end_time,
#     #     step='30s'
#     # )
#     test()

if __name__ == "__main__":
    main()
