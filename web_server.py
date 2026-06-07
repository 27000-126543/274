import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from api.routes import api_router
from config.settings import settings
from utils.logger import logger
from utils.dependency_manager import DependencyManager


def run_dependency_check():
    """运行依赖检查，确保爬虫相关组件可用"""
    try:
        logger.info("正在检查爬虫依赖...")
        summary = DependencyManager.run_full_check()
        return summary
    except Exception as e:
        logger.warning(f"依赖检查过程出错: {e}")
        return None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(
    title="知识产权侵权监测与维权管理系统 API",
    description="企业级自动化知识产权侵权监测与维权管理系统的RESTful API接口",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "is_login_page": True})


@app.get("/cases", response_class=HTMLResponse)
async def cases_page(request: Request):
    return templates.TemplateResponse("cases.html", {"request": request})


@app.get("/cases/{case_id}", response_class=HTMLResponse)
async def case_detail_page(request: Request, case_id: int):
    return templates.TemplateResponse("case_detail.html", {"request": request})


@app.get("/ips", response_class=HTMLResponse)
async def ips_page(request: Request):
    return templates.TemplateResponse("ips.html", {"request": request})


@app.get("/clues", response_class=HTMLResponse)
async def clues_page(request: Request):
    return templates.TemplateResponse("clues.html", {"request": request})


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return templates.TemplateResponse("reports.html", {"request": request})


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    return templates.TemplateResponse("logs.html", {"request": request})


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "IP Protection System", "version": "2.0.0"}


@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("知识产权侵权监测与维权管理系统 Web 服务启动")
    logger.info(f"API文档地址: http://{settings.SERVER_HOST}:{settings.SERVER_PORT}/api/docs")
    logger.info(f"管理界面地址: http://{settings.SERVER_HOST}:{settings.SERVER_PORT}/")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Web服务已关闭")


def main():
    import uvicorn
    import threading

    print("\n" + "=" * 60)
    print("  知识产权侵权监测与维权管理系统 - Web服务启动")
    print("=" * 60 + "\n")

    dep_thread = threading.Thread(target=run_dependency_check, daemon=True)
    dep_thread.start()

    print("\n" + "=" * 60)
    print(f"  Web管理界面: http://localhost:{settings.SERVER_PORT}/")
    print(f"  API文档地址: http://localhost:{settings.SERVER_PORT}/api/docs")
    print(f"  默认账号: admin / admin123")
    print("=" * 60)
    print("  爬虫依赖正在后台检查安装中，请稍候...")
    print("  按 Ctrl+C 停止服务\n")

    uvicorn.run(
        "web_server:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=False,
        workers=1
    )


if __name__ == "__main__":
    main()
