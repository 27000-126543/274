import asyncio
import hashlib
import json
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote_plus, urljoin, urlparse
import aiohttp
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from database.models import PlatformEnum, CrawledProduct
from database.connection import get_db
from utils.logger import logger


class PlaywrightWrapper:
    """Playwright包装器 - 自动检测可用性"""

    _available = None
    _browser = None
    _playwright_instance = None

    @classmethod
    async def init(cls):
        if cls._available is not None:
            return cls._available
        try:
            from playwright.async_api import async_playwright
            cls._playwright_instance = await async_playwright().start()
            cls._browser = await cls._playwright_instance.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ],
                timeout=30000
            )
            cls._available = True
            logger.info("✅ Playwright浏览器引擎初始化成功")
        except Exception as e:
            logger.warning(f"⚠️  Playwright不可用 ({e})，将使用Requests方案")
            cls._available = False
        return cls._available

    @classmethod
    async def fetch(cls, url: str, wait_selector: Optional[str] = None, wait_time: int = 3) -> Optional[str]:
        """使用Playwright抓取页面"""
        if not await cls.init():
            return None
        try:
            context = await cls._browser.new_context(
                user_agent=settings.USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN'
            )
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    pass
            await asyncio.sleep(wait_time)
            content = await page.content()
            await context.close()
            return content
        except Exception as e:
            logger.debug(f"Playwright抓取失败: {e}")
            return None

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright_instance:
            await cls._playwright_instance.stop()
            cls._playwright_instance = None
        cls._available = None


def get_requests_headers(referer: str = "") -> Dict[str, str]:
    """获取标准请求头"""
    headers = {
        "User-Agent": settings.USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    return headers


async def fetch_with_requests(url: str, session: aiohttp.ClientSession, **kwargs) -> Optional[str]:
    """使用aiohttp抓取页面"""
    try:
        headers = get_requests_headers(kwargs.get("referer", ""))
        async with session.get(url, headers=headers, timeout=settings.REQUEST_TIMEOUT, proxy=kwargs.get("proxy")) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        logger.debug(f"Requests抓取失败 {url}: {e}")
    return None


def clean_text(text: str) -> str:
    """清理文本"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def parse_price(price_text: str) -> Optional[float]:
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


def parse_sales(sales_text: str) -> Optional[int]:
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


class TaobaoSpider:
    """淘宝爬虫 - 双引擎真实抓取"""

    def __init__(self):
        self.platform = PlatformEnum.TAOBAO

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        logger.info(f"[淘宝] 搜索关键词: {keyword}")
        products = []
        url = f"https://s.taobao.com/search?q={quote_plus(keyword)}"

        # 方案1: Playwright动态渲染
        html = await PlaywrightWrapper.fetch(
            url,
            wait_selector='div[class*="item"], div[class*="card"]',
            wait_time=5
        )
        if html:
            products = self._parse_page(html, keyword)
            if products:
                logger.info(f"[淘宝] Playwright抓取成功，获取 {len(products)} 个商品")
                return products

        # 方案2: Requests + 多备用搜索入口
        logger.info("[淘宝] Playwright不可用，尝试Requests方案")
        search_urls = [
            f"https://s.taobao.com/search?q={quote_plus(keyword)}",
            f"https://re.taobao.com/search?keyword={quote_plus(keyword)}",
            f"https://ai.taobao.com/search/index.htm?key={quote_plus(keyword)}",
        ]

        for search_url in search_urls:
            html = await fetch_with_requests(search_url, session, referer="https://www.taobao.com/")
            if html:
                products = self._parse_page(html, keyword)
                if products:
                    logger.info(f"[淘宝] Requests抓取成功 ({search_url}), 获取 {len(products)} 个商品")
                    return products

        # 方案3: 从搜索结果页的script标签中提取数据
        products = await self._extract_from_script(keyword, session)
        if products:
            logger.info(f"[淘宝] 从Script标签提取数据成功，获取 {len(products)} 个商品")
            return products

        logger.warning(f"[淘宝] 所有方案均未获取到数据")
        return []

    def _parse_page(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")

            selectors = [
                'div[class*="item"]',
                'div[class*="Item--"]',
                'div[class*="card"]',
                'div[class*="product"]',
                'li[class*="item"]',
                'div.J_MouserOnverReq',
            ]

            items = []
            for sel in selectors:
                items = soup.select(sel)
                if len(items) >= 3:
                    break

            for item in items[:30]:
                try:
                    title = ""
                    title_selectors = [
                        'a[class*="title"]',
                        'a[class*="J_ClickStat"]',
                        'h3', '.title',
                        'a[href*="item.taobao.com"]',
                        'a[href*="detail.tmall.com"]'
                    ]
                    for ts in title_selectors:
                        t = item.select_one(ts)
                        if t:
                            title = t.get("title", "") or t.get_text(strip=True)
                            if title and len(title) > 5:
                                break

                    if not title or len(title) < 3:
                        continue

                    price = None
                    for ps in ['[class*="price"] strong', '[class*="price"] em', '.price', 'strong']:
                        p = item.select_one(ps)
                        if p:
                            price = parse_price(p.get_text())
                            if price:
                                break

                    sales = None
                    for ss in ['.deal-cnt', '[class*="sales"]', '[class*="sold"]']:
                        s = item.select_one(ss)
                        if s:
                            sales = parse_sales(s.get_text())
                            if sales:
                                break

                    seller = ""
                    for sls in ['.shopname', '[class*="shop"] a', '[class*="seller"]']:
                        sl = item.select_one(sls)
                        if sl:
                            seller = clean_text(sl.get_text())
                            if seller:
                                break

                    product_url = ""
                    link = item.select_one('a[href*="item.taobao.com"], a[href*="detail.tmall.com"], a[href*="click"]')
                    if link:
                        href = link.get("href", "")
                        if href.startswith("//"):
                            product_url = "https:" + href
                        elif href.startswith("/"):
                            product_url = "https://s.taobao.com" + href
                        elif href.startswith("http"):
                            product_url = href

                    img_url = ""
                    img = item.select_one('img')
                    if img:
                        src = img.get("src", "") or img.get("data-src", "") or img.get("data-ks-lazyload", "")
                        if src.startswith("//"):
                            img_url = "https:" + src
                        elif src.startswith("http"):
                            img_url = src

                    product_id = hashlib.md5(f"{title}_{price}_{product_url}".encode()).hexdigest()[:16]

                    products.append({
                        "platform": self.platform,
                        "product_id": product_id,
                        "title": clean_text(title),
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

    async def _extract_from_script(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """从页面script标签中提取数据"""
        products = []
        try:
            url = f"https://s.taobao.com/search?q={quote_plus(keyword)}"
            html = await fetch_with_requests(url, session)
            if not html:
                return []

            patterns = [
                r'g_page_config\s*=\s*({.+?});',
                r'g_srp_loadCss\(\);\s*var\s+g_page_config\s*=\s*({.+?});',
                r'"auctions"\s*:\s*\[(.+?)\]',
            ]

            for pattern in patterns:
                matches = re.search(pattern, html, re.DOTALL)
                if matches:
                    try:
                        if "auctions" in pattern:
                            data_str = "[" + matches.group(1) + "]"
                            auctions = json.loads(data_str)
                        else:
                            data = json.loads(matches.group(1))
                            auctions = data.get("mods", {}).get("itemlist", {}).get("data", {}).get("auctions", [])

                        for item in auctions[:20]:
                            try:
                                title = item.get("raw_title", "") or item.get("title", "")
                                if not title:
                                    continue
                                products.append({
                                    "platform": self.platform,
                                    "product_id": str(item.get("nid", hashlib.md5(title.encode()).hexdigest()[:16])),
                                    "title": clean_text(title),
                                    "price": parse_price(item.get("view_price", "")),
                                    "seller_name": item.get("nick", ""),
                                    "seller_id": item.get("user_id", ""),
                                    "seller_level": None,
                                    "seller_fans": None,
                                    "product_url": "https://item.taobao.com/item.htm?id=" + str(item.get("nid", "")) if item.get("nid") else "",
                                    "image_urls": ["https:" + item.get("pic_url", "")] if item.get("pic_url") else [],
                                    "category": keyword,
                                    "sales_volume": parse_sales(item.get("view_sales", "")),
                                })
                            except Exception:
                                continue

                        if products:
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"淘宝Script提取失败: {e}")

        return products


class JDSpider:
    """京东爬虫 - 双引擎真实抓取"""

    def __init__(self):
        self.platform = PlatformEnum.JD

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        logger.info(f"[京东] 搜索关键词: {keyword}")
        products = []
        url = f"https://search.jd.com/Search?keyword={quote_plus(keyword)}&enc=utf-8"

        # 方案1: Playwright动态渲染
        html = await PlaywrightWrapper.fetch(
            url,
            wait_selector='.gl-item, .goods-list, li[class*="item"]',
            wait_time=5
        )
        if html:
            products = self._parse_page(html, keyword)
            if products:
                logger.info(f"[京东] Playwright抓取成功，获取 {len(products)} 个商品")
                return products

        # 方案2: Requests方案
        logger.info("[京东] Playwright不可用，尝试Requests方案")
        html = await fetch_with_requests(url, session, referer="https://www.jd.com/")
        if html:
            products = self._parse_page(html, keyword)
            if products:
                logger.info(f"[京东] Requests抓取成功，获取 {len(products)} 个商品")
                return products

        # 方案3: 京东API接口
        products = await self._fetch_via_api(keyword, session)
        if products:
            logger.info(f"[京东] API接口抓取成功，获取 {len(products)} 个商品")
            return products

        logger.warning(f"[京东] 所有方案均未获取到数据")
        return []

    def _parse_page(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")
            items = soup.select('.gl-item, .j-sku-item, li[class*="item"], .goods-item')

            for item in items[:30]:
                try:
                    sku = item.get("data-sku", "") or item.get("sku", "")

                    title = ""
                    title_elem = item.select_one('.p-name em, .p-name a, .goods-title, .p-title')
                    if title_elem:
                        title = clean_text(title_elem.get_text())

                    if not title or len(title) < 3:
                        continue

                    price = None
                    price_elem = item.select_one('.p-price i, .p-price em, .goods-price, .price')
                    if price_elem:
                        price = parse_price(price_elem.get_text())

                    sales = None
                    sales_elem = item.select_one('.p-commit strong, .sales-volume, .comment')
                    if sales_elem:
                        sales = parse_sales(sales_elem.get_text())

                    seller = ""
                    seller_elem = item.select_one('.p-shop a, .p-shop span, .shop-name')
                    if seller_elem:
                        seller = seller_elem.get("title", seller_elem.get_text(strip=True))

                    product_url = ""
                    link_elem = item.select_one('.p-img a, .goods-img a, a[href*="item.jd.com"]')
                    if link_elem:
                        href = link_elem.get("href", "")
                        if href.startswith("//"):
                            product_url = "https:" + href
                        elif href.startswith("/"):
                            product_url = "https://item.jd.com" + href
                        elif href.startswith("http"):
                            product_url = href
                    elif sku:
                        product_url = f"https://item.jd.com/{sku}.html"

                    img_url = ""
                    img_elem = item.select_one('.p-img img, .goods-img img')
                    if img_elem:
                        src = img_elem.get("src", "") or img_elem.get("data-lazy-img", "")
                        if src.startswith("//"):
                            img_url = "https:" + src
                        elif src.startswith("http"):
                            img_url = src

                    product_id = sku if sku else hashlib.md5(title.encode()).hexdigest()[:16]

                    products.append({
                        "platform": self.platform,
                        "product_id": str(product_id),
                        "title": title,
                        "price": price,
                        "seller_name": clean_text(seller),
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

    async def _fetch_via_api(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """通过京东搜索API获取数据"""
        products = []
        api_urls = [
            f"https://search-x.jd.com/Search?keyword={quote_plus(keyword)}&enc=utf-8",
        ]
        try:
            for url in api_urls:
                html = await fetch_with_requests(url, session)
                if html:
                    products = self._parse_page(html, keyword)
                    if products:
                        break
        except Exception as e:
            logger.debug(f"京东API抓取失败: {e}")
        return products


class DouyinSpider:
    """抖音爬虫 - 真实Requests搜索请求"""

    def __init__(self):
        self.platform = PlatformEnum.DOUYIN

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        logger.info(f"[抖音] 搜索关键词: {keyword}")
        products = []

        # 方案1: 真实搜索API请求
        products = await self._search_api(keyword, session)
        if products:
            logger.info(f"[抖音] API搜索成功，获取 {len(products)} 个结果")
            return products

        # 方案2: Web页面抓取
        logger.info("[抖音] API搜索失败，尝试Web页面抓取")
        products = await self._search_web(keyword, session)
        if products:
            logger.info(f"[抖音] Web页面抓取成功，获取 {len(products)} 个结果")
            return products

        # 方案3: Playwright动态渲染
        logger.info("[抖音] 尝试Playwright方案")
        products = await self._search_playwright(keyword)
        if products:
            logger.info(f"[抖音] Playwright抓取成功，获取 {len(products)} 个结果")
            return products

        logger.warning(f"[抖音] 所有方案均未获取到数据")
        return []

    async def _search_api(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """调用抖音搜索API"""
        products = []

        endpoints = [
            {
                "url": f"https://www.douyin.com/aweme/v1/web/general/search/single/",
                "params": {"keyword": keyword, "count": 20, "offset": 0, "search_channel": "aweme_general"},
            },
            {
                "url": f"https://www.douyin.com/aweme/v1/web/search/item/",
                "params": {"keyword": keyword, "count": 20, "offset": 0, "search_channel": "aweme_goods_search"},
            },
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.douyin.com/",
        }

        for ep in endpoints:
            try:
                async with session.get(ep["url"], params=ep["params"], headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            items = data.get("data", [])
                            if items:
                                for item in items[:15]:
                                    try:
                                        aweme = item.get("aweme_info", item)
                                        desc = aweme.get("desc", "") or aweme.get("aweme_name", "")
                                        if not desc:
                                            continue

                                        author = aweme.get("author", {})
                                        stats = aweme.get("statistics", {})

                                        cover = ""
                                        video = aweme.get("video", {})
                                        if video:
                                            covers = video.get("cover", {}).get("url_list", [])
                                            if covers:
                                                cover = covers[0]

                                        aweme_id = aweme.get("aweme_id", "")
                                        if not aweme_id:
                                            aweme_id = hashlib.md5(desc.encode()).hexdigest()[:16]

                                        products.append({
                                            "platform": self.platform,
                                            "product_id": str(aweme_id),
                                            "title": clean_text(desc),
                                            "price": None,
                                            "seller_name": author.get("nickname", "抖音用户"),
                                            "seller_id": str(author.get("uid", "")),
                                            "seller_level": None,
                                            "seller_fans": author.get("follower_count", 0),
                                            "product_url": f"https://www.douyin.com/video/{aweme_id}",
                                            "image_urls": [cover] if cover else [],
                                            "category": keyword,
                                            "sales_volume": stats.get("digg_count", 0),
                                        })
                                    except Exception:
                                        continue

                                if products:
                                    break
                        except Exception as e:
                            logger.debug(f"解析抖音API响应失败: {e}")
                            continue
            except Exception as e:
                logger.debug(f"抖音API请求失败: {e}")
                continue

        return products

    async def _search_web(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """通过Web页面提取数据"""
        products = []
        try:
            url = f"https://www.douyin.com/search/{quote_plus(keyword)}?type=general"
            html = await fetch_with_requests(url, session, referer="https://www.douyin.com/")
            if not html:
                return []

            soup = BeautifulSoup(html, "lxml")

            script_tag = soup.find("script", id="RENDER_DATA")
            if script_tag:
                try:
                    import urllib.parse
                    data_str = urllib.parse.unquote(script_tag.string)
                    data = json.loads(data_str)

                    def find_items(obj, depth=0):
                        results = []
                        if depth > 10:
                            return results
                        if isinstance(obj, dict):
                            if "awemeId" in obj or "desc" in obj:
                                results.append(obj)
                            for v in obj.values():
                                results.extend(find_items(v, depth + 1))
                        elif isinstance(obj, list):
                            for item in obj:
                                results.extend(find_items(item, depth + 1))
                        return results

                    items = find_items(data)
                    seen = set()
                    for item in items[:20]:
                        try:
                            desc = item.get("desc", "")
                            if not desc or desc in seen:
                                continue
                            seen.add(desc)
                            aweme_id = item.get("awemeId", hashlib.md5(desc.encode()).hexdigest()[:16])
                            author = item.get("author", {})
                            products.append({
                                "platform": self.platform,
                                "product_id": str(aweme_id),
                                "title": clean_text(desc),
                                "price": None,
                                "seller_name": author.get("nickname", ""),
                                "seller_id": "",
                                "seller_level": None,
                                "seller_fans": author.get("followerCount"),
                                "product_url": f"https://www.douyin.com/video/{aweme_id}",
                                "image_urls": [],
                                "category": keyword,
                                "sales_volume": None,
                            })
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"解析抖音页面数据失败: {e}")

            if not products:
                cards = soup.select('[class*="video-card"], [class*="search-item"], div[data-e2e*="item"]')
                for card in cards[:15]:
                    try:
                        title_elem = card.select_one('[class*="title"], [class*="desc"], p')
                        title = title_elem.get_text(strip=True) if title_elem else ""
                        if title and len(title) > 5:
                            products.append({
                                "platform": self.platform,
                                "product_id": hashlib.md5(title.encode()).hexdigest()[:16],
                                "title": clean_text(title),
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
            logger.debug(f"抖音Web抓取失败: {e}")

        return products

    async def _search_playwright(self, keyword: str) -> List[Dict[str, Any]]:
        """使用Playwright抓取抖音"""
        products = []
        try:
            url = f"https://www.douyin.com/search/{quote_plus(keyword)}?type=general"
            html = await PlaywrightWrapper.fetch(url, wait_time=6)
            if html:
                products = self._parse_douyin_html(html, keyword)
        except Exception as e:
            logger.debug(f"抖音Playwright抓取失败: {e}")
        return products

    def _parse_douyin_html(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")
            cards = soup.select('[class*="video-card"], [class*="search-item"], [data-e2e*="item"]')
            for card in cards[:15]:
                try:
                    title_elem = card.select_one('[class*="title"], [class*="desc"]')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    if title and len(title) > 5:
                        products.append({
                            "platform": self.platform,
                            "product_id": hashlib.md5(title.encode()).hexdigest()[:16],
                            "title": clean_text(title),
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
        except Exception:
            pass
        return products


class PDDPlatSpider:
    """拼多多爬虫"""

    def __init__(self):
        self.platform = PlatformEnum.PDD

    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        logger.info(f"[拼多多] 搜索关键词: {keyword}")
        products = []
        try:
            url = f"https://mobile.yangkeduo.com/search_result.html?search_key={quote_plus(keyword)}"
            html = await PlaywrightWrapper.fetch(url, wait_time=5)
            if html:
                products = self._parse_page(html, keyword)
                if products:
                    logger.info(f"[拼多多] 抓取成功，获取 {len(products)} 个商品")
                    return products
        except Exception as e:
            logger.debug(f"拼多多搜索失败: {e}")

        logger.warning(f"[拼多多] 未获取到数据")
        return []

    def _parse_page(self, html: str, keyword: str) -> List[Dict[str, Any]]:
        products = []
        try:
            soup = BeautifulSoup(html, "lxml")
            items = soup.select('[class*="goods"], [class*="item"]')
            for item in items[:15]:
                try:
                    title_elem = item.select_one('[class*="title"], [class*="name"]')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    if not title or len(title) < 3:
                        continue
                    price_elem = item.select_one('[class*="price"]')
                    price = parse_price(price_elem.get_text()) if price_elem else None
                    products.append({
                        "platform": self.platform,
                        "product_id": hashlib.md5(title.encode()).hexdigest()[:16],
                        "title": clean_text(title),
                        "price": price,
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
        except Exception:
            pass
        return products


class SpiderManager:
    """爬虫管理器"""

    def __init__(self):
        self.spiders: Dict[PlatformEnum, Any] = {}
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
            tasks = [spider.search(keyword, session) for spider in self.spiders.values()]
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

        async def bounded_crawl(kw):
            async with semaphore:
                return await self.crawl_keyword(kw)

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
                    existing = db.query(CrawledProduct).filter(CrawledProduct.content_hash == content_hash).first()
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
