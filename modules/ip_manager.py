from datetime import date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from database.models import IntellectualProperty, IPTypeEnum, IPStatusEnum
from utils.logger import logger


class IntellectualPropertyManager:
    def __init__(self, db: Session):
        self.db = db

    def add_ip(
        self,
        ip_type: IPTypeEnum,
        ip_number: str,
        name: str,
        owner: str,
        description: Optional[str] = None,
        application_date: Optional[date] = None,
        grant_date: Optional[date] = None,
        expiration_date: Optional[date] = None,
        status: IPStatusEnum = IPStatusEnum.ACTIVE,
        category: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        image_urls: Optional[List[str]] = None,
        document_url: Optional[str] = None
    ) -> IntellectualProperty:
        existing = self.db.query(IntellectualProperty).filter(
            IntellectualProperty.ip_number == ip_number
        ).first()
        if existing:
            logger.warning(f"知识产权 {ip_number} 已存在，跳过添加")
            return existing

        ip = IntellectualProperty(
            ip_type=ip_type,
            ip_number=ip_number,
            name=name,
            description=description,
            owner=owner,
            application_date=application_date,
            grant_date=grant_date,
            expiration_date=expiration_date,
            status=status,
            category=category,
            keywords=keywords or [],
            image_urls=image_urls or [],
            document_url=document_url
        )
        self.db.add(ip)
        self.db.commit()
        self.db.refresh(ip)
        logger.info(f"成功添加知识产权: {ip_number} - {name}")
        return ip

    def get_ip_by_number(self, ip_number: str) -> Optional[IntellectualProperty]:
        return self.db.query(IntellectualProperty).filter(
            IntellectualProperty.ip_number == ip_number
        ).first()

    def get_ip_by_id(self, ip_id: int) -> Optional[IntellectualProperty]:
        return self.db.query(IntellectualProperty).filter(
            IntellectualProperty.id == ip_id
        ).first()

    def list_ips(
        self,
        ip_type: Optional[IPTypeEnum] = None,
        status: Optional[IPStatusEnum] = None,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[IntellectualProperty]:
        query = self.db.query(IntellectualProperty)

        if ip_type:
            query = query.filter(IntellectualProperty.ip_type == ip_type)
        if status:
            query = query.filter(IntellectualProperty.status == status)
        if category:
            query = query.filter(IntellectualProperty.category == category)
        if keyword:
            query = query.filter(
                (IntellectualProperty.name.like(f"%{keyword}%")) |
                (IntellectualProperty.ip_number.like(f"%{keyword}%")) |
                (IntellectualProperty.description.like(f"%{keyword}%"))
            )

        return query.offset(skip).limit(limit).all()

    def get_all_active_ips(self) -> List[IntellectualProperty]:
        return self.db.query(IntellectualProperty).filter(
            IntellectualProperty.status == IPStatusEnum.ACTIVE
        ).all()

    def update_ip(self, ip_id: int, **kwargs) -> Optional[IntellectualProperty]:
        ip = self.get_ip_by_id(ip_id)
        if not ip:
            logger.warning(f"知识产权 ID {ip_id} 不存在")
            return None

        for key, value in kwargs.items():
            if hasattr(ip, key) and value is not None:
                setattr(ip, key, value)

        self.db.commit()
        self.db.refresh(ip)
        logger.info(f"更新知识产权: {ip.ip_number}")
        return ip

    def delete_ip(self, ip_id: int) -> bool:
        ip = self.get_ip_by_id(ip_id)
        if not ip:
            return False

        self.db.delete(ip)
        self.db.commit()
        logger.info(f"删除知识产权: {ip.ip_number}")
        return True

    def batch_import(self, ip_data_list: List[Dict[str, Any]]) -> Dict[str, int]:
        success_count = 0
        skip_count = 0
        error_count = 0

        for ip_data in ip_data_list:
            try:
                result = self.add_ip(**ip_data)
                if result:
                    success_count += 1
                else:
                    skip_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"批量导入知识产权失败: {ip_data.get('ip_number')}, 错误: {e}")

        return {
            "success": success_count,
            "skipped": skip_count,
            "errors": error_count
        }

    def check_expiration(self, days_before: int = 30) -> List[IntellectualProperty]:
        from datetime import timedelta
        today = date.today()
        warning_date = today + timedelta(days=days_before)

        expiring_ips = self.db.query(IntellectualProperty).filter(
            IntellectualProperty.status == IPStatusEnum.ACTIVE,
            IntellectualProperty.expiration_date <= warning_date,
            IntellectualProperty.expiration_date >= today
        ).all()

        if expiring_ips:
            logger.warning(f"发现 {len(expiring_ips)} 个即将过期的知识产权")

        return expiring_ips
