# 自定义调度器容器化部署指南

本文档提供了将`LeastReplicaFirst`自定义调度器容器化并部署到Kubernetes集群的完整命令序列。

## 1. 构建容器镜像

首先，确保您位于包含调度器代码的目录中：

```bash
# 切换到Experiment目录
cd /path/to/muBench/Experiment
```

构建Docker镜像：

```bash
# 构建镜像
docker build -t least-replica-first-scheduler:latest .
```

## 2. 镜像处理选项

### 选项A：使用本地镜像（适用于单节点集群或测试环境）

如果您在单节点集群上测试，可以直接使用本地构建的镜像，无需推送到镜像仓库。

### 选项B：推送到镜像仓库（适用于多节点集群）

对于多节点集群，需要将镜像推送到可访问的镜像仓库：

```bash
# 标记镜像
docker tag least-replica-first-scheduler:latest <your-registry>/least-replica-first-scheduler:latest

# 登录到镜像仓库
docker login <your-registry>

# 推送镜像
docker push <your-registry>/least-replica-first-scheduler:latest
```

> 注意：如果使用镜像仓库，需要修改`scheduler-deployment.yaml`中的镜像地址为`<your-registry>/least-replica-first-scheduler:latest`

## 3. 部署RBAC权限

应用RBAC配置，为调度器创建必要的权限：

```bash
kubectl apply -f scheduler-rbac.yaml
```

这将创建：
- 名为`least-replica-first-scheduler`的ServiceAccount
- 具有必要权限的ClusterRole
- 将ServiceAccount与ClusterRole绑定的ClusterRoleBinding

## 4. 部署调度器

应用调度器的Deployment配置：

```bash
kubectl apply -f scheduler-deployment.yaml
```

## 5. 验证部署

检查调度器是否成功部署并运行：

```bash
# 检查Pod状态
kubectl get pods -n kube-system -l app=least-replica-first-scheduler

# 查看调度器日志
kubectl logs -n kube-system -l app=least-replica-first-scheduler
```

## 6. 使用自定义调度器

要使用此调度器调度Pod，在Pod或Deployment的spec中添加以下字段：

```yaml
spec:
  schedulerName: least-replica-first-scheduler
```

## 7. 故障排除

如果调度器无法正常工作，请检查：

1. 调度器Pod是否正常运行
2. 查看调度器日志中是否有错误信息
3. 确认RBAC权限配置是否正确
4. 验证镜像是否可以被Kubernetes节点访问

## 8. 清理资源

如需删除调度器及其相关资源：

```bash
# 删除调度器Deployment
kubectl delete -f scheduler-deployment.yaml

# 删除RBAC配置
kubectl delete -f scheduler-rbac.yaml
```