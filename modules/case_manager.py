import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from database.models import (
    InfringementCase, InfringingParty, CrawledProduct,
    RiskLevelEnum, InfringementStatusEnum, OperationTypeEnum,
    Lawyer
)
from database.connection import get_db
from utils.logger import logger
from modules.operation_logger import OperationLogger


class RiskAssessor:
    def __init__(self):
        self.op_logger = OperationLogger()

    def assess_risk(self, product: CrawledProduct, infringing_party: Optional[InfringingParty] = None) -> RiskLevelEnum:
        score = 0

        if product.seller_level:
            if product.seller_level >= 5:
                score += 30
            elif product.seller_level >= 3:
                score += 20
            else:
                score += 10

        if product.seller_fans:
            if product.seller_fans >= 100000:
                score += 30
            elif product.seller_fans >= 10000:
                score += 20
            elif product.seller_fans >= 1000:
                score += 10

        if product.sales_volume:
            if product.sales_volume >= 10000:
                score += 25
            elif product.sales_volume >= 1000:
                score += 15
            elif product.sales_volume >= 100:
                score += 5

        if product.price:
            if product.price >= 1000:
                score += 15
            elif product.price >= 100:
                score += 10
            else:
                score += 5

        if infringing_party and infringing_party.complaint_count:
            if infringing_party.complaint_count >= 3:
                score += 30
            elif infringing_party.complaint_count >= 2:
                score += 20
            elif infringing_party.complaint_count >= 1:
                score += 10

        if score >= 70:
            return RiskLevelEnum.HIGH
        elif score >= 40:
            return RiskLevelEnum.MEDIUM
        else:
            return RiskLevelEnum.LOW

    def get_or_create_infringing_party(self, db: Session, product: CrawledProduct) -> InfringingParty:
        party = db.query(InfringingParty).filter(
            InfringingParty.name == product.seller_name,
            InfringingParty.platform == product.platform
        ).first()

        if not party:
            party = InfringingParty(
                name=product.seller_name or "未知商家",
                platform=product.platform,
                shop_url=f"https://shop.example.com/{product.seller_id}" if product.seller_id else "",
                shop_level=product.seller_level,
                fans_count=product.seller_fans
            )
            db.add(party)
            db.flush()
            logger.info(f"创建新侵权方: {party.name}")

        return party


class CaseManager:
    def __init__(self):
        self.risk_assessor = RiskAssessor()
        self.op_logger = OperationLogger()

    def _generate_case_number(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        uuid_part = uuid.uuid4().hex[:8].upper()
        return f"IP-{date_str}-{uuid_part}"

    def create_infringement_case(
        self,
        ip_id: int,
        product_id: int,
        similarity_score: float,
        source_type: str = "auto_crawl",
        notes: Optional[str] = None
    ) -> InfringementCase:
        with get_db() as db:
            product = db.query(CrawledProduct).filter(CrawledProduct.id == product_id).first()
            if not product:
                raise ValueError(f"商品 {product_id} 不存在")

            infringing_party = self.risk_assessor.get_or_create_infringing_party(db, product)
            risk_level = self.risk_assessor.assess_risk(product, infringing_party)

            case = InfringementCase(
                case_number=self._generate_case_number(),
                ip_id=ip_id,
                product_id=product_id,
                infringing_party_id=infringing_party.id,
                similarity_score=similarity_score,
                status=InfringementStatusEnum.CONFIRMED,
                risk_level=risk_level,
                source_type=source_type,
                notes=notes
            )

            if risk_level == RiskLevelEnum.HIGH:
                case.first_response_due = datetime.now() + timedelta(days=15)
                case.status = InfringementStatusEnum.LITIGATION_PREPARED

            infringing_party.complaint_count = (infringing_party.complaint_count or 0) + 1

            db.add(case)
            db.commit()
            db.refresh(case)

            self.op_logger.log_operation(
                operation_type=OperationTypeEnum.MARK_INFRINGEMENT,
                target_id=case.id,
                target_type="infringement_case",
                details={
                    "case_number": case.case_number,
                    "similarity_score": similarity_score,
                    "risk_level": risk_level.value,
                    "infringing_party": infringing_party.name
                }
            )

            logger.info(f"创建侵权案件: {case.case_number}, 风险等级: {risk_level.value}, 相似度: {similarity_score}")
            return case

    def batch_create_cases(self, matches: List[Dict[str, Any]]) -> List[InfringementCase]:
        cases = []
        for match in matches:
            try:
                case = self.create_infringement_case(
                    ip_id=match["ip_id"],
                    product_id=match["product_id"],
                    similarity_score=match["final_score"],
                    notes=f"自动比对发现，文本相似度: {match['text_similarity']}, 图像相似度: {match['image_similarity']}"
                )
                cases.append(case)
            except Exception as e:
                logger.error(f"创建案件失败: {e}")

        logger.info(f"批量创建案件完成，成功 {len(cases)} 个")
        return cases

    def assign_lawyer(self, case_id: int, lawyer_id: int) -> Optional[InfringementCase]:
        with get_db() as db:
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
            lawyer = db.query(Lawyer).filter(Lawyer.id == lawyer_id).first()

            if not case or not lawyer:
                logger.warning(f"案件或律师不存在: case={case_id}, lawyer={lawyer_id}")
                return None

            case.assigned_lawyer = lawyer.name
            case.assigned_lawyer_email = lawyer.email
            case.status = InfringementStatusEnum.LITIGATION_IN_PROGRESS
            lawyer.case_count = (lawyer.case_count or 0) + 1

            db.commit()
            db.refresh(case)

            self.op_logger.log_operation(
                operation_type=OperationTypeEnum.ASSIGN_LAWYER,
                target_id=case.id,
                target_type="infringement_case",
                details={"lawyer": lawyer.name, "lawyer_id": lawyer_id}
            )

            logger.info(f"案件 {case.case_number} 已分配给律师 {lawyer.name}")
            return case

    def check_overdue_cases(self) -> List[InfringementCase]:
        with get_db() as db:
            now = datetime.now()
            overdue_cases = db.query(InfringementCase).filter(
                InfringementCase.first_response_due < now,
                InfringementCase.status.in_([
                    InfringementStatusEnum.LITIGATION_PREPARED,
                    InfringementStatusEnum.LITIGATION_IN_PROGRESS
                ])
            ).all()

            for case in overdue_cases:
                needs_reminder = False
                if case.last_reminder_at is None:
                    needs_reminder = True
                else:
                    time_since_reminder = now - case.last_reminder_at
                    if time_since_reminder >= timedelta(days=3):
                        needs_reminder = True

                if needs_reminder:
                    case.last_reminder_at = now
                    self._escalate_case(case)
                    db.commit()

                    self.op_logger.log_operation(
                        operation_type=OperationTypeEnum.ESCALATE,
                        target_id=case.id,
                        target_type="infringement_case",
                        details={"overdue_days": (now - case.first_response_due).days}
                    )

            logger.info(f"发现 {len(overdue_cases)} 个超期案件，已升级处理")
            return overdue_cases

    def _escalate_case(self, case: InfringementCase):
        logger.warning(
            f"案件 {case.case_number} 超期未处理，已升级至法务总监。"
            f"首次响应时限: {case.first_response_due}"
        )

    def update_case_status(
        self,
        case_id: int,
        status: InfringementStatusEnum,
        notes: Optional[str] = None
    ) -> Optional[InfringementCase]:
        with get_db() as db:
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
            if not case:
                return None

            case.status = status
            if notes:
                case.notes = (case.notes or "") + f"\n{datetime.now().isoformat()}: {notes}"

            db.commit()
            db.refresh(case)

            self.op_logger.log_operation(
                operation_type=OperationTypeEnum.UPDATE_STATUS,
                target_id=case.id,
                target_type="infringement_case",
                details={"new_status": status.value, "notes": notes}
            )

            logger.info(f"案件 {case.case_number} 状态更新为: {status.value}")
            return case

    def get_case_by_number(self, case_number: str) -> Optional[InfringementCase]:
        with get_db() as db:
            return db.query(InfringementCase).filter(
                InfringementCase.case_number == case_number
            ).first()

    def list_cases(
        self,
        status: Optional[InfringementStatusEnum] = None,
        risk_level: Optional[RiskLevelEnum] = None,
        infringing_party_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[InfringementCase]:
        with get_db() as db:
            query = db.query(InfringementCase)

            if status:
                query = query.filter(InfringementCase.status == status)
            if risk_level:
                query = query.filter(InfringementCase.risk_level == risk_level)
            if infringing_party_id:
                query = query.filter(InfringementCase.infringing_party_id == infringing_party_id)
            if start_date:
                query = query.filter(InfringementCase.created_at >= start_date)
            if end_date:
                query = query.filter(InfringementCase.created_at <= end_date)

            return query.order_by(InfringementCase.created_at.desc()).offset(skip).limit(limit).all()
