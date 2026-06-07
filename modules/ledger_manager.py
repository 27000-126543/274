import uuid
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from difflib import SequenceMatcher
from database.models import (
    RightsProtectionLedger, InfringementCase, OfflineClue,
    InfringementStatusEnum, OperationTypeEnum
)
from database.connection import get_db
from utils.logger import logger
from modules.operation_logger import OperationLogger


class LedgerManager:
    def __init__(self):
        self.op_logger = OperationLogger()

    def add_ledger_entry(
        self,
        case_id: int,
        record_date: Optional[date] = None,
        compensation_amount: float = 0,
        attorney_fee: float = 0,
        court_fee: float = 0,
        evidence_fee: float = 0,
        other_cost: float = 0,
        payment_status: str = "pending",
        notes: Optional[str] = None
    ) -> RightsProtectionLedger:
        with get_db() as db:
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
            if not case:
                raise ValueError(f"案件 {case_id} 不存在")

            total_cost = attorney_fee + court_fee + evidence_fee + other_cost
            net_amount = compensation_amount - total_cost

            entry = RightsProtectionLedger(
                case_id=case_id,
                record_date=record_date or date.today(),
                compensation_amount=compensation_amount,
                attorney_fee=attorney_fee,
                court_fee=court_fee,
                evidence_fee=evidence_fee,
                other_cost=other_cost,
                total_cost=total_cost,
                net_amount=net_amount,
                payment_status=payment_status,
                notes=notes
            )
            db.add(entry)

            case.compensation_amount = (case.compensation_amount or 0) + compensation_amount
            case.cost_amount = (case.cost_amount or 0) + total_cost

            if compensation_amount > 0 or payment_status == "completed":
                case.status = InfringementStatusEnum.SETTLED
                case.settlement_date = record_date or date.today()

            db.commit()
            db.refresh(entry)

            logger.info(f"添加台账记录: 案件 {case.case_number}, 赔偿 {compensation_amount}, 成本 {total_cost}")
            return entry

    def get_ledger_by_case(self, case_id: int) -> List[RightsProtectionLedger]:
        with get_db() as db:
            return db.query(RightsProtectionLedger).filter(
                RightsProtectionLedger.case_id == case_id
            ).order_by(RightsProtectionLedger.record_date.desc()).all()

    def get_ledger_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        with get_db() as db:
            query = db.query(RightsProtectionLedger)

            if start_date:
                query = query.filter(RightsProtectionLedger.record_date >= start_date)
            if end_date:
                query = query.filter(RightsProtectionLedger.record_date <= end_date)

            entries = query.all()

            total_compensation = sum(e.compensation_amount for e in entries)
            total_attorney_fee = sum(e.attorney_fee for e in entries)
            total_court_fee = sum(e.court_fee for e in entries)
            total_evidence_fee = sum(e.evidence_fee for e in entries)
            total_other_cost = sum(e.other_cost for e in entries)
            total_cost = sum(e.total_cost for e in entries)
            total_net = sum(e.net_amount for e in entries)

            return {
                "entry_count": len(entries),
                "total_compensation": total_compensation,
                "total_attorney_fee": total_attorney_fee,
                "total_court_fee": total_court_fee,
                "total_evidence_fee": total_evidence_fee,
                "total_other_cost": total_other_cost,
                "total_cost": total_cost,
                "total_net_amount": total_net,
                "average_compensation": total_compensation / len(entries) if entries else 0
            }

    def update_ledger_entry(
        self,
        entry_id: int,
        **kwargs
    ) -> Optional[RightsProtectionLedger]:
        with get_db() as db:
            entry = db.query(RightsProtectionLedger).filter(
                RightsProtectionLedger.id == entry_id
            ).first()
            if not entry:
                return None

            for key, value in kwargs.items():
                if hasattr(entry, key) and value is not None:
                    setattr(entry, key, value)

            entry.total_cost = entry.attorney_fee + entry.court_fee + entry.evidence_fee + entry.other_cost
            entry.net_amount = entry.compensation_amount - entry.total_cost

            db.commit()
            db.refresh(entry)
            return entry


class OfflineClueManager:
    def __init__(self):
        self.op_logger = OperationLogger()

    def _generate_clue_number(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        uuid_part = uuid.uuid4().hex[:8].upper()
        return f"CLUE-{date_str}-{uuid_part}"

    def _calculate_duplicate_score(
        self,
        new_clue: Dict[str, Any],
        existing_clue: OfflineClue
    ) -> float:
        scores = []

        name_score = SequenceMatcher(
            None,
            new_clue.get("infringing_party_name", ""),
            existing_clue.infringing_party_name
        ).ratio()
        scores.append(name_score * 0.4)

        content_score = SequenceMatcher(
            None,
            new_clue.get("infringing_content", ""),
            existing_clue.infringing_content
        ).ratio()
        scores.append(content_score * 0.4)

        location_score = SequenceMatcher(
            None,
            new_clue.get("infringing_location", ""),
            existing_clue.infringing_location or ""
        ).ratio()
        scores.append(location_score * 0.2)

        return sum(scores)

    def check_duplicate(self, clue_data: Dict[str, Any]) -> Optional[OfflineClue]:
        with get_db() as db:
            existing_clues = db.query(OfflineClue).filter(
                OfflineClue.is_duplicate == False
            ).all()

            for clue in existing_clues:
                score = self._calculate_duplicate_score(clue_data, clue)
                if score >= 0.8:
                    logger.info(f"发现重复线索，相似度: {score:.2f}, 原线索编号: {clue.clue_number}")
                    return clue

            return None

    def add_offline_clue(
        self,
        infringing_party_name: str,
        infringing_content: str,
        infringing_location: Optional[str] = None,
        discovery_date: Optional[date] = None,
        reporter: Optional[str] = None,
        contact_info: Optional[str] = None,
        notes: Optional[str] = None
    ) -> OfflineClue:
        clue_data = {
            "infringing_party_name": infringing_party_name,
            "infringing_content": infringing_content,
            "infringing_location": infringing_location or ""
        }

        duplicate_clue = self.check_duplicate(clue_data)

        with get_db() as db:
            if duplicate_clue:
                clue = OfflineClue(
                    clue_number=self._generate_clue_number(),
                    infringing_party_name=infringing_party_name,
                    infringing_content=infringing_content,
                    infringing_location=infringing_location,
                    discovery_date=discovery_date or date.today(),
                    reporter=reporter,
                    contact_info=contact_info,
                    is_duplicate=True,
                    merged_to_clue_id=duplicate_clue.id,
                    status="merged",
                    notes=notes
                )
                db.add(clue)
                db.commit()
                db.refresh(clue)

                self.op_logger.log_operation(
                    operation_type=OperationTypeEnum.MERGE_CLUE,
                    target_id=clue.id,
                    target_type="offline_clue",
                    details={
                        "merged_to": duplicate_clue.clue_number,
                        "duplicate_score": self._calculate_duplicate_score(clue_data, duplicate_clue)
                    }
                )

                logger.info(f"线下线索已标记为重复，合并至: {duplicate_clue.clue_number}")
            else:
                clue = OfflineClue(
                    clue_number=self._generate_clue_number(),
                    infringing_party_name=infringing_party_name,
                    infringing_content=infringing_content,
                    infringing_location=infringing_location,
                    discovery_date=discovery_date or date.today(),
                    reporter=reporter,
                    contact_info=contact_info,
                    is_duplicate=False,
                    status="pending",
                    notes=notes
                )
                db.add(clue)
                db.commit()
                db.refresh(clue)

                self.op_logger.log_operation(
                    operation_type=OperationTypeEnum.MANUAL_ENTRY,
                    target_id=clue.id,
                    target_type="offline_clue",
                    details={"clue_number": clue.clue_number, "reporter": reporter}
                )

                logger.info(f"新增线下线索: {clue.clue_number}")

            return clue

    def link_clue_to_case(self, clue_id: int, case_id: int) -> bool:
        with get_db() as db:
            clue = db.query(OfflineClue).filter(OfflineClue.id == clue_id).first()
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()

            if not clue or not case:
                return False

            clue.case_id = case_id
            clue.status = "linked"
            db.commit()

            logger.info(f"线索 {clue.clue_number} 已关联至案件 {case.case_number}")
            return True

    def list_clues(
        self,
        status: Optional[str] = None,
        is_duplicate: Optional[bool] = None,
        reporter: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[OfflineClue]:
        with get_db() as db:
            query = db.query(OfflineClue)

            if status:
                query = query.filter(OfflineClue.status == status)
            if is_duplicate is not None:
                query = query.filter(OfflineClue.is_duplicate == is_duplicate)
            if reporter:
                query = query.filter(OfflineClue.reporter == reporter)
            if start_date:
                query = query.filter(OfflineClue.discovery_date >= start_date)
            if end_date:
                query = query.filter(OfflineClue.discovery_date <= end_date)

            return query.order_by(OfflineClue.created_at.desc()).offset(skip).limit(limit).all()

    def get_pending_clues(self) -> List[OfflineClue]:
        with get_db() as db:
            return db.query(OfflineClue).filter(
                OfflineClue.status == "pending",
                OfflineClue.is_duplicate == False
            ).all()
