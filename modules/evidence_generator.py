import os
import json
import hashlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse
import requests
from config.settings import settings
from database.models import InfringementCase, CrawledProduct, IntellectualProperty, Evidence, OperationTypeEnum
from database.connection import get_db
from utils.logger import logger
from modules.operation_logger import OperationLogger


class ScreenshotManager:
    _playwright_available = None
    _selenium_available = None

    @classmethod
    def check_playwright(cls) -> bool:
        if cls._playwright_available is not None:
            return cls._playwright_available
        try:
            import playwright
            cls._playwright_available = True
            logger.info("Playwright可用")
        except ImportError:
            cls._playwright_available = False
            logger.warning("Playwright不可用")
        return cls._playwright_available

    @classmethod
    def check_selenium(cls) -> bool:
        if cls._selenium_available is not None:
            return cls._selenium_available
        try:
            import selenium
            from selenium import webdriver
            cls._selenium_available = True
            logger.info("Selenium可用")
        except ImportError:
            cls._selenium_available = False
            logger.warning("Selenium不可用")
        return cls._selenium_available

    @classmethod
    async def take_screenshot_playwright(cls, url: str, save_path: Path) -> bool:
        if not cls.check_playwright():
            return False
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                context = await browser.new_context(
                    user_agent=settings.USER_AGENT,
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN'
                )
                page = await context.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)
                await page.screenshot(path=str(save_path), full_page=True)
                await browser.close()
            return True
        except Exception as e:
            logger.warning(f"Playwright截图失败: {e}")
            return False

    @classmethod
    def take_screenshot_selenium(cls, url: str, save_path: Path) -> bool:
        if not cls.check_selenium():
            return False
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"user-agent={settings.USER_AGENT}")
            chrome_options.add_argument("--window-size=1920,1080")

            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except:
                driver = webdriver.Chrome(options=chrome_options)

            driver.set_page_load_timeout(30)
            driver.get(url)
            import time
            time.sleep(3)
            driver.save_screenshot(str(save_path))
            driver.quit()
            return True
        except Exception as e:
            logger.warning(f"Selenium截图失败: {e}")
            return False

    @classmethod
    def generate_html_snapshot(cls, url: str, save_path: Path, title: str = "") -> bool:
        try:
            response = requests.get(url, timeout=15, headers={"User-Agent": settings.USER_AGENT})
            if response.status_code == 200:
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>网页快照 - {title or url}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .url {{ color: #666; font-size: 14px; }}
        .timestamp {{ color: #999; font-size: 12px; }}
        .content {{ border: 1px solid #ddd; padding: 15px; border-radius: 5px; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; }}
    </style>
</head>
<body>
    <div class="header">
        <h3>网页快照</h3>
        <div class="url">URL: {url}</div>
        <div class="timestamp">抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
    <div class="content">
        <h4>原始响应文本:</h4>
        <pre>{response.text[:50000]}</pre>
    </div>
</body>
</html>"""
                save_path.write_text(html_content, encoding='utf-8')
                return True
        except Exception as e:
            logger.warning(f"HTML快照生成失败: {e}")
        return False

    @classmethod
    def generate_text_snapshot(cls, url: str, save_path: Path, title: str = "") -> bool:
        try:
            from bs4 import BeautifulSoup
            response = requests.get(url, timeout=15, headers={"User-Agent": settings.USER_AGENT})
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text_content = '\n'.join(chunk for chunk in chunks if chunk)

                snapshot = f"""=== 网页文本快照 ===
URL: {url}
标题: {title or soup.title.string if soup.title else ''}
抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
========================

{text_content[:10000]}
"""
                save_path.write_text(snapshot, encoding='utf-8')
                return True
        except Exception as e:
            logger.warning(f"文本快照生成失败: {e}")
        return False

    @classmethod
    async def take_screenshot(cls, url: str, save_dir: Path, title: str = "") -> Tuple[bool, str]:
        screenshot_path = save_dir / "screenshot.png"
        html_path = save_dir / "page_snapshot.html"
        text_path = save_dir / "page_text.txt"

        if await cls.take_screenshot_playwright(url, screenshot_path):
            return True, "playwright_screenshot"

        if cls.take_screenshot_selenium(url, screenshot_path):
            return True, "selenium_screenshot"

        if cls.generate_html_snapshot(url, html_path, title):
            if cls.generate_text_snapshot(url, text_path, title):
                return True, "html_text_snapshot"
            return True, "html_snapshot"

        if cls.generate_text_snapshot(url, text_path, title):
            return True, "text_snapshot"

        fallback_info = {
            "url": url,
            "title": title,
            "capture_time": datetime.now().isoformat(),
            "note": "截图功能不可用，已保存基本信息"
        }
        info_path = save_dir / "capture_info.json"
        info_path.write_text(json.dumps(fallback_info, ensure_ascii=False, indent=2), encoding='utf-8')
        return False, "none"


class EvidenceGenerator:
    def __init__(self):
        self.base_path = settings.evidence_path
        self.op_logger = OperationLogger()

    def _get_case_dir(self, case_number: str) -> Path:
        case_dir = self.base_path / case_number
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _download_image(self, url: str, save_path: Path) -> bool:
        try:
            response = requests.get(url, timeout=15, headers={"User-Agent": settings.USER_AGENT})
            if response.status_code == 200:
                save_path.write_bytes(response.content)
                return True
        except Exception as e:
            logger.warning(f"下载图片失败 {url}: {e}")
        return False

    def _generate_md5(self, file_path: Path) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _generate_metadata(self, case: InfringementCase, product: CrawledProduct, ip: IntellectualProperty, capture_method: str) -> Dict[str, Any]:
        return {
            "case_number": case.case_number,
            "generated_at": datetime.now().isoformat(),
            "capture_method": capture_method,
            "ip_info": {
                "ip_type": ip.ip_type.value,
                "ip_number": ip.ip_number,
                "name": ip.name,
                "owner": ip.owner
            },
            "product_info": {
                "platform": product.platform.value,
                "product_id": product.product_id,
                "title": product.title,
                "price": product.price,
                "seller_name": product.seller_name,
                "product_url": product.product_url,
                "crawl_time": product.crawl_time.isoformat() if product.crawl_time else None
            },
            "similarity": {
                "score": case.similarity_score,
                "threshold": settings.SIMILARITY_THRESHOLD
            },
            "company": settings.COMPANY_NAME
        }

    async def generate_evidence_pack_async(self, case_id: int) -> Optional[str]:
        return self.generate_evidence_pack(case_id)

    def generate_evidence_pack(self, case_id: int) -> Optional[str]:
        with get_db() as db:
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
            if not case:
                logger.error(f"案件 {case_id} 不存在")
                return None

            product = case.product
            ip = case.ip

            if not product or not ip:
                logger.error(f"案件 {case_id} 缺少商品或知识产权信息")
                return None

            case_dir = self._get_case_dir(case.case_number)
            evidence_files = []

            import asyncio
            try:
                success, method = asyncio.get_event_loop().run_until_complete(
                    ScreenshotManager.take_screenshot(product.product_url, case_dir, product.title)
                )
            except:
                success, method = False, "none"

            if (case_dir / "screenshot.png").exists():
                evidence_files.append(("screenshot", case_dir / "screenshot.png", f"网页截图({method})"))
            if (case_dir / "page_snapshot.html").exists():
                evidence_files.append(("html_snapshot", case_dir / "page_snapshot.html", "网页HTML快照"))
            if (case_dir / "page_text.txt").exists():
                evidence_files.append(("text_snapshot", case_dir / "page_text.txt", "网页文本快照"))
            if (case_dir / "capture_info.json").exists():
                evidence_files.append(("capture_info", case_dir / "capture_info.json", "抓取信息"))

            for idx, img_url in enumerate(product.image_urls[:5]):
                img_path = case_dir / f"product_image_{idx}.jpg"
                if self._download_image(img_url, img_path):
                    evidence_files.append((f"product_image_{idx}", img_path, f"商品图片{idx+1}"))

            for idx, img_url in enumerate(ip.image_urls[:3]):
                img_path = case_dir / f"ip_image_{idx}.jpg"
                if self._download_image(img_url, img_path):
                    evidence_files.append((f"ip_image_{idx}", img_path, f"知识产权图片{idx+1}"))

            metadata = self._generate_metadata(case, product, ip, method)
            metadata_path = case_dir / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            evidence_files.append(("metadata", metadata_path, "元数据文件"))

            evidence_index = []
            for name, file_path, desc in evidence_files:
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    md5_hash = self._generate_md5(file_path)
                    evidence = Evidence(
                        case_id=case.id,
                        evidence_type=name,
                        file_path=str(file_path),
                        file_name=file_path.name,
                        file_size=file_size,
                        md5_hash=md5_hash,
                        description=desc
                    )
                    db.add(evidence)
                    evidence_index.append({
                        "name": name,
                        "file_name": file_path.name,
                        "description": desc,
                        "file_size": file_size,
                        "md5": md5_hash
                    })

            index_path = case_dir / "evidence_index.json"
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(evidence_index, f, ensure_ascii=False, indent=2)

            zip_path = case_dir / f"{case.case_number}_evidence.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for name, file_path, _ in evidence_files:
                    if file_path.exists():
                        zipf.write(file_path, arcname=file_path.name)
                zipf.write(index_path, arcname="evidence_index.json")

            case.evidence_pack_path = str(zip_path)
            db.commit()

            self.op_logger.log_operation(
                operation_type=OperationTypeEnum.GENERATE_EVIDENCE,
                target_id=case.id,
                target_type="infringement_case",
                details={"evidence_pack": str(zip_path), "evidence_count": len(evidence_files), "capture_method": method}
            )

            logger.info(f"证据包生成完成: {case.case_number}, 路径: {zip_path}, 方式: {method}")
            return str(zip_path)

    def get_evidence_list(self, case_id: int) -> List[Evidence]:
        with get_db() as db:
            return db.query(Evidence).filter(Evidence.case_id == case_id).all()

    def verify_evidence_integrity(self, evidence_id: int) -> bool:
        with get_db() as db:
            evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
            if not evidence:
                return False

            file_path = Path(evidence.file_path)
            if not file_path.exists():
                return False

            current_md5 = self._generate_md5(file_path)
            return current_md5 == evidence.md5_hash
