import sys
import subprocess
import importlib
from typing import Dict, List, Tuple
from utils.logger import logger


class DependencyManager:
    """依赖自动检查和安装管理器"""

    DEPENDENCIES: Dict[str, str] = {
        "playwright": "playwright>=1.40.0",
        "selenium": "selenium>=4.15.0",
        "bs4": "beautifulsoup4>=4.12.0",
        "lxml": "lxml>=4.9.0",
    }

    @classmethod
    def install_package(cls, package_name: str) -> bool:
        """安装Python包"""
        try:
            logger.info(f"正在安装依赖: {package_name}")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=300
            )
            if result.returncode == 0:
                logger.info(f"✅ {package_name} 安装成功")
                return True
            else:
                logger.error(f"❌ {package_name} 安装失败: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"❌ 安装 {package_name} 时出错: {e}")
            return False

    @classmethod
    def is_installed(cls, module_name: str) -> bool:
        """检查模块是否已安装"""
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False

    @classmethod
    def check_and_install_dependencies(cls) -> Tuple[bool, Dict[str, bool]]:
        """检查并安装所有必需依赖"""
        results = {}
        all_success = True

        logger.info("=" * 60)
        logger.info("正在检查爬虫相关依赖...")
        logger.info("=" * 60)

        for module, package in cls.DEPENDENCIES.items():
            if cls.is_installed(module):
                logger.info(f"✅ {module} 已安装")
                results[module] = True
            else:
                logger.warning(f"⚠️  {module} 未安装，正在安装...")
                success = cls.install_package(package)
                results[module] = success
                if not success:
                    all_success = False

        logger.info("=" * 60)
        return all_success, results

    @classmethod
    def install_playwright_browsers(cls) -> bool:
        """安装Playwright浏览器驱动"""
        try:
            if not cls.is_installed("playwright"):
                logger.warning("Playwright未安装，跳过浏览器安装")
                return False

            logger.info("正在检查Playwright浏览器...")

            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    try:
                        browser = p.chromium.launch(headless=True)
                        browser.close()
                        logger.info("✅ Playwright Chromium 浏览器已就绪")
                        return True
                    except Exception:
                        pass
            except Exception:
                pass

            logger.info("正在安装Playwright Chromium浏览器...")
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=600
            )

            if result.returncode == 0:
                logger.info("✅ Playwright Chromium 浏览器安装成功")
                return True
            else:
                logger.warning(f"Playwright浏览器安装警告: {result.stderr[:200]}")
                return False

        except Exception as e:
            logger.warning(f"安装Playwright浏览器时出错: {e}")
            return False

    @classmethod
    def check_selenium_chrome(cls) -> bool:
        """检查Selenium Chrome可用性"""
        try:
            if not cls.is_installed("selenium"):
                return False

            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")

            try:
                service = Service()
                driver = webdriver.Chrome(service=service, options=options)
                driver.quit()
                logger.info("✅ Selenium Chrome 已就绪")
                return True
            except Exception:
                pass

            try:
                import chromedriver_autoinstaller
                chromedriver_autoinstaller.install()
                service = Service()
                driver = webdriver.Chrome(service=service, options=options)
                driver.quit()
                logger.info("✅ Selenium Chrome 已就绪（自动安装驱动）")
                return True
            except Exception:
                pass

            logger.warning("⚠️  Selenium Chrome 不可用")
            return False

        except Exception as e:
            logger.warning(f"检查Selenium时出错: {e}")
            return False

    @classmethod
    def get_available_crawlers(cls) -> Dict[str, bool]:
        """获取可用的爬虫引擎"""
        return {
            "playwright": cls.is_installed("playwright"),
            "selenium": cls.is_installed("selenium"),
            "requests": cls.is_installed("requests"),
        }

    @classmethod
    def run_full_check(cls) -> Dict:
        """运行完整的依赖检查"""
        logger.info("=" * 60)
        logger.info("运行爬虫依赖完整性检查")
        logger.info("=" * 60)

        dep_ok, dep_results = cls.check_and_install_dependencies()

        playwright_ok = False
        if dep_results.get("playwright"):
            playwright_ok = cls.install_playwright_browsers()

        selenium_ok = False
        if dep_results.get("selenium"):
            selenium_ok = cls.check_selenium_chrome()

        engines = cls.get_available_crawlers()

        summary = {
            "dependencies": dep_results,
            "playwright_browser": playwright_ok,
            "selenium_available": selenium_ok,
            "available_engines": engines,
            "all_ok": dep_ok and (playwright_ok or engines["requests"])
        }

        logger.info("=" * 60)
        logger.info("依赖检查完成:")
        logger.info(f"  Python依赖: {'✅ 全部通过' if dep_ok else '❌ 部分失败'}")
        logger.info(f"  Playwright: {'✅ 可用' if playwright_ok else '⚠️  不可用'}")
        logger.info(f"  Selenium: {'✅ 可用' if selenium_ok else '⚠️  不可用'}")
        logger.info(f"  Requests: {'✅ 可用' if engines['requests'] else '❌ 不可用'}")
        logger.info(f"  推荐引擎: {'Playwright' if playwright_ok else ('Selenium' if selenium_ok else 'Requests')}")
        logger.info("=" * 60)

        return summary
