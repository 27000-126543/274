import sys
from datetime import date, timedelta
from faker import Faker
import random

sys.path.insert(0, '.')

from database.connection import init_db, get_db
from database.models import (
    IntellectualProperty, IPTypeEnum, IPStatusEnum,
    Lawyer, InfringingParty, PlatformEnum, CrawledProduct,
    InfringementCase, InfringementStatusEnum, RiskLevelEnum
)
from modules import IntellectualPropertyManager, CaseManager
from utils.logger import logger

fake = Faker('zh_CN')


def seed_sample_data():
    logger.info("开始初始化示例数据...")
    init_db()

    with get_db() as db:
        existing_ips = db.query(IntellectualProperty).count()
        if existing_ips > 0:
            logger.info("数据库已有数据，跳过初始化")
            return

        ip_manager = IntellectualPropertyManager(db)

        sample_ips = [
            {
                "ip_type": IPTypeEnum.PATENT,
                "ip_number": "ZL202310123456.7",
                "name": "智能穿戴设备及其控制方法",
                "owner": "示例科技有限公司",
                "description": "本发明涉及一种新型智能穿戴设备，采用创新的生物传感器技术，可实时监测用户健康数据。",
                "application_date": date(2023, 1, 15),
                "grant_date": date(2023, 8, 20),
                "expiration_date": date(2043, 1, 14),
                "status": IPStatusEnum.ACTIVE,
                "category": "电子设备",
                "keywords": ["智能穿戴", "健康监测", "生物传感器", "可穿戴设备"],
                "image_urls": ["https://picsum.photos/400/300?random=1"]
            },
            {
                "ip_type": IPTypeEnum.TRADEMARK,
                "ip_number": "第12345678号",
                "name": "示例品牌",
                "owner": "示例科技有限公司",
                "description": "示例品牌商标，第9类、第35类、第42类已注册。",
                "application_date": date(2022, 6, 1),
                "grant_date": date(2023, 1, 10),
                "expiration_date": date(2033, 1, 9),
                "status": IPStatusEnum.ACTIVE,
                "category": "商标",
                "keywords": ["示例品牌", "示例LOGO"],
                "image_urls": ["https://picsum.photos/400/300?random=2"]
            },
            {
                "ip_type": IPTypeEnum.COPYRIGHT,
                "ip_number": "国作登字-2023-F-00012345",
                "name": "智能家居控制系统软件V1.0",
                "owner": "示例科技有限公司",
                "description": "智能家居控制系统软件，支持多设备联动和语音控制。",
                "application_date": date(2023, 3, 10),
                "grant_date": date(2023, 4, 5),
                "expiration_date": date(2073, 12, 31),
                "status": IPStatusEnum.ACTIVE,
                "category": "计算机软件",
                "keywords": ["智能家居", "控制软件", "物联网"],
                "image_urls": ["https://picsum.photos/400/300?random=3"]
            },
            {
                "ip_type": IPTypeEnum.PATENT,
                "ip_number": "ZL202320987654.3",
                "name": "高效散热电子装置",
                "owner": "示例科技有限公司",
                "description": "本实用新型涉及电子设备散热技术领域，特别涉及一种高效散热结构。",
                "application_date": date(2023, 5, 20),
                "grant_date": date(2023, 11, 8),
                "expiration_date": date(2033, 5, 19),
                "status": IPStatusEnum.ACTIVE,
                "category": "电子设备",
                "keywords": ["散热", "电子装置", "热管理"],
                "image_urls": ["https://picsum.photos/400/300?random=4"]
            },
            {
                "ip_type": IPTypeEnum.TRADEMARK,
                "ip_number": "第87654321号",
                "name": "智享生活",
                "owner": "示例科技有限公司",
                "description": "智享生活品牌商标，用于智能家居产品系列。",
                "application_date": date(2022, 9, 15),
                "grant_date": date(2023, 4, 20),
                "expiration_date": date(2033, 4, 19),
                "status": IPStatusEnum.ACTIVE,
                "category": "商标",
                "keywords": ["智享生活", "智能家居"],
                "image_urls": ["https://picsum.photos/400/300?random=5"]
            }
        ]

        for ip_data in sample_ips:
            ip_manager.add_ip(**ip_data)

        lawyers = [
            {"name": "张三", "email": "zhangsan@company.com", "phone": "13800000001", "position": "法务专员"},
            {"name": "李四", "email": "lisi@company.com", "phone": "13800000002", "position": "法务专员"},
            {"name": "王五", "email": "wangwu@company.com", "phone": "13800000003", "position": "高级法务"},
            {"name": "赵六", "email": "zhaoliu@company.com", "phone": "13800000004", "position": "法务总监"},
        ]

        for lawyer_data in lawyers:
            lawyer = Lawyer(**lawyer_data)
            db.add(lawyer)

        platforms = [PlatformEnum.TAOBAO, PlatformEnum.JD, PlatformEnum.DOUYIN, PlatformEnum.PDD]
        seller_names = [
            "诚信电子专营店", "数码优品旗舰店", "智能生活专营店",
            "科技创新店", "品质数码馆", "未来科技专卖店",
            "智能家居体验馆", "数码配件批发店", "优选电子商城"
        ]

        for i in range(20):
            platform = random.choice(platforms)
            seller_name = random.choice(seller_names)
            fans_count = random.randint(100, 100000)

            party = InfringingParty(
                name=seller_name,
                contact_person=fake.name(),
                contact_email=fake.email(),
                contact_phone=fake.phone_number(),
                platform=platform,
                shop_url=f"https://shop.example.com/{seller_name}",
                shop_level=random.randint(1, 5),
                fans_count=fans_count,
                complaint_count=random.randint(0, 5)
            )
            db.add(party)

        for i in range(50):
            platform = random.choice(platforms)
            ip_ref = random.choice(sample_ips)
            title_variations = [
                f"新款{ip_ref['name']}",
                f"升级版{ip_ref['name']}同款",
                f"热销{ip_ref['keywords'][0]}产品",
                f"仿{ip_ref['name']}设计",
                f"同款{ip_ref['category']}"
            ]

            product = CrawledProduct(
                platform=platform,
                product_id=f"prod_{fake.uuid4()[:8]}",
                title=random.choice(title_variations),
                description=fake.text(max_nb_chars=200),
                price=round(random.uniform(50, 2000), 2),
                seller_name=random.choice(seller_names),
                seller_id=f"seller_{random.randint(1000, 9999)}",
                seller_level=random.randint(1, 5),
                seller_fans=random.randint(100, 50000),
                product_url=f"https://item.example.com/{random.randint(100000, 999999)}",
                image_urls=[f"https://picsum.photos/400/300?random={random.randint(10, 100)}"],
                category=ip_ref['category'],
                sales_volume=random.randint(10, 5000),
                content_hash=fake.md5()
            )
            db.add(product)

        db.commit()
        logger.info("示例数据初始化完成")
        logger.info(f"  - 知识产权: {len(sample_ips)} 件")
        logger.info(f"  - 法务人员: {len(lawyers)} 人")
        logger.info(f"  - 侵权方: 20 个")
        logger.info(f"  - 抓取商品: 50 个")


if __name__ == "__main__":
    seed_sample_data()
