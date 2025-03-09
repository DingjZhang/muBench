#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse
import logging
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('UpdateScheduler')

def run_command(command, shell=False):
    """
    执行命令并返回结果
    
    Args:
        command: 要执行的命令（字符串或列表）
        shell: 是否使用shell执行
        
    Returns:
        subprocess.CompletedProcess: 命令执行结果
    """
    try:
        logger.info(f"执行命令: {command if isinstance(command, str) else ' '.join(command)}")
        result = subprocess.run(
            command,
            shell=shell,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"命令执行成功")
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"命令执行失败: {e}")
        logger.error(f"错误输出: {e.stderr}")
        raise

def build_docker_image(image_name, tag, dockerfile_path=".", scheduler_dir=None):
    """
    构建Docker镜像
    
    Args:
        image_name: 镜像名称
        tag: 镜像标签
        dockerfile_path: Dockerfile路径
        scheduler_dir: 调度器目录路径
    """
    logger.info(f"开始构建Docker镜像: {image_name}:{tag}")
    full_image_name = f"{image_name}:{tag}"
    
    # 如果提供了调度器目录，则使用该目录作为Dockerfile路径
    if scheduler_dir:
        dockerfile_path = scheduler_dir
    
    try:
        run_command(["docker", "build", "-t", full_image_name, dockerfile_path])
        logger.info(f"Docker镜像构建成功: {full_image_name}")
    except Exception as e:
        logger.error(f"Docker镜像构建失败: {e}")
        sys.exit(1)

def push_docker_image(image_name, tag, registry):
    """
    推送Docker镜像到仓库
    
    Args:
        image_name: 镜像名称
        tag: 镜像标签
        registry: 镜像仓库地址
    """
    local_image = f"{image_name}:{tag}"
    registry_image = f"{registry}/{image_name}:{tag}"
    
    logger.info(f"标记镜像: {local_image} -> {registry_image}")
    try:
        # 标记镜像
        run_command(["docker", "tag", local_image, registry_image])
        
        # 推送镜像
        logger.info(f"推送镜像到仓库: {registry_image}")
        run_command(["docker", "push", registry_image])
        logger.info(f"镜像推送成功: {registry_image}")
    except Exception as e:
        logger.error(f"镜像推送失败: {e}")
        sys.exit(1)

def update_deployment_image(deployment_file, registry, image_name, tag):
    """
    更新部署文件中的镜像地址
    
    Args:
        deployment_file: 部署文件路径
        registry: 镜像仓库地址
        image_name: 镜像名称
        tag: 镜像标签
    """
    logger.info(f"更新部署文件中的镜像地址: {deployment_file}")
    new_image = f"{registry}/{image_name}:{tag}"
    
    try:
        # 读取部署文件
        with open(deployment_file, 'r') as f:
            content = f.read()
        
        # 查找并替换镜像地址
        import re
        pattern = r'image:\s*[^\n]+'
        new_content = re.sub(pattern, f'image: {new_image}', content)
        
        # 写回部署文件
        with open(deployment_file, 'w') as f:
            f.write(new_content)
            
        logger.info(f"部署文件更新成功，新镜像地址: {new_image}")
    except Exception as e:
        logger.error(f"更新部署文件失败: {e}")
        sys.exit(1)

def delete_scheduler(deployment_file):
    """
    删除现有的调度器部署
    
    Args:
        namespace: 命名空间
        scheduler_name: 调度器名称
    """
    logger.info(f"删除现有的调度器部署: {deployment_file}")
    try:
        # 使用 kubectl delete -f 命令删除调度器
        run_command(["kubectl", "delete", "-f", deployment_file])
        logger.info(f"调度器删除成功")
        # 等待Pod完全终止
        logger.info("等待Pod完全终止...")
        time.sleep(5)
    except Exception as e:
        logger.error(f"删除调度器失败: {e}")
        # 继续执行，因为可能是首次部署
        logger.warning("继续执行部署步骤...")


def deploy_scheduler(deployment_file, rbac_file=None, namespace="kube-system"):
    """
    部署调度器
    
    Args:
        deployment_file: 部署文件路径
        rbac_file: RBAC文件路径
        namespace: 命名空间
    """
    # 如果提供了RBAC文件，先应用RBAC配置
    if rbac_file:
        logger.info(f"应用RBAC配置: {rbac_file}")
        try:
            run_command(["kubectl", "apply", "-f", rbac_file])
            logger.info("RBAC配置应用成功")
        except Exception as e:
            logger.error(f"应用RBAC配置失败: {e}")
            sys.exit(1)
    
    # 部署调度器
    logger.info(f"部署调度器: {deployment_file}")
    try:
        run_command(["kubectl", "apply", "-f", deployment_file])
        logger.info("调度器部署成功")
    except Exception as e:
        logger.error(f"部署调度器失败: {e}")
        sys.exit(1)

def verify_deployment(namespace="kube-system", scheduler_name="least-replica-first-scheduler", timeout=60):
    """
    验证调度器部署是否成功
    
    Args:
        namespace: 命名空间
        scheduler_name: 调度器名称
        timeout: 超时时间（秒）
    """
    logger.info(f"验证调度器部署: {scheduler_name} (命名空间: {namespace})")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 检查Pod状态
            result = run_command(["kubectl", "get", "pods", "-n", namespace, "-l", f"app={scheduler_name}", "-o", "jsonpath={.items[0].status.phase}"])
            status = result.stdout.strip()
            
            if status == "Running":
                logger.info(f"调度器已成功部署并运行")
            #     # 显示调度器日志
            #     try:
            #         log_result = run_command(["kubectl", "logs", "-n", namespace, "-l", f"app={scheduler_name}", "--tail=10"])
            #         logger.info("调度器日志（最后10行）:")
            #         for line in log_result.stdout.strip().split('\n'):
            #             print(f"  {line}")
            #     except:
            #         logger.warning("无法获取调度器日志")
                return True
            
            # logger.info(f"调度器状态: {status}，等待变为Running...")
            time.sleep(5)
        except Exception as e:
            logger.warning(f"检查调度器状态时出错: {e}")
            time.sleep(5)
    
    logger.error(f"调度器部署验证超时，请手动检查状态")
    return False

def main():
    parser = argparse.ArgumentParser(description='更新Kubernetes自定义调度器')
    # 添加调度器存储目录参数
    parser.add_argument('--scheduler-dir', default='LeastReplicaFirst', help='调度器数据存储目录路径')
    parser.add_argument('--image-name', default='least-replica-first-scheduler', help='Docker镜像名称')
    parser.add_argument('--tag', default='latest', help='Docker镜像标签')
    parser.add_argument('--registry', default='civildocker', help='Docker镜像仓库地址')
    parser.add_argument('--namespace', default='kube-system', help='Kubernetes命名空间')
    parser.add_argument('--deployment-file', default='scheduler-deployment.yaml', help='调度器部署文件路径')
    parser.add_argument('--rbac-file', default='scheduler-rbac.yaml', help='RBAC配置文件路径')
    parser.add_argument('--skip-build', action='store_true', help='跳过构建镜像步骤')
    parser.add_argument('--skip-push', action='store_true', help='跳过推送镜像步骤')
    parser.add_argument('--skip-verify', action='store_true', help='跳过验证部署步骤')
    
    args = parser.parse_args()
    
    # 确保调度器目录路径是绝对路径
    scheduler_dir = os.path.abspath(args.scheduler_dir)
    
    # 构建部署文件和RBAC文件的完整路径
    deployment_file = os.path.join(scheduler_dir, args.deployment_file)
    rbac_file = os.path.join(scheduler_dir, args.rbac_file) if args.rbac_file else None
    
    # 构建Docker镜像
    if not args.skip_build:
        build_docker_image(args.image_name, args.tag, scheduler_dir=scheduler_dir)
    
    # 推送Docker镜像到仓库
    if not args.skip_push:
        push_docker_image(args.image_name, args.tag, args.registry)
    
    # 更新部署文件中的镜像地址
    # update_deployment_image(deployment_file, args.registry, args.image_name, args.tag)
    
    # 删除现有的调度器部署
    delete_scheduler(deployment_file)
    
    # 部署调度器
    deploy_scheduler(deployment_file, rbac_file, args.namespace)
    
    # 验证部署
    if not args.skip_verify:
        verify_deployment(args.namespace, args.image_name)
    
    logger.info("调度器更新完成")

if __name__ == "__main__":
    main()