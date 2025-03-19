#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import re
import shutil
import tempfile
import subprocess
import zipfile
import glob
import argparse

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='将文件发送到服务器')
    parser.add_argument('--master', action='store_true', help='只向master服务器发送文件')
    parser.add_argument('--update', action='store_true', help='更新脚本中的域名变量')
    args = parser.parse_args()
    # 设置域名变量
    master_domain_name = "c220g5-111030.wisc.cloudlab.us"
    worker1_domain_name = "c220g5-111032.wisc.cloudlab.us"
    worker2_domain_name = "clnode251.clemson.cloudlab.us"
    # worker3_domain_name = "pc85.cloudlab.umass.edu"
    # worker4_domain_name = "pc83.cloudlab.umass.edu"
    load_gen_domain_name = "c220g5-111012.wisc.cloudlab.us"
    
    # 定义要发送的文件夹路径
    # source_dir = r"D:\adaptation\muBench\Experiment"
    source_dir = "/mnt/d/adaptation/muBench/Experiment"
    all_source_file_dir = "/mnt/d/adaptation/muBench"
    target_dir = "~/Experiment"
    username = "Dingjie"
    
    if args.update:
        print("正在更新脚本中的域名变量...")
        
        # 更新 shell 脚本中的域名变量
        shell_scripts = ["master.sh", "worker.sh", "tc.sh"]
        for script in shell_scripts:
            script_path = os.path.join(source_dir, script)
            if os.path.exists(script_path):
                # 读取文件内容
                with open(script_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 替换域名变量
                content = re.sub(r'MASTER_DOMAIN_NAME=".*?"', f'MASTER_DOMAIN_NAME="{master_domain_name}"', content)
                content = re.sub(r'WORKER1_DOMAIN_NAME=".*?"', f'WORKER1_DOMAIN_NAME="{worker1_domain_name}"', content)
                content = re.sub(r'WORKER2_DOMAIN_NAME=".*?"', f'WORKER2_DOMAIN_NAME="{worker2_domain_name}"', content)
                # content = re.sub(r'WORKER3_DOMAIN_NAME=".*?"', f'WORKER3_DOMAIN_NAME="{worker3_domain_name}"', content)
                # content = re.sub(r'WORKER4_DOMAIN_NAME=".*?"', f'WORKER4_DOMAIN_NAME="{worker4_domain_name}"', content)
                content = re.sub(r'LOAD_GEN_DOMAIN_NAME=".*?"', f'LOAD_GEN_DOMAIN_NAME="{load_gen_domain_name}"', content)
                # 转换为 Unix 格式（LF 换行符）
                content = content.replace('\r\n', '\n')
                
                # 写回文件
                with open(script_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)

        locust_conf_file = os.path.join(source_dir, "locust.conf")
        if os.path.exists(locust_conf_file):
            # 获取master服务器的IP地址
            try:
                master_ip = subprocess.check_output(["dig", "+short", master_domain_name]).decode().strip()

                # 读取locust.conf文件内容
                with open(locust_conf_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 使用正则表达式替换IP地址
                content = re.sub(r'host = http://\d+\.\d+\.\d+\.\d+:31113', f'host = http://{master_ip}:31113', content)

                # 写回文件
                with open(locust_conf_file, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)

                print(f"已更新locust.conf中的master IP地址为: {master_ip}")
            except subprocess.CalledProcessError as e:
                print(f"获取master IP地址失败: {str(e)}")
            except Exception as e:
                print(f"更新locust.conf文件失败: {str(e)}")


                print("域名变量更新和格式转换完成！")

                print("正在将shell脚本转换为Unix格式...")

        # 获取source_dir中所有.sh结尾的文件
        shell_files = glob.glob(os.path.join(source_dir, "*.sh"))

        # 对每个shell脚本执行dos2unix转换
        for shell_file in shell_files:
            try:
                # 使用subprocess调用dos2unix命令
                subprocess.run(["dos2unix", shell_file], check=True)
                print(f"成功转换文件: {shell_file}")
            except subprocess.CalledProcessError as e:
                print(f"转换文件失败 {shell_file}: {str(e)}")
            except FileNotFoundError:
                print("错误: 未找到dos2unix命令，请确保已安装")
                sys.exit(1)
        
        print("shell脚本格式转换完成！")
    
    # 根据命令行参数决定发送文件的目标服务器
    if args.master:
        # 只向master服务器发送文件
        print(f"--master选项已启用，只向master服务器发送文件")
        print(f"正在发送文件到 {master_domain_name}...")
        # 使用rsync的--exclude选项排除以.开头的文件和文件夹
        subprocess.run(["rsync", "-avzhP", "--exclude=.*", all_source_file_dir, f"{username}@{master_domain_name}:~/"])
    else:
        # 使用 scp 将文件夹发送到所有 worker 服务器
        worker_servers = [
            worker1_domain_name,
            worker2_domain_name
            # worker3_domain_name,
            # worker4_domain_name
        ]
        
        for server in worker_servers:
            print(f"正在发送文件到 {server}...")
            subprocess.run(["rsync", "-avzhP", source_dir, f"{username}@{server}:~/"])

        master_servers = [
            master_domain_name,
            load_gen_domain_name
        ]
        for server in master_servers:
            print(f"正在发送文件到 {server}...")
            # 使用rsync的--exclude选项排除以.开头的文件和文件夹
            subprocess.run(["rsync", "-avzhP", "--exclude=.*", all_source_file_dir, f"{username}@{server}:~/"])

    # # 压缩并发送整个 muBench 目录到 master 服务器
    # print(f"正在发送文件到 {master_domain_name}...")
    # # mubench_dir = r"D:\adaptation\muBench"
    # mubench_dir = "/mnt/d/adaptation/muBench"
    
    # # 创建临时目录
    # temp_dir = os.path.join(tempfile.gettempdir(), "mubench_temp")
    # if os.path.exists(temp_dir):
    #     shutil.rmtree(temp_dir)
    # os.makedirs(temp_dir)
    # print(temp_dir)
    
    # print("正在复制文件...")
    
    # # 复制所有非隐藏文件和文件夹到临时目录
    # for item in os.listdir(mubench_dir):
    #     if not item.startswith('.'):
    #         src_path = os.path.join(mubench_dir, item)
    #         dst_path = os.path.join(temp_dir, item)
            
    #         if os.path.isdir(src_path):
    #             shutil.copytree(src_path, dst_path)
    #         else:
    #             shutil.copy2(src_path, dst_path)

    
    # # 创建压缩文件名（使用时间戳避免重名）
    # archive_name = "mubench.zip"
    # archive_path = os.path.join(temp_dir, archive_name)
    
    # print("正在压缩文件...")
    
    # # 压缩文件
    # with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    #     for root, dirs, files in os.walk(temp_dir):
    #         for file in files:
    #             if file != archive_name:  # 避免将压缩文件本身添加到压缩包中
    #                 file_path = os.path.join(root, file)
    #                 arcname = os.path.relpath(file_path, temp_dir)
    #                 zipf.write(file_path, arcname)
    
    # # 传输压缩文件到目标服务器
    # print(f"正在传输压缩文件到 {master_domain_name}...")
    # subprocess.run(["scp", archive_path, f"{username}@{master_domain_name}:~/"])
    # subprocess.run(["scp", archive_path, f"{username}@{load_gen_domain_name}:~/"])

    # # 清理临时文件
    # shutil.rmtree(temp_dir)
    
    print("所有文件传输完成！")

if __name__ == "__main__":
    main()