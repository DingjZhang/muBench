import pandas as pd
import schedule
import time
import os
import requests
from datetime import datetime
from kubernetes import client, config

query_command = "sum by (s0) (increase(mub_request_processing_latency_milliseconds_sum{}[2m])) / sum by (s0) (increase(mub_request_processing_latency_milliseconds_count{}[2m]))"
prometheus_url = "http://localhost:30000"

index = 0
result_dict = {'latency': [], 'node1': [], 'node2': []}

def collect_data():
    global index
    try:
        # 获取当前时间戳
        timestamp = datetime.now().isoformat()
        
        # 加载Kubernetes配置
        config.load_kube_config()
        v1 = client.CoreV1Api()
        
        # 获取Pod信息
        pod_list = v1.list_namespaced_pod(namespace='default')
        current_pods = {}
        for pod in pod_list.items:
            pod_name = pod.metadata.name
            node_name = pod.spec.node_name
            current_pods[pod_name] = {
                'node': node_name,
                'status': pod.status.phase,
                'start_time': pod.status.start_time.isoformat()
            }
        
        # 执行Prometheus查询
        response = requests.get(f"{prometheus_url}/api/v1/query", params={'query': query_command})
        prom_data = response.json()['data']['result']
        
        # 计算平均延迟
        avg_latency = sum(float(r['value'][1]) for r in prom_data)/len(prom_data) if prom_data else 0
        
        # 创建包含Pod分布信息的DataFrame
        pod_data = []
        for pod_name, pod_info in current_pods.items():
            pod_data.append({
                'index': index,
                'timestamp': timestamp,
                'pod_name': pod_name,
                'node_name': pod_info['node'],
                'pod_status': pod_info['status'],
                'pod_start_time': pod_info['start_time'],
                'pod_count': len(current_pods),
                'avg_latency': avg_latency
            })
        
        # 创建合并的DataFrame
        combined_df = pd.DataFrame(pod_data)
        
        # 保存到单个CSV文件
        os.makedirs('collected_data', exist_ok=True)
        combined_df.to_csv(f'collected_data/combined_data_{index}_{timestamp[:10]}.csv', index=False)
        
        print(f"已保存合并数据到: collected_data/combined_data_{index}_{timestamp[:10]}.csv")
        
        index += 1
        
    except Exception as e:
        print(f"采集数据时发生错误: {e}")

# 设置定时任务（示例：每5分钟执行一次）
schedule.every(5).minutes.do(collect_data)

# 主循环
if __name__ == '__main__':
    while True:
        schedule.run_pending()
        time.sleep(1)

