import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}
resp = requests.get('https://search.jd.com/Search?keyword=手机&enc=utf-8', headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, 'lxml')
print('页面标题:', soup.title.string if soup.title else '无标题')
print()
print('前15个li元素的class:')
for i, li in enumerate(soup.find_all('li')[:20]):
    cls = li.get('class', [])
    if cls:
        print(f'  [{i}] class={cls}')

print()
skus = soup.find_all(attrs={'data-sku': True})
print(f'找到 {len(skus)} 个带data-sku的元素')
if skus:
    for i, s in enumerate(skus[:5]):
        print(f'  [{i}] tag={s.name}, class={s.get("class",[])}')
        text = s.get_text(strip=True)[:100]
        print(f'      文本: {text[:80]}')

# 保存HTML到文件
with open('d:/新项目/274/jd_debug.html', 'w', encoding='utf-8') as f:
    f.write(resp.text)
print(f'\nHTML已保存到jd_debug.html, 大小: {len(resp.text)} bytes')
