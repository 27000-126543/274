@echo off
chcp 65001 > nul
echo ============================================================
echo 知识产权侵权监测与维权管理系统 - Web服务启动脚本
echo ============================================================
echo.
echo 正在检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.9+
    pause
    exit /b 1
)
echo [OK] Python环境正常
echo.

echo 正在检查依赖包...
python -c "import fastapi; import uvicorn; import sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo [提示] 部分依赖未安装，正在安装...
    pip install -r requirements.txt
)
echo [OK] 依赖包检查完成
echo.

echo 正在初始化数据库（如首次运行）...
python -c "from database.connection import init_db; init_db()" 2>nul
echo [OK] 数据库初始化完成
echo.

echo 正在导入示例数据（如首次运行）...
if not exist ip_protection.db (
    echo [提示] 检测到新数据库，正在导入示例数据...
    python seed_data.py
)
echo.

echo ============================================================
echo 服务即将启动，请访问以下地址：
echo   Web管理界面: http://localhost:8000/
echo   API文档地址: http://localhost:8000/api/docs
echo.
echo 默认登录账号:
echo   管理员: admin / admin123
echo   法务人员: legal / legal123
echo ============================================================
echo.
echo 按 Ctrl+C 停止服务
echo.

python web_server.py
pause
