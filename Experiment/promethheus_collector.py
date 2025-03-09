import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta

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
if __name__ == "__main__":
    # 采集CPU使用率指标的过去2小时数据
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)
    collect_prometheus_metrics(
        metric_name="node_cpu_seconds_total{mode='idle'}",
        start_time=start_time,
        end_time=end_time,
        step='15s',
        prometheus_url='http://localhost:30000'
    )
