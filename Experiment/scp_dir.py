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

def main():
    # 设置域名变量
    master_domain_name = "pc75.cloudlab.umass.edu"
    worker1_domain_name = "pc74.cloudlab.umass.edu"
    worker2_domain_name = "pc98.cloudlab.umass.edu"
    worker3_domain_name = "pc63.cloudlab.umass.edu"
    worker4_domain_name = "pc83.cloudlab.umass.edu"
    
    # 定义要发送的文件夹路径
    source_dir = r"D:\adaptation\muBench\Experiment"
    target_dir = "~/Experiment"
    username = "Dingjie"
    
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
            content = re.sub(r'WORKER3_DOMAIN_NAME=".*?"', f'WORKER3_DOMAIN_NAME="{worker3_domain_name}"', content)
            content = re.sub(r'WORKER4_DOMAIN_NAME=".*?"', f'WORKER4_DOMAIN_NAME="{worker4_domain_name}"', content)
            
            # 转换为 Unix 格式（LF 换行符）
            content = content.replace('\r\n', '\n')
            
            # 写回文件
            with open(script_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
    
    print("域名变量更新和格式转换完成！")
    
    # 使用 scp 将文件夹发送到所有 worker 服务器
    servers = [
        worker1_domain_name,
        worker2_domain_name,
        worker3_domain_name,
        worker4_domain_name,
        master_domain_name
    ]
    
    for server in servers:
        print(f"正在发送文件到 {server}...")
        subprocess.run(["scp", "-r", source_dir, f"{username}@{server}:{target_dir}"])
    
    # 压缩并发送整个 muBench 目录到 master 服务器
    print(f"正在发送文件到 {master_domain_name}...")
    mubench_dir = r"D:\adaptation\muBench"
    
    # 创建临时目录
    temp_dir = os.path.join(tempfile.gettempdir(), "mubench_temp")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    print(temp_dir)
    
    print("正在复制文件...")
    
    # 复制所有非隐藏文件和文件夹到临时目录
    for item in os.listdir(mubench_dir):
        if not item.startswith('.'):
            src_path = os.path.join(mubench_dir, item)
            dst_path = os.path.join(temp_dir, item)
            
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)

    
    # 创建压缩文件名（使用时间戳避免重名）
    archive_name = "mubench.zip"
    archive_path = os.path.join(temp_dir, archive_name)
    
    print("正在压缩文件...")
    
    # 压缩文件
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file != archive_name:  # 避免将压缩文件本身添加到压缩包中
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
    
    # 传输压缩文件到目标服务器
    print(f"正在传输压缩文件到 {master_domain_name}...")
    subprocess.run(["scp", archive_path, f"{username}@{master_domain_name}:~/"])
    
    # 清理临时文件
    shutil.rmtree(temp_dir)
    
    print("所有文件传输完成！")

if __name__ == "__main__":
    main()