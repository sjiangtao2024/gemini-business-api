# 部署和运维指南

> 版本：v1.0
> 日期：2025-01-31

## 📋 概述

本文档提供 Gemini Business API 在树莓派5上的完整部署和运维指南。

**目标环境：**
- 硬件：树莓派5（4GB+ 内存推荐）
- 系统：Raspberry Pi OS / Ubuntu Server
- 部署方式：Docker + docker-compose
- 使用场景：个人使用

---

## 🔧 环境准备

### 1. 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| CPU | 树莓派5（4核心） | 树莓派5 |
| 内存 | 2GB | 4GB+ |
| 存储 | 8GB | 16GB+ |
| 系统 | Raspberry Pi OS Lite | Raspberry Pi OS (64-bit) |

### 2. 软件依赖

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 添加当前用户到 docker 组（避免每次 sudo）
sudo usermod -aG docker $USER
newgrp docker

# 安装 Docker Compose
sudo apt install docker-compose -y

# 验证安装
docker --version
docker-compose --version
```

### 3. 安装 Git

```bash
sudo apt install git -y
git --version
```

---

## 📦 部署步骤

### 方式一：使用 docker-compose（推荐）

#### 1. 克隆项目

```bash
# 创建工作目录
mkdir -p ~/apps
cd ~/apps

# 克隆项目（替换为你的仓库地址）
git clone https://github.com/yourusername/gemini-business-api.git
cd gemini-business-api
```

#### 2. 配置账号

```bash
# 创建配置目录
mkdir -p config

# 创建账号配置文件
nano config/accounts.json
```

**粘贴配置内容：**
```json
{
  "accounts": [
    {
      "team_id": "你的team_id",
      "secure_c_ses": "你的__Secure-c-SES",
      "host_c_oses": "你的__Host-c-OSES",
      "csesidx": "你的csesidx",
      "user_agent": "你的User-Agent"
    }
  ],
  "settings": {
    "token_refresh_interval_hours": 11,
    "account_expire_warning_days": 28,
    "check_interval_minutes": 30,
    "cooldown_401_seconds": 7200,
    "cooldown_403_seconds": 7200,
    "cooldown_429_seconds": 14400
  }
}
```

#### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑环境变量
nano .env
```

**.env 内容：**
```bash
# 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_LEVEL=INFO

# 服务端口
PORT=8000

# 可选：API 访问密钥（留空则公开访问）
API_KEY=

# 可选：图片输出格式（base64/url）
IMAGE_OUTPUT_FORMAT=url

# 可选：视频输出格式（html/url/markdown）
VIDEO_OUTPUT_FORMAT=html
```

#### 4. 启动服务

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart
```

#### 5. 验证部署

```bash
# 检查容器状态
docker-compose ps

# 测试 API
curl http://localhost:8000/health

# 测试 OpenAI 兼容接口
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

---

### 方式二：手动部署（不使用 Docker）

```bash
# 安装 Python 3.11
sudo apt install python3.11 python3.11-venv python3-pip -y

# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置账号（同上）
mkdir -p config
nano config/accounts.json

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 后台运行（使用 screen 或 tmux）
screen -S gemini-api
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 按 Ctrl+A, D 离开 screen

# 恢复 screen
screen -r gemini-api
```

---

## 🐳 Docker 配置详解

### Dockerfile

```dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（如需要）
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  gemini-api:
    build: .
    container_name: gemini-business-api
    restart: unless-stopped

    ports:
      - "8000:8000"

    volumes:
      # 配置文件（支持热重载）
      - ./config:/app/config

      # 日志持久化（可选）
      - ./logs:/app/logs

    environment:
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - API_KEY=${API_KEY:-}
      - IMAGE_OUTPUT_FORMAT=${IMAGE_OUTPUT_FORMAT:-url}
      - VIDEO_OUTPUT_FORMAT=${VIDEO_OUTPUT_FORMAT:-html}

    # 资源限制（树莓派5推荐）
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M

    # 健康检查
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

# 可选：使用网络桥接
networks:
  default:
    name: gemini-api-network
```

---

## 🔄 更新和维护

### 1. 更新代码

```bash
cd ~/apps/gemini-business-api

# 拉取最新代码
git pull origin main

# 重新构建并启动
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 查看日志确认启动成功
docker-compose logs -f
```

### 2. 更新配置（热重载）

```bash
# 编辑配置文件
nano config/accounts.json

# 保存后自动重载，无需重启服务
# 查看重载日志
docker-compose logs -f | grep CONFIG
```

### 3. 备份配置

```bash
# 创建备份脚本
cat > ~/backup-gemini-config.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=~/gemini-backups
mkdir -p $BACKUP_DIR

# 备份配置文件
cp ~/apps/gemini-business-api/config/accounts.json \
   $BACKUP_DIR/accounts_$DATE.json

# 只保留最近7天的备份
find $BACKUP_DIR -name "accounts_*.json" -mtime +7 -delete

echo "Backup completed: accounts_$DATE.json"
EOF

chmod +x ~/backup-gemini-config.sh

# 添加定时任务（每天凌晨2点备份）
crontab -e
# 添加：0 2 * * * /home/pi/backup-gemini-config.sh
```

### 4. 日志管理

```bash
# 查看实时日志
docker-compose logs -f

# 查看最近100行日志
docker-compose logs --tail=100

# 查看特定时间的日志
docker-compose logs --since="2025-01-31T10:00:00"

# 日志轮转（防止日志文件过大）
# 在 docker-compose.yml 中添加：
services:
  gemini-api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 📊 监控和调试

### 1. 健康检查

```bash
# 检查服务健康状态
curl http://localhost:8000/health

# 预期响应
{
  "status": "healthy",
  "timestamp": "2025-01-31T10:00:00",
  "accounts": {
    "total": 3,
    "active": 2,
    "cooldown": 1
  }
}
```

### 2. 账号状态监控

```bash
# 查看账号池状态（需实现管理 API）
curl http://localhost:8000/admin/accounts

# 预期响应
{
  "accounts": [
    {
      "team_id": "1d468dcc...",
      "status": "active",
      "token_expires_in": 39600,
      "cooldown_remaining": 0,
      "requests_count": 123
    }
  ]
}
```

### 3. 性能监控

```bash
# 查看容器资源占用
docker stats gemini-business-api

# 输出示例
CONTAINER           CPU %     MEM USAGE / LIMIT     MEM %     NET I/O
gemini-business-api 5.23%     256MiB / 1GiB        25.00%    1.2MB / 3.4MB
```

### 4. 调试模式

```bash
# 临时启用调试日志
docker-compose down
echo "LOG_LEVEL=DEBUG" >> .env
docker-compose up -d

# 查看详细日志
docker-compose logs -f

# 恢复正常日志级别
sed -i 's/LOG_LEVEL=DEBUG/LOG_LEVEL=INFO/' .env
docker-compose restart
```

---

## 🚨 常见问题排查

### 问题 1：容器无法启动

**症状：**
```bash
docker-compose ps
# 显示 Exit 1 或 Restarting
```

**排查步骤：**
```bash
# 1. 查看完整日志
docker-compose logs

# 2. 检查配置文件是否存在
ls -la config/accounts.json

# 3. 验证 JSON 格式
cat config/accounts.json | python3 -m json.tool

# 4. 检查端口占用
sudo netstat -tlnp | grep 8000

# 5. 重新构建
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### 问题 2：Token 刷新失败

**症状：**
```
[TOKEN] 账号 1d468dcc Token刷新失败: 401 Unauthorized
```

**解决方案：**
```bash
# 1. 重新获取 Cookie
# 登录 Gemini Business，更新配置文件

# 2. 检查账号是否过期（30天限制）
# 查看日志中的账号添加时间

# 3. 更新配置
nano config/accounts.json
# 保存后自动重载
```

### 问题 3：请求返回 503

**症状：**
```json
{"error": "No available accounts"}
```

**解决方案：**
```bash
# 1. 检查账号状态
docker-compose logs | grep ACCOUNT

# 2. 检查是否所有账号都在冷却期
# 等待冷却期结束，或添加新账号

# 3. 检查配置文件是否正确加载
docker-compose logs | grep CONFIG
```

### 问题 4：内存占用过高

**症状：**
```bash
docker stats
# 显示内存占用 > 1GB
```

**解决方案：**
```bash
# 1. 限制容器内存（docker-compose.yml）
deploy:
  resources:
    limits:
      memory: 512M

# 2. 重启容器
docker-compose restart

# 3. 清理 Docker 缓存
docker system prune -a
```

### 问题 5：配置热重载不生效

**症状：**
修改 `accounts.json` 后没有重载日志

**解决方案：**
```bash
# 1. 检查 volume 挂载
docker-compose config | grep volumes

# 2. 检查文件权限
ls -la config/accounts.json

# 3. 手动触发重载（编辑后保存）
touch config/accounts.json

# 4. 查看 watchdog 日志
docker-compose logs | grep watchdog
```

---

## 🔒 安全建议

### 1. 配置文件保护

```bash
# 限制配置文件权限
chmod 600 config/accounts.json

# 避免提交到 Git
echo "config/accounts.json" >> .gitignore
```

### 2. API 密钥认证

```bash
# 在 .env 中设置 API 密钥
echo "API_KEY=your_secret_key_here" >> .env

# 客户端请求时需要携带
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer your_secret_key_here" \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini-2.5-flash", "messages": [...]}'
```

### 3. 反向代理（可选）

```bash
# 安装 Nginx
sudo apt install nginx -y

# 配置反向代理
sudo nano /etc/nginx/sites-available/gemini-api
```

**Nginx 配置：**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # 支持 SSE 流式响应
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
    }
}
```

```bash
# 启用配置
sudo ln -s /etc/nginx/sites-available/gemini-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. HTTPS 配置（推荐）

```bash
# 使用 Let's Encrypt
sudo apt install certbot python3-certbot-nginx -y

# 自动配置 HTTPS
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

---

## 📈 性能优化

### 1. 树莓派5优化

```bash
# 启用 cgroup v2（如果未启用）
sudo nano /boot/cmdline.txt
# 添加：cgroup_enable=cpuset cgroup_enable=memory cgroup_memory=1

# 重启生效
sudo reboot
```

### 2. Docker 优化

```yaml
# docker-compose.yml 性能调优
services:
  gemini-api:
    # 使用多阶段构建减小镜像体积
    # 限制日志大小
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

    # 资源预留
    deploy:
      resources:
        reservations:
          cpus: '0.5'
          memory: 256M
```

### 3. 应用优化

- 使用账号池轮询，避免单账号过载
- Token 主动刷新，减少请求延迟
- 合理设置冷却时间，避免频繁 429 错误

---

## 🔧 运维工具脚本

### 1. 服务管理脚本

```bash
# 创建管理脚本
cat > ~/manage-gemini.sh << 'EOF'
#!/bin/bash

APP_DIR=~/apps/gemini-business-api

case "$1" in
    start)
        cd $APP_DIR && docker-compose up -d
        echo "Service started"
        ;;
    stop)
        cd $APP_DIR && docker-compose down
        echo "Service stopped"
        ;;
    restart)
        cd $APP_DIR && docker-compose restart
        echo "Service restarted"
        ;;
    logs)
        cd $APP_DIR && docker-compose logs -f
        ;;
    status)
        cd $APP_DIR && docker-compose ps
        ;;
    update)
        cd $APP_DIR
        git pull origin main
        docker-compose down
        docker-compose build --no-cache
        docker-compose up -d
        echo "Service updated"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|status|update}"
        exit 1
        ;;
esac
EOF

chmod +x ~/manage-gemini.sh

# 使用示例
~/manage-gemini.sh start
~/manage-gemini.sh logs
~/manage-gemini.sh update
```

### 2. 健康检查脚本

```bash
# 创建健康检查脚本
cat > ~/check-gemini-health.sh << 'EOF'
#!/bin/bash

HEALTH_URL="http://localhost:8000/health"

response=$(curl -s -w "\n%{http_code}" $HEALTH_URL)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

if [ "$http_code" == "200" ]; then
    echo "✅ Service is healthy"
    echo "$body" | python3 -m json.tool
    exit 0
else
    echo "❌ Service is unhealthy (HTTP $http_code)"
    echo "$body"
    exit 1
fi
EOF

chmod +x ~/check-gemini-health.sh

# 添加定时检查（每5分钟）
crontab -e
# 添加：*/5 * * * * /home/pi/check-gemini-health.sh >> /var/log/gemini-health.log 2>&1
```

---

## 📝 运维清单

### 日常维护（建议频率）

- [ ] **每天**：查看日志，检查错误
- [ ] **每周**：检查账号状态，更新即将过期的账号
- [ ] **每月**：更新代码，备份配置
- [ ] **按需**：添加/移除账号，调整冷却参数

### 月度检查清单

```bash
# 1. 检查服务运行时间
docker-compose ps

# 2. 检查磁盘空间
df -h

# 3. 检查日志大小
du -sh ~/apps/gemini-business-api/logs

# 4. 检查 Docker 镜像
docker images

# 5. 清理无用资源
docker system prune -f
```

---

**文档版本历史：**
- v1.0 (2025-01-31): 初始版本，完成部署和运维指南
