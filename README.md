# 企业级知识产权侵权监测与维权管理系统

## 系统概述

本系统是一个企业级自动化在线监测外部知识产权侵权与维权管理平台，支持从电商平台、社交媒体等多渠道自动抓取商品信息，通过智能相似度比对识别疑似侵权，自动进行风险评估和分级处理，全流程管理维权案件。

## 核心功能

### 1. 多平台数据抓取
- 支持淘宝、京东、拼多多、抖音、小红书等主流电商平台
- 高并发异步爬取，支持每日百万级商品数据处理
- 自动去重，基于内容哈希避免重复存储

### 2. 智能相似度比对
- 文本相似度：融合编辑距离、序列匹配、Jaccard系数、TF-IDF余弦相似度
- 图像相似度：基于感知哈希（pHash）算法
- 综合评分：文本占70%，图像占30%，超过80%自动标记疑似侵权

### 3. 证据包自动生成
- 网页截图（Selenium无头浏览器）
- 商品图片与知识产权图片下载
- 元数据与时间戳记录
- MD5哈希完整性校验
- 自动打包为ZIP压缩包

### 4. 风险评估与分级处理
- **低风险**（小商家、粉丝少、销量低）：自动发送电子警告函，追踪回执
- **中风险**（中等规模商家）：人工审核后决定处理方式
- **高风险**（大商家、粉丝多、销量高）：生成诉讼文档模板，指派法务专员

### 5. 警告函管理
- 自动生成标准格式警告函
- 支持SMTP邮件发送（含附件）
- 回执状态追踪
- 模拟发送模式（无SMTP配置时）

### 6. 诉讼管理
- 自动生成民事诉讼起诉状模板
- 案件预分析报告（胜诉概率、赔偿预估、成本分析）
- 15天首次响应时限设置
- 超期未处理自动升级至法务总监，每3天催办
- 批量诉讼建议（同一侵权方累计3次以上）

### 7. 维权台账管理
- 记录赔偿金额与各项成本（律师费、诉讼费、取证费等）
- 自动计算净收益
- 支持按时间段汇总统计

### 8. 线下线索管理
- 手动录入线下侵权线索
- 自动查重与合并（相似度≥80%）
- 支持关联至对应案件

### 9. 周报自动生成
- 每周一自动生成
- 包含：案件数量、处理状态、成功率、平均响应时长
- 趋势图表（饼图、柱状图、折线图）
- 输出格式：PDF + Excel

### 10. 查询与导出
- 组合查询：侵权方名称、专利号、时间段、状态、风险等级
- 全生命周期记录查询
- 批量导出Excel

### 11. 操作日志
- 所有操作详细记录（抓取、比对、标记、警告、诉讼等）
- 支持按操作类型、操作人、时间范围检索

## 系统架构

```
ip_protection/
├── config/              # 配置模块
│   ├── __init__.py
│   └── settings.py      # 系统配置（基于Pydantic）
├── database/            # 数据库层
│   ├── __init__.py
│   ├── connection.py    # 数据库连接与会话管理
│   └── models.py        # ORM数据模型（13张表）
├── modules/             # 业务模块
│   ├── __init__.py
│   ├── ip_manager.py    # 知识产权库管理
│   ├── spider_manager.py# 多平台爬虫管理
│   ├── similarity_engine.py  # 相似度比对引擎
│   ├── evidence_generator.py # 证据包生成
│   ├── case_manager.py  # 案件管理与风险评估
│   ├── litigation_manager.py # 警告函与诉讼管理
│   ├── ledger_manager.py# 台账与线下线索管理
│   ├── report_manager.py# 报告生成与批量诉讼
│   ├── export_manager.py# 查询与导出
│   └── operation_logger.py  # 操作日志
├── utils/               # 工具模块
│   ├── __init__.py
│   └── logger.py        # 日志配置（Loguru）
├── evidence/            # 证据存储目录（自动创建）
│   ├── reports/         # 周报告
│   ├── exports/         # 导出文件
│   └── batch_suggestions/  # 批量诉讼建议
├── logs/                # 日志目录（自动创建）
├── main.py              # 主入口与调度器
├── examples.py          # 使用示例
├── seed_data.py         # 示例数据初始化
├── requirements.txt     # Python依赖
├── .env.example         # 环境变量示例
└── README.md            # 项目说明
```

## 快速开始

### 1. 环境要求

- Python 3.9+
- SQLite 3.x（默认）或 PostgreSQL 12+
- Chrome/Chromium 浏览器（用于截图功能，可选）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，根据需要修改配置：

```bash
cp .env.example .env
```

关键配置项：
- `DATABASE_URL`: 数据库连接字符串
- `SIMILARITY_THRESHOLD`: 相似度阈值，默认0.80
- `SMTP_*`: 邮件服务器配置（发送警告函）
- `COMPANY_NAME`: 公司名称

### 4. 初始化数据库

```bash
python main.py init
```

### 5. 加载示例数据（可选）

```bash
python seed_data.py
```

### 6. 运行示例

```bash
python examples.py
```

### 7. 执行单次完整任务

```bash
python main.py run
```

### 8. 启动定时调度器

```bash
python main.py scheduler
```

定时任务配置：
- 每天凌晨 02:00：自动爬取与比对
- 每天早上 08:00：案件处理（发送警告函、生成诉讼文档）
- 每周一早上 09:00：生成周报告
- 每 6 小时：系统健康检查

## 数据库模型

### 核心数据表

| 表名 | 说明 |
|------|------|
| `intellectual_properties` | 知识产权库（专利、商标、著作权） |
| `crawled_products` | 抓取的商品信息 |
| `infringing_parties` | 侵权方信息 |
| `infringement_cases` | 侵权案件主表 |
| `evidences` | 证据文件 |
| `warning_letters` | 警告函记录 |
| `litigations` | 诉讼案件 |
| `rights_protection_ledgers` | 维权台账 |
| `offline_clues` | 线下侵权线索 |
| `operation_logs` | 操作日志 |
| `weekly_reports` | 周报告记录 |
| `lawyers` | 法务人员 |

## API使用示例

### 1. 添加知识产权

```python
from modules import IntellectualPropertyManager
from database.connection import get_db
from database.models import IPTypeEnum, IPStatusEnum
from datetime import date

with get_db() as db:
    ip_mgr = IntellectualPropertyManager(db)
    ip = ip_mgr.add_ip(
        ip_type=IPTypeEnum.PATENT,
        ip_number="ZL202410000001.0",
        name="新型节能技术",
        owner="示例科技有限公司",
        description="本发明涉及一种新型节能技术",
        application_date=date(2024, 1, 1),
        grant_date=date(2024, 6, 1),
        expiration_date=date(2044, 1, 1),
        category="节能技术",
        keywords=["节能", "环保", "新能源"]
    )
```

### 2. 爬取与比对

```python
import asyncio
from modules import SpiderManager, SimilarityMatcher

spider_mgr = SpiderManager()
similarity_matcher = SimilarityMatcher()

# 爬取
products = asyncio.run(spider_mgr.crawl_multiple_keywords(["智能穿戴", "节能技术"]))
spider_mgr.save_products(products)

# 比对
suspected = similarity_matcher.get_suspected_matches()
```

### 3. 查询案件

```python
from modules import QueryManager, ExportManager
from database.models import RiskLevelEnum

query_mgr = QueryManager()
export_mgr = ExportManager()

# 组合查询
cases = query_mgr.query_cases(
    infringing_party_name="某某商家",
    risk_level=RiskLevelEnum.HIGH,
    start_date=date(2024, 1, 1)
)

# 导出
export_path = export_mgr.export_cases_to_excel(cases)
```

### 4. 录入线下线索

```python
from modules import OfflineClueManager
from datetime import date

clue_mgr = OfflineClueManager()
clue = clue_mgr.add_offline_clue(
    infringing_party_name="某某市场A12摊位",
    infringing_content="销售仿冒专利产品",
    infringing_location="深圳市福田区华强北",
    discovery_date=date.today(),
    reporter="巡查员 张三"
)
```

### 5. 台账记录

```python
from modules import LedgerManager
from datetime import date

ledger_mgr = LedgerManager()
entry = ledger_mgr.add_ledger_entry(
    case_id=1,
    record_date=date.today(),
    compensation_amount=50000.00,
    attorney_fee=8000.00,
    court_fee=2000.00,
    evidence_fee=1500.00,
    payment_status="completed"
)
```

## 性能优化建议

### 处理百万级数据

1. **数据库优化**
   - 使用 PostgreSQL 替代 SQLite
   - 为常用查询字段建立索引
   - 考虑分表策略（按时间分表）

2. **爬虫优化**
   - 增加 `MAX_CONCURRENT_SPIDERS` 配置
   - 使用代理IP池避免封禁
   - 分布式爬取（Celery + Redis）

3. **相似度比对优化**
   - 使用向量数据库（如 Milvus、FAISS）
   - 预计算知识产权特征向量
   - 分批处理，避免内存溢出

4. **缓存策略**
   - 使用 Redis 缓存热点数据
   - 商品内容哈希缓存，避免重复比对

## 扩展开发

### 新增电商平台

1. 继承 `BaseSpider` 类
2. 实现 `search()` 和 `parse_product()` 方法
3. 在 `SpiderManager._init_spiders()` 中注册

### 新增相似度算法

1. 在 `TextSimilarityEngine` 或 `ImageSimilarityEngine` 中添加方法
2. 在 `compute_*_similarity()` 中调整权重

### 集成第三方服务

- 企业邮箱API（阿里云邮件、腾讯企业邮）
- 电子存证服务（保全网、易保全）
- 市场监管投诉接口
- 法院网上立案系统

## 注意事项

1. 本系统仅供内部管理使用，爬取数据请遵守各平台robots协议
2. 证据生成仅作辅助，正式诉讼建议咨询专业律师并进行公证
3. 建议定期备份数据库和证据文件
4. SMTP密码等敏感信息请勿提交至代码仓库

## 技术栈

- **框架**: Python 3.9+, SQLAlchemy 2.0, Pydantic
- **爬虫**: aiohttp, BeautifulSoup4, Selenium
- **NLP**: jieba, scikit-learn, python-Levenshtein
- **图像**: Pillow, imagehash
- **报告**: ReportLab, Pandas, XlsxWriter, Matplotlib, Seaborn
- **调度**: APScheduler
- **日志**: Loguru
- **重试**: Tenacity

## License

本项目仅供学习和内部使用。
