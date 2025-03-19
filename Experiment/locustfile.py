import os
import time
import json
import configparser
from locust import HttpUser, task, between, events, constant_throughput
from locust.exception import StopUser
import logging
from locust import LoadTestShape

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

trace_file = 'traces/scaled_diurnal.txt'
multiplier = 1

# 读取配置文件
# def load_config(config_file='config.conf'):
#     """从配置文件中读取配置，返回配置字典"""
#     config = {}
#     try:
#         with open(config_file, 'r') as f:
#             for line in f:
#                 line = line.strip()
#                 if line and not line.startswith('#'):
#                     key, value = line.split('=', 1)
#                     config[key.strip()] = value.strip()
#         logger.info(f"已从{config_file}加载配置")
#     except Exception as e:
#         logger.warning(f"读取配置文件出错: {e}，将使用默认配置")
#     return config

# # 加载配置
# config = load_config()



# 存储统计信息
stats = []
local_latency_stats = []

# 当前用户数

# 读取负载文件
def load_trace_file(file_path):
    """读取负载文件，返回每秒请求数列表"""
    try:
        with open(file_path, 'r') as f:
            trace_data = [int(float(line.strip())) for line in f if line.strip()]
            # 每隔12个选一个数据
            trace_data = trace_data[::2]
            trace_data = [int(x * multiplier) for x in trace_data]
            return trace_data
    except Exception as e:
        logger.error(f"读取负载文件出错: {e}")
        return [1]  # 默认负载

# 负载数据
# trace_data = load_trace_file(TRACE_FILE)
# logger.info(f"已加载负载文件，共{len(trace_data)}个数据点")

class CustomLoadShape(LoadTestShape):
    """自定义负载形状"""
    
    def __init__(self):
        super().__init__()
        self.trace_data = load_trace_file(trace_file)
    
    def tick(self):
        run_time = self.get_run_time()
        run_time = int(run_time)
        """返回当前时刻的用户数和生成率"""
        if run_time >= len(self.trace_data):
            return None
        
        target_users = self.trace_data[run_time]
        
        return (
            int(target_users),
            int(target_users)  # 生成率设置为与用户数相同
        )

# 测试开始时的事件处理
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始时的处理函数"""
    logger.info("开始负载测试")
    # logger.info(f"目标主机: {TARGET_HOST}")
    # logger.info(f"服务路径: {SERVICE_PATH}")
    # logger.info(f"负载文件: {TRACE_FILE}")

# 测试停止时的事件处理
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时的处理函数"""
    logger.info("负载测试结束")
    
    # 计算统计信息
    if local_latency_stats:
        avg_latency = sum(local_latency_stats) / len(local_latency_stats)
        logger.info(f"平均延迟: {avg_latency:.2f}ms")
        logger.info(f"总请求数: {len(local_latency_stats)}")
    
    # 保存统计信息到文件
    if stats:
        os.makedirs("Experiment/locust_dir", exist_ok=True)
        with open("Experiment/locust_dir/locust_results.txt", "w") as f:
            f.writelines("\n".join(stats))
        logger.info("已保存结果到 locust_results.txt")

# 定义用户行为
class MuBenchUser(HttpUser):
    # wait_time = between(0.001, 0.005)  # 由LoadTestShape完全控制生成率
    wait_time = constant_throughput(1)
    # fixed_count = 1
    
    
    def on_start(self):
        """用户启动时的初始化"""
        pass
    
    @task
    def access_service(self):
        """发送请求到服务"""
        # start_time = time.time()
        # now_ms = int(start_time * 1000)
        
        try:
            # 发送请求
            response = self.client.get(f"/s0")
            
            # 计算延迟
            # req_latency_ms = int((time.time() - start_time) * 1000)
            
            # 记录统计信息
            # stats.append(f"{now_ms} \t {req_latency_ms} \t {response.status_code} \t {len(stats) + 1}")
            # local_latency_stats.append(req_latency_ms)
            
            # 定期输出状态
            # if len(stats) % 100 == 0:
            #     logger.info(f"已处理请求: {len(stats)}, 延迟: {req_latency_ms}ms")
                
        except Exception as e:
            logger.error(f"请求出错: {e}")