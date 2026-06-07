import asyncio
import hashlib
import json
import time
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote_plus, urljoin
import aiohttp
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from database.models import PlatformEnum, CrawledProduct
from database.connection import get_db
from utils.logger import logger
from utils.dependency_manager import DependencyManager


class PlaywrightEngine:
    """Playwright浏览器引擎管理器"""

    def __init__(self):
        self._browser = None
        self._playwright = None
        self._available = None

    async def init(self) -> bool:
        """初始化浏览器"""
        if self._available is not None:
            return self._available

        if not DependencyManager.is_installed("playwright"):
            logger.warning("Playwright未安装，将使用Requests作为降级方案")
            self._available = False
            return False

        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()

            launch_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]

            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=launch_args,
                timeout=60000
            )

            logger.info("✅ Playwright浏览器引擎初始化成功")
            self._available = True
            return True

        except Exception as e:
            logger.warning(f"⚠️  Playwright初始化失败: {e}，将使用Requests作为降级方案")
            self._available = False
            return False

    async def get_browser(self):
        if self._available is None:
            await self.init()
        return self._browser if self._available else None

    async def fetch_page(self, url: str, wait_selector: Optional[str] = None,
                        wait_time: int = 3, extra_headers: Optional[Dict] = None) -> Optional[Tuple[str, str]]:
        """
        使用Playwright抓取页面
        返回: (页面HTML内容, 最终URL)
        """
        browser = await self.get_browser()
        if not browser:
            return None

        try:
            context = await browser.new_context(
                user_agent=settings.USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                extra_http_headers=extra_headers or {}
            )

            page = await context.new_page()

            await page.goto(url, wait_until='domcontentloaded', timeout=45000)

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    pass

            await asyncio.sleep(wait_time)

            content = await page.content()
            final_url = page.url

            await context.close()
            return (content, final_url)

        except Exception as e:
            logger.debug(f"Playwright抓取失败 {url}: {e}")
            return None

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._available = None


playwright_engine = PlaywrightEngine()


class RequestsEngine:
    """HTTP请求引擎"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": settings.USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.session.get(url, timeout=settings.REQUEST_TIMEOUT, **kwargs)
            return resp
        except Exception as e:
            logger.debug(f"HTTP请求失败 {url}: {e}")
            return None

    async def async_get(self, url: str, session: aiohttp.ClientSession, **kwargs) -> Optional[str]:
        try:
            async with session.get(url, timeout=settings.REQUEST_TIMEOUT, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.text()
        except Exception as e:
            logger.debug(f"Async HTTP请求失败 {url}: {e}")
        return None


requests_engine = RequestsEngine()


class BaseSpider:
    """爬虫基类"""

    def __init__(self):
        self.platform: PlatformEnum = PlatformEnum.OTHER
        self.engine_priority = ["playwright", "requests"]

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """搜索关键词，返回商品列表"""
        raise NotImplementedError

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _parse_price(self, price_text: str) -> Optional[float]:
        """解析价格"""
        if not price_text:
            return None
        try:
            cleaned = re.sub(r'[^\d.]', '', price_text)
            if cleaned:
                return float(cleaned)
        except Exception:
            pass
        return None

    def _parse_sales(self, sales_text: str) -> Optional[int]:
        """解析销量"""
        if not sales_text:
            return None
        try:
            sales_text = sales_text.lower()
            if "万" in sales_text:
                num = float(re.sub(r'[^\d.]', '', sales_text))
                return int(num * 10000)
            else:
                digits = re.sub(r'[^\d]', '', sales_text)
                if digits:
                    return int(digits)
        except Exception:
            pass
        return None


class TaobaoSpider(BaseSpider):
    """淘宝爬虫 - 使用Playwright真实动态渲染"""

    def __init__(self):
        super().__init__()
        self.platform = PlatformEnum.TAOBAO
        self.search_url = "https://s.taobao.com/search?q={}"

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        url = self.search_url.format(quote_plus(keyword))
        logger.info(f"[淘宝] 正在搜索: {keyword}")

        products = []

        result = await playwright_engine.fetch_page(
            url,
            wait_selector='div[class*="items"], div[class*="item"], div[data-category="products"]',
            wait_time=4
        )

        if result:
            html, final_url = result
            products = self._parse_taobao_page(html, keyword)
            if products:
                logger.info(f"[淘宝] Playwright抓取成功，获取 {len(products)} 个商品")
                return products

        logger.info(f"[淘宝] Playwright不可用，尝试Requests降级方案")
        html = await requests_engine.async_get(url, session)
        if html:
            products = self._parse_taobao_page(html, keyword)
            if products:
                logger.info(f"[淘宝] Requests抓取成功，获取 {len(products)} 个商品")
                return products

        logger.warning(f"[淘宝] 所有方案均未获取到数据，关键词: {keyword}")
        return []

    def _parse_taobao_page(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")

            selectors = [
                'div[class*="Item--item"]',
                'div[class*="itemWrapper"]',
                'div[class*="J_MouserOnverReq"]',
                'div.item',
                'div[class*="product-card"]',
                'div[class*="card"]',
            ]

            items = []
            for selector in selectors:
                items = soup.select(selector)
                if len(items) >= 3:
                    break

            for item in items[:30]:
                try:
                    title = ""
                    title_selectors = [
                        '[class*="title--titleText"] a',
                        '.J_ClickStat',
                        'a[class*="title"]',
                        'h3',
                        '.title',
                    ]
                    for ts in title_selectors:
                        t_elem = item.select_one(ts)
                        if t_elem:
                            title = t_elem.get("title", "") or t_elem.get_text(strip=True)
                            if title:
                                break

                    if not title:
                        continue

                    price = None
                    price_selectors = [
                        '[class*="price--priceInt"]',
                        '[class*="price"] strong',
                        '.price em',
                        '[class*="priceText"]',
                    ]
                    for ps in price_selectors:
                        p_elem = item.select_one(ps)
                        if p_elem:
                            price = self._parse_price(p_elem.get_text())
                            if price:
                                break

                    sales = None
                    sales_selectors = [
                        '[class*="sales--realSales"]',
                        '.deal-cnt',
                        '[class*="sales"]',
                    ]
                    for ss in sales_selectors:
                        s_elem = item.select_one(ss)
                        if s_elem:
                            sales = self._parse_sales(s_elem.get_text())
                            if sales:
                                break

                    seller = ""
                    seller_selectors = [
                        '[class*="shopInfo--shopName"]',
                        '.shopname',
                        '[class*="shop"] a',
                    ]
                    for sls in seller_selectors:
                        s_elem = item.select_one(sls)
                        if s_elem:
                            seller = s_elem.get_text(strip=True)
                            break

                    product_url = ""
                    link_elem = item.select_one('a[href*="item.taobao.com"], a[href*="detail"]')
                    if link_elem:
                        href = link_elem.get("href", "")
                        if href.startswith("//"):
                            product_url = "https:" + href
                        elif href.startswith("http"):
                            product_url = href

                    img_url = ""
                    img_elem = item.select_one('img')
                    if img_elem:
                        src = img_elem.get("src", "") or img_elem.get("data-src", "")
                        if src.startswith("//"):
                            img_url = "https:" + src
                        elif src.startswith("http"):
                            img_url = src

                    product_id = hashlib.md5(f"{title}_{product_url}".encode()).hexdigest()[:16]

                    products.append({
                        "platform": self.platform,
                        "product_id": product_id,
                        "title": self._clean_text(title),
                        "price": price,
                        "seller_name": seller,
                        "seller_id": "",
                        "seller_level": None,
                        "seller_fans": None,
                        "product_url": product_url,
                        "image_urls": [img_url] if img_url else [],
                        "category": keyword,
                        "sales_volume": sales,
                    })
                except Exception as e:
                    logger.debug(f"解析淘宝商品项失败: {e}")
                    continue

        except Exception as e:
            logger.debug(f"淘宝页面解析失败: {e}")

        return products


class JDSpider(BaseSpider):
    """京东爬虫 - 使用Playwright真实动态渲染"""

    def __init__(self):
        super().__init__()
        self.platform = PlatformEnum.JD
        self.search_url = "https://search.jd.com/Search?keyword={}&enc=utf-8"

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        url = self.search_url.format(quote_plus(keyword))
        logger.info(f"[京东] 正在搜索: {keyword}")

        products = []

        result = await playwright_engine.fetch_page(
            url,
            wait_selector='.gl-item, .goods-item, .j-sku-item',
            wait_time=4
        )

        if result:
            html, final_url = result
            products = self._parse_jd_page(html, keyword)
            if products:
                logger.info(f"[京东] Playwright抓取成功，获取 {len(products)} 个商品")
                return products

        logger.info(f"[京东] Playwright不可用，尝试Requests降级方案")
        html = await requests_engine.async_get(url, session)
        if html:
            products = self._parse_jd_page(html, keyword)
            if products:
                logger.info(f"[京东] Requests抓取成功，获取 {len(products)} 个商品")
                return products

        logger.warning(f"[京东] 所有方案均未获取到数据，关键词: {keyword}")
        return []

    def _parse_jd_page(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")

            items = soup.select('.gl-item')
            if not items:
                items = soup.select('.goods-item, .j-sku-item, .product-item')

            for item in items[:30]:
                try:
                    title_elem = item.select_one('.p-name em, .p-name a, .goods-title')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    if not title:
                        continue

                    price = None
                    price_elem = item.select_one('.p-price i, .goods-price, .price')
                    if price_elem:
                        price = self._parse_price(price_elem.get_text())

                    sales = None
                    sales_elem = item.select_one('.p-commit strong, .sales-volume')
                    if sales_elem:
                        sales = self._parse_sales(sales_elem.get_text())

                    seller = ""
                    seller_elem = item.select_one('.p-shop a, .p-shop span, .shop-name')
                    if seller_elem:
                        seller = seller_elem.get("title", seller_elem.get_text(strip=True))

                    product_url = ""
                    link_elem = item.select_one('.p-img a, .goods-img a')
                    if link_elem:
                        href = link_elem.get("href", "")
                        if href.startswith("//"):
                            product_url = "https:" + href
                        elif href.startswith("/"):
                            product_url = "https://item.jd.com" + href

                    img_url = ""
                    img_elem = item.select_one('.p-img img, .goods-img img')
                    if img_elem:
                        src = img_elem.get("src", "") or img_elem.get("data-lazy-img", "")
                        if src.startswith("//"):
                            img_url = "https:" + src

                    sku = item.get("data-sku", "")
                    product_id = sku if sku else hashlib.md5(title.encode()).hexdigest()[:16]

                    products.append({
                        "platform": self.platform,
                        "product_id": product_id,
                        "title": self._clean_text(title),
                        "price": price,
                        "seller_name": seller,
                        "seller_id": "",
                        "seller_level": None,
                        "seller_fans": None,
                        "product_url": product_url,
                        "image_urls": [img_url] if img_url else [],
                        "category": keyword,
                        "sales_volume": sales,
                    })
                except Exception as e:
                    logger.debug(f"解析京东商品项失败: {e}")
                    continue

        except Exception as e:
            logger.debug(f"京东页面解析失败: {e}")

        return products


class DouyinSpider(BaseSpider):
    """抖音爬虫 - 使用真实Requests搜索请求"""

    def __init__(self):
        super().__init__()
        self.platform = PlatformEnum.DOUYIN
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.douyin.com/",
        })

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        logger.info(f"[抖音] 正在搜索: {keyword}")
        products = []

        try:
            products = await self._search_douyin_goods(keyword, session)
            if products:
                logger.info(f"[抖音] API搜索成功，获取 {len(products)} 个商品")
                return products
        except Exception as e:
            logger.debug(f"抖音API搜索失败: {e}")

        try:
            web_url = f"https://www.douyin.com/search/{quote_plus(keyword)}?type=goods"
            result = await playwright_engine.fetch_page(web_url, wait_time=5)
            if result:
                html, _ = result
                products = self._parse_douyin_web(html, keyword)
                if products:
                    logger.info(f"[抖音] Web页面抓取成功，获取 {len(products)} 个商品")
                    return products
        except Exception as e:
            logger.debug(f"抖音Web抓取失败: {e}")

        logger.warning(f"[抖音] 未获取到数据，关键词: {keyword}")
        return []

    async def _search_douyin_goods(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """调用抖音搜索接口"""
        products = []

        search_urls = [
            f"https://www.douyin.com/aweme/v1/web/search/item/?keyword={quote_plus(keyword)}&count=20&search_channel=aweme_goods_search",
            f"https://www.douyin.com/aweme/v1/web/general/search/single/?keyword={quote_plus(keyword)}&count=20",
        ]

        headers = {
            "User-Agent": settings.USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.douyin.com/",
        }

        for url in search_urls:
            try:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("data", [])
                        if items:
                            for item in items[:15]:
                                try:
                                    aweme = item.get("aweme_info", item)
                                    desc = aweme.get("desc", "")

                                    author = aweme.get("author", {})
                                    author_name = author.get("nickname", "抖音用户")
                                    fans = author.get("follower_count", 0)

                                    stats = aweme.get("statistics", {})

                                    cover = ""
                                    video_data = aweme.get("video", {})
                                    if video_data:
                                        cover_list = video_data.get("cover", {}).get("url_list", [])
                                        if cover_list:
                                            cover = cover_list[0]

                                    product_id = aweme.get("aweme_id", hashlib.md5(desc.encode()).hexdigest()[:16])

                                    products.append({
                                        "platform": self.platform,
                                        "product_id": str(product_id),
                                        "title": self._clean_text(desc) or f"{keyword} 相关视频",
                                        "price": None,
                                        "seller_name": author_name,
                                        "seller_id": str(author.get("uid", "")),
                                        "seller_level": None,
                                        "seller_fans": fans,
                                        "product_url": f"https://www.douyin.com/video/{product_id}",
                                        "image_urls": [cover] if cover else [],
                                        "category": keyword,
                                        "sales_volume": stats.get("digg_count", 0),
                                    })
                                except Exception:
                                    continue
                            if products:
                                break
            except Exception as e:
                logger.debug(f"抖音搜索API {url} 失败: {e}")
                continue

        return products

    def _parse_douyin_web(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")

            script_data = soup.find("script", id="RENDER_DATA")
            if script_data:
                try:
                    import urllib.parse
                    data_str = urllib.parse.unquote(script_data.string)
                    data = json.loads(data_str)

                    def find_items(obj):
                        results = []
                        if isinstance(obj, dict):
                            if "awemeId" in obj or "desc" in obj:
                                results.append(obj)
                            for v in obj.values():
                                results.extend(find_items(v))
                        elif isinstance(obj, list):
                            for item in obj:
                                results.extend(find_items(item))
                        return results

                    items = find_items(data)
                    for item in items[:15]:
                        try:
                            desc = item.get("desc", "")
                            if not desc:
                                continue
                            author = item.get("author", {})
                            products.append({
                                "platform": self.platform,
                                "product_id": str(item.get("awemeId", hashlib.md5(desc.encode()).hexdigest()[:16])),
                                "title": self._clean_text(desc),
                                "price": None,
                                "seller_name": author.get("nickname", ""),
                                "seller_id": "",
                                "seller_level": None,
                                "seller_fans": author.get("followerCount"),
                                "product_url": f"https://www.douyin.com/video/{item.get('awemeId', '')}",
                                "image_urls": [],
                                "category": keyword,
                                "sales_volume": None,
                            })
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"解析抖音内嵌数据失败: {e}")

            if not products:
                cards = soup.select('[class*="video-card"], [class*="search-result"], [class*="item"]')
                for card in cards[:10]:
                    try:
                        title_elem = card.select_one('[class*="title"], [class*="desc"]')
                        title = title_elem.get_text(strip=True) if title_elem else ""
                        if title:
                            products.append({
                                "platform": self.platform,
                                "product_id": hashlib.md5(title.encode()).hexdigest()[:16],
                                "title": self._clean_text(title),
                                "price": None,
                                "seller_name": "",
                                "seller_id": "",
                                "seller_level": None,
                                "seller_fans": None,
                                "product_url": "",
                                "image_urls": [],
                                "category": keyword,
                                "sales_volume": None,
                            })
                    except Exception:
                        continue

        except Exception as e:
            logger.debug(f"抖音页面解析失败: {e}")

        return products


class PDDPlatSpider(BaseSpider):
    """拼多多爬虫"""

    def __init__(self):
        super().__init__()
        self.platform = PlatformEnum.PDD

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        logger.info(f"[拼多多] 正在搜索: {keyword}")
        products = []

        url = f"https://mobile.yangkeduo.com/search_result.html?search_key={quote_plus(keyword)}"

        result = await playwright_engine.fetch_page(url, wait_time=5)
        if result:
            html, _ = result
            products = self._parse_pdd_page(html, keyword)
            if products:
                logger.info(f"[拼多多] Playwright抓取成功，获取 {len(products)} 个商品")
                return products

        logger.warning(f"[拼多多] 未获取到数据，关键词: {keyword}")
        return []

    def _parse_pdd_page(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")
            items = soup.select('[class*="goods-item"], [class*="item"], ._2jF2V')

            for item in items[:15]:
                try:
                    title_elem = item.select_one('[class*="title"], [class*="goods-name"]')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    if not title:
                        continue

                    price = None
                    price_elem = item.select_one('[class*="price"], [class*="goods-price"]')
                    if price_elem:
                        price = self._parse_price(price_elem.get_text())

                    sales = None
                    sales_elem = item.select_one('[class*="sales"], [class*="sold"]')
                    if sales_elem:
                        sales = self._parse_sales(sales_elem.get_text())

                    products.append({
                        "platform": self.platform,
                        "product_id": hashlib.md5(title.encode()).hexdigest()[:16],
                        "title": self._clean_text(title),
                        "price": price,
                        "seller_name": "",
                        "seller_id": "",
                        "seller_level": None,
                        "seller_fans": None,
                        "product_url": "",
                        "image_urls": [],
                        "category": keyword,
                        "sales_volume": sales,
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"拼多多页面解析失败: {e}")

        return products


class SpiderManager:
    """爬虫管理器"""

    def __init__(self):
        self.spiders: Dict[PlatformEnum, BaseSpider] = {}
        self._initialized = False

    def _init_spiders(self):
        if self._initialized:
            return

        if settings.TAOBAO_ENABLED:
            self.spiders[PlatformEnum.TAOBAO] = TaobaoSpider()
        if settings.JD_ENABLED:
            self.spiders[PlatformEnum.JD] = JDSpider()
        if settings.DOUYIN_ENABLED:
            self.spiders[PlatformEnum.DOUYIN] = DouyinSpider()
        if settings.PDD_ENABLED:
            self.spiders[PlatformEnum.PDD] = PDDPlatSpider()

        self._initialized = True
        logger.info(f"爬虫管理器初始化完成，已加载 {len(self.spiders)} 个平台爬虫")

    async def crawl_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        self._init_spiders()

        all_products = []
        connector = aiohttp.TCPConnector(limit=settings.MAX_CONCURRENT_SPIDERS)

        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for spider in self.spiders.values():
                task = spider.search(keyword, session)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, list):
                    all_products.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"爬虫任务异常: {result}")

        logger.info(f"关键词 '{keyword}' 抓取完成，共获取 {len(all_products)} 个商品")
        return all_products

    async def crawl_multiple_keywords(self, keywords: List[str]) -> List[Dict[str, Any]]:
        self._init_spiders()

        all_products = []
        semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_SPIDERS)

        async def bounded_crawl(keyword):
            async with semaphore:
                return await self.crawl_keyword(keyword)

        tasks = [bounded_crawl(kw) for kw in keywords]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_products.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"关键词抓取异常: {result}")

        logger.info(f"批量抓取完成，共 {len(keywords)} 个关键词，获取 {len(all_products)} 个商品")
        return all_products

    def save_products(self, products: List[Dict[str, Any]]) -> int:
        saved_count = 0
        with get_db() as db:
            for prod_data in products:
                try:
                    content_str = f"{prod_data.get('title', '')}{prod_data.get('description', '')}{prod_data.get('product_url', '')}"
                    content_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()

                    existing = db.query(CrawledProduct).filter(
                        CrawledProduct.content_hash == content_hash
                    ).first()

                    if existing:
                        continue

                    product = CrawledProduct(
                        platform=prod_data.get("platform", PlatformEnum.OTHER),
                        product_id=prod_data.get("product_id", ""),
                        title=prod_data.get("title", ""),
                        description=prod_data.get("description", ""),
                        price=prod_data.get("price"),
                        seller_name=prod_data.get("seller_name", ""),
                        seller_id=prod_data.get("seller_id", ""),
                        seller_level=prod_data.get("seller_level"),
                        seller_fans=prod_data.get("seller_fans"),
                        product_url=prod_data.get("product_url", ""),
                        image_urls=prod_data.get("image_urls", []),
                        category=prod_data.get("category", ""),
                        sales_volume=prod_data.get("sales_volume"),
                        content_hash=content_hash
                    )
                    db.add(product)
                    saved_count += 1

                    if saved_count % 100 == 0:
                        db.commit()
                except Exception as e:
                    logger.error(f"保存商品失败: {e}")
                    db.rollback()

            db.commit()

        logger.info(f"成功保存 {saved_count} 个新商品")
        return saved_count

    def get_pending_products(self, limit: int = 1000) -> List[CrawledProduct]:
        from database.models import InfringementCase
        with get_db() as db:
            subquery = db.query(InfringementCase.product_id).filter(
                InfringementCase.product_id.isnot(None)
            ).subquery()

            products = db.query(CrawledProduct).filter(
                CrawledProduct.id.notin_(subquery)
            ).order_by(CrawledProduct.crawl_time.desc()).limit(limit).all()

            return products
