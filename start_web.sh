#!/bin/bash
echo "============================================================"
echo "知识产权侵权监测与维权管理系统 - Web服务启动脚本"
echo "============================================================"
echo ""

echo "正在检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到Python3，请先安装Python 3.9+"
    exit 1
fi
echo "[OK] Python环境正常"
echo ""

echo "正在检查依赖包..."
python3 -c "import fastapi; import uvicorn; import sqlalchemy" &> /dev/null
if [ $? -ne 0 ]; then
    echo "[提示] 部分依赖未安装，正在安装..."
    pip3 install -r requirements.txt
fi
echo "[OK] 依赖包检查完成"
echo ""

echo "正在初始化数据库（如首次运行）..."
python3 -c "from database.connection import init_db; init_db()" &> /dev/null
echo "[OK] 数据库初始化完成"
echo ""

echo "正在导入示例数据（如首次运行）..."
if [ ! -f "ip_protection.db" ]; then
    echo "[提示] 检测到新数据库，正在导入示例数据..."
    python3 seed_data.py
fi
echo ""

echo "============================================================"
echo "服务即将启动，请访问以下地址："
echo "  Web管理界面: http://localhost:8000/"
echo "  API文档地址: http://localhost:8000/api/docs"
echo ""
echo "默认登录账号:"
echo "  管理员: admin / admin123"
echo "  法务人员: legal / legal123"
echo "============================================================"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python3 web_server.py
