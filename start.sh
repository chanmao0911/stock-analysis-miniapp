#!/bin/bash
# 业绩快查 - 一键启动脚本

echo "正在启动后端服务..."
cd "$(dirname "$0")/backend"

# 杀掉旧进程
pkill -f "uvicorn main:app" 2>/dev/null
sleep 1

# 启动后端
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/stock-backend.log 2>&1 &

sleep 3

# 验证
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✓ 后端启动成功"
    echo ""
    echo "=== 访问地址 ==="
    echo "电脑浏览器: http://localhost:8000/"
    echo "手机浏览器: http://$(ipconfig getifaddr en0 2>/dev/null):8000/"
    echo ""
    open http://localhost:8000/
else
    echo "✗ 启动失败，查看日志: tail /tmp/stock-backend.log"
fi
