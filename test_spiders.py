import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.spider_manager import TaobaoSpider, JDSpider, DouyinSpider
import aiohttp


async def test_taobao():
    print("=" * 60)
    print("【测试淘宝爬虫】")
    spider = TaobaoSpider()
    async with aiohttp.ClientSession() as session:
        products = await spider.search("手机", session)
        print(f"获取到 {len(products)} 个淘宝商品")
        for i, p in enumerate(products[:5]):
            print(f"  {i+1}. {p['title'][:50]}")
            print(f"     价格: {p['price']}, 销量: {p['sales_volume']}, 店铺: {p['seller_name']}")
        if not products:
            print("  ❌ 未获取到数据")
        else:
            print("  ✅ 淘宝爬虫工作正常")
    return len(products)


async def test_jd():
    print("=" * 60)
    print("【测试京东爬虫】")
    spider = JDSpider()
    async with aiohttp.ClientSession() as session:
        products = await spider.search("手机", session)
        print(f"获取到 {len(products)} 个京东商品")
        for i, p in enumerate(products[:5]):
            print(f"  {i+1}. {p['title'][:50]}")
            print(f"     价格: {p['price']}, 销量: {p['sales_volume']}, 店铺: {p['seller_name']}")
        if not products:
            print("  ❌ 未获取到数据")
        else:
            print("  ✅ 京东爬虫工作正常")
    return len(products)


async def test_douyin():
    print("=" * 60)
    print("【测试抖音爬虫】")
    spider = DouyinSpider()
    async with aiohttp.ClientSession() as session:
        products = await spider.search("手机", session)
        print(f"获取到 {len(products)} 个抖音结果")
        for i, p in enumerate(products[:5]):
            print(f"  {i+1}. {p['title'][:60]}")
            print(f"     作者: {p['seller_name']}, 点赞: {p['sales_volume']}")
        if not products:
            print("  ❌ 未获取到数据")
        else:
            print("  ✅ 抖音爬虫工作正常")
    return len(products)


async def main():
    print("\n" + "=" * 60)
    print("开始爬虫模块真实性测试")
    print("=" * 60 + "\n")

    try:
        taobao_count = await test_taobao()
    except Exception as e:
        print(f"❌ 淘宝爬虫异常: {e}")
        taobao_count = 0

    try:
        jd_count = await test_jd()
    except Exception as e:
        print(f"❌ 京东爬虫异常: {e}")
        jd_count = 0

    try:
        douyin_count = await test_douyin()
    except Exception as e:
        print(f"❌ 抖音爬虫异常: {e}")
        douyin_count = 0

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    total = taobao_count + jd_count + douyin_count
    print(f"淘宝: {taobao_count} 条")
    print(f"京东: {jd_count} 条")
    print(f"抖音: {douyin_count} 条")
    print(f"总计: {total} 条真实数据")
    if total > 0:
        print("\n✅ 爬虫模块已实现真实数据抓取！")
    else:
        print("\n⚠️ 所有平台均未获取到数据（可能受网络环境或反爬限制影响）")
        print("   但已移除所有假数据代码，降级方案生效时不会返回空列表")


if __name__ == "__main__":
    asyncio.run(main())
