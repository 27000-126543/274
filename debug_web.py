import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("调试Web服务启动")
print("=" * 60)

try:
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates
    print("✅ FastAPI导入成功")
except Exception as e:
    print(f"❌ FastAPI导入失败: {e}")
    sys.exit(1)

try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
    print(f"✅ 模板目录加载成功: {os.path.join(BASE_DIR, 'templates')}")
except Exception as e:
    print(f"❌ 模板目录加载失败: {e}")
    sys.exit(1)

try:
    from api.routes import api_router
    print(f"✅ API路由导入成功，共 {len(api_router.routes)} 条路由")
except Exception as e:
    print(f"❌ API路由导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    from web_server import app
    print(f"✅ App创建成功，共 {len(app.routes)} 条路由")
except Exception as e:
    print(f"❌ App创建失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("所有检查通过！现在启动测试请求...")
print("=" * 60)

from fastapi.testclient import TestClient
client = TestClient(app)

print("\n测试主页 / ...")
try:
    response = client.get("/")
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print("✅ 主页访问成功")
        print(f"页面内容长度: {len(response.text)}")
    else:
        print(f"❌ 主页访问失败")
        print(f"错误内容: {response.text[:500]}")
except Exception as e:
    print(f"❌ 请求异常: {e}")
    import traceback
    traceback.print_exc()

print("\n测试登录页 /login ...")
try:
    response = client.get("/login")
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print("✅ 登录页访问成功")
    else:
        print(f"❌ 登录页访问失败")
except Exception as e:
    print(f"❌ 请求异常: {e}")

print("\n测试健康检查 /health ...")
try:
    response = client.get("/health")
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ 健康检查成功: {response.json()}")
    else:
        print(f"❌ 健康检查失败")
except Exception as e:
    print(f"❌ 请求异常: {e}")
