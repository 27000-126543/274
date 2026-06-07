from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd
from config.settings import settings
from database.models import (
    InfringementCase, InfringingParty, IntellectualProperty,
    CrawledProduct, OfflineClue, RightsProtectionLedger,
    OperationLog, InfringementStatusEnum, RiskLevelEnum, OperationTypeEnum
)
from database.connection import get_db
from utils.logger import logger
from modules.operation_logger import OperationLogger


class QueryManager:
    def __init__(self):
        self.op_logger = OperationLogger()

    def query_cases(
        self,
        infringing_party_name: Optional[str] = None,
        ip_number: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[InfringementStatusEnum] = None,
        risk_level: Optional[RiskLevelEnum] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[InfringementCase]:
        with get_db() as db:
            query = db.query(InfringementCase)

            if infringing_party_name:
                query = query.join(InfringingParty).filter(
                    InfringingParty.name.like(f"%{infringing_party_name}%")
                )

            if ip_number:
                query = query.join(IntellectualProperty).filter(
                    IntellectualProperty.ip_number.like(f"%{ip_number}%")
                )

            if start_date:
                query = query.filter(InfringementCase.created_at >= datetime.combine(start_date, datetime.min.time()))
            if end_date:
                query = query.filter(InfringementCase.created_at <= datetime.combine(end_date, datetime.max.time()))

            if status:
                query = query.filter(InfringementCase.status == status)
            if risk_level:
                query = query.filter(InfringementCase.risk_level == risk_level)

            results = query.order_by(InfringementCase.created_at.desc()).offset(skip).limit(limit).all()
            logger.info(f"案件查询完成，返回 {len(results)} 条结果")
            return results

    def query_case_full_lifecycle(self, case_id: int) -> Dict[str, Any]:
        with get_db() as db:
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
            if not case:
                return {}

            lifecycle = {
                "case_info": {
                    "case_number": case.case_number,
                    "status": case.status.value,
                    "risk_level": case.risk_level.value,
                    "similarity_score": case.similarity_score,
                    "created_at": case.created_at.isoformat() if case.created_at else None,
                    "first_response_due": case.first_response_due.isoformat() if case.first_response_due else None,
                    "compensation_amount": case.compensation_amount,
                    "cost_amount": case.cost_amount,
                    "notes": case.notes
                },
                "ip_info": None,
                "product_info": None,
                "infringing_party": None,
                "warning_letters": [],
                "litigations": [],
                "evidences": [],
                "ledger_entries": [],
                "operation_logs": []
            }

            if case.ip:
                lifecycle["ip_info"] = {
                    "ip_type": case.ip.ip_type.value,
                    "ip_number": case.ip.ip_number,
                    "name": case.ip.name,
                    "owner": case.ip.owner,
                    "application_date": case.ip.application_date.isoformat() if case.ip.application_date else None
                }

            if case.product:
                lifecycle["product_info"] = {
                    "platform": case.product.platform.value,
                    "product_id": case.product.product_id,
                    "title": case.product.title,
                    "price": case.product.price,
                    "seller_name": case.product.seller_name,
                    "product_url": case.product.product_url,
                    "crawl_time": case.product.crawl_time.isoformat() if case.product.crawl_time else None
                }

            if case.infringing_party:
                lifecycle["infringing_party"] = {
                    "name": case.infringing_party.name,
                    "complaint_count": case.infringing_party.complaint_count,
                    "contact_email": case.infringing_party.contact_email,
                    "platform": case.infringing_party.platform.value if case.infringing_party.platform else None
                }

            for letter in case.warning_letters:
                lifecycle["warning_letters"].append({
                    "letter_number": letter.letter_number,
                    "send_to": letter.send_to,
                    "send_email": letter.send_email,
                    "send_time": letter.send_time.isoformat() if letter.send_time else None,
                    "receipt_received": letter.receipt_received,
                    "receipt_time": letter.receipt_time.isoformat() if letter.receipt_time else None
                })

            for lit in case.litigations:
                lifecycle["litigations"].append({
                    "litigation_number": lit.litigation_number,
                    "court": lit.court,
                    "filing_date": lit.filing_date.isoformat() if lit.filing_date else None,
                    "judgment_result": lit.judgment_result,
                    "is_batch": lit.is_batch,
                    "batch_id": lit.batch_id
                })

            for ev in case.evidences:
                lifecycle["evidences"].append({
                    "evidence_type": ev.evidence_type,
                    "file_name": ev.file_name,
                    "file_size": ev.file_size,
                    "md5_hash": ev.md5_hash,
                    "timestamp": ev.timestamp.isoformat() if ev.timestamp else None
                })

            for entry in case.ledger_entries:
                lifecycle["ledger_entries"].append({
                    "record_date": entry.record_date.isoformat() if entry.record_date else None,
                    "compensation_amount": entry.compensation_amount,
                    "total_cost": entry.total_cost,
                    "net_amount": entry.net_amount,
                    "payment_status": entry.payment_status
                })

            logs = db.query(OperationLog).filter(
                OperationLog.target_id == case.id,
                OperationLog.target_type == "infringement_case"
            ).order_by(OperationLog.created_at.asc()).all()

            for log in logs:
                lifecycle["operation_logs"].append({
                    "operation_type": log.operation_type.value,
                    "operator": log.operator,
                    "details": log.details,
                    "created_at": log.created_at.isoformat() if log.created_at else None
                })

            return lifecycle

    def query_offline_clues(
        self,
        infringing_party_name: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[OfflineClue]:
        with get_db() as db:
            query = db.query(OfflineClue)

            if infringing_party_name:
                query = query.filter(OfflineClue.infringing_party_name.like(f"%{infringing_party_name}%"))
            if status:
                query = query.filter(OfflineClue.status == status)
            if start_date:
                query = query.filter(OfflineClue.discovery_date >= start_date)
            if end_date:
                query = query.filter(OfflineClue.discovery_date <= end_date)

            return query.order_by(OfflineClue.created_at.desc()).offset(skip).limit(limit).all()


class ExportManager:
    def __init__(self):
        self.op_logger = OperationLogger()
        self.export_path = Path(settings.EVIDENCE_STORAGE_PATH) / "exports"
        self.export_path.mkdir(parents=True, exist_ok=True)

    def export_cases_to_excel(
        self,
        cases: List[InfringementCase],
        filename: Optional[str] = None
    ) -> str:
        if not filename:
            filename = f"cases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        export_file = self.export_path / filename

        case_data = []
        for case in cases:
            case_data.append({
                '案件编号': case.case_number,
                '知识产权类型': case.ip.ip_type.value if case.ip else '',
                '知识产权编号': case.ip.ip_number if case.ip else '',
                '知识产权名称': case.ip.name if case.ip else '',
                '侵权商品': case.product.title if case.product else '',
                '侵权平台': case.product.platform.value if case.product else '',
                '侵权方': case.infringing_party.name if case.infringing_party else '',
                '相似度(%)': round(case.similarity_score * 100, 1) if case.similarity_score else 0,
                '风险等级': case.risk_level.value,
                '案件状态': case.status.value,
                '创建时间': case.created_at.strftime('%Y-%m-%d %H:%M') if case.created_at else '',
                '首次响应期限': case.first_response_due.strftime('%Y-%m-%d %H:%M') if case.first_response_due else '',
                '赔偿金额(元)': case.compensation_amount or 0,
                '维权成本(元)': case.cost_amount or 0,
                '指派律师': case.assigned_lawyer or '',
                '案件来源': case.source_type or '',
                '备注': case.notes or ''
            })

        df = pd.DataFrame(case_data)

        with pd.ExcelWriter(export_file, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='案件列表', index=False)

            workbook = writer.book
            worksheet = writer.sheets['案件列表']
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#42A5F5',
                'font_color': 'white',
                'align': 'center',
                'valign': 'vcenter'
            })

            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                column_width = max(len(str(value)), df[value].astype(str).map(len).max()) + 2
                worksheet.set_column(col_num, col_num, min(column_width, 40))

            worksheet.freeze_panes(1, 0)

        self.op_logger.log_operation(
            operation_type=OperationTypeEnum.EXPORT_DATA,
            target_type="cases",
            details={"filename": filename, "count": len(cases)}
        )

        logger.info(f"案件数据导出完成: {export_file}, 共 {len(cases)} 条")
        return str(export_file)

    def export_ledger_to_excel(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        filename: Optional[str] = None
    ) -> str:
        if not filename:
            filename = f"ledger_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        export_file = self.export_path / filename

        with get_db() as db:
            query = db.query(RightsProtectionLedger)
            if start_date:
                query = query.filter(RightsProtectionLedger.record_date >= start_date)
            if end_date:
                query = query.filter(RightsProtectionLedger.record_date <= end_date)

            entries = query.order_by(RightsProtectionLedger.record_date.desc()).all()

        ledger_data = []
        for entry in entries:
            ledger_data.append({
                '案件编号': entry.case.case_number if entry.case else '',
                '记录日期': entry.record_date.strftime('%Y-%m-%d') if entry.record_date else '',
                '赔偿金额(元)': entry.compensation_amount,
                '律师费(元)': entry.attorney_fee,
                '诉讼费(元)': entry.court_fee,
                '取证费(元)': entry.evidence_fee,
                '其他费用(元)': entry.other_cost,
                '总成本(元)': entry.total_cost,
                '净收益(元)': entry.net_amount,
                '支付状态': entry.payment_status,
                '备注': entry.notes or ''
            })

        df = pd.DataFrame(ledger_data)

        with pd.ExcelWriter(export_file, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='台账明细', index=False)

            summary_row = pd.DataFrame([{
                '案件编号': '合计',
                '记录日期': '',
                '赔偿金额(元)': df['赔偿金额(元)'].sum(),
                '律师费(元)': df['律师费(元)'].sum(),
                '诉讼费(元)': df['诉讼费(元)'].sum(),
                '取证费(元)': df['取证费(元)'].sum(),
                '其他费用(元)': df['其他费用(元)'].sum(),
                '总成本(元)': df['总成本(元)'].sum(),
                '净收益(元)': df['净收益(元)'].sum(),
                '支付状态': '',
                '备注': ''
            }])

            summary_row.to_excel(writer, sheet_name='台账明细', startrow=len(df) + 2, index=False)

            workbook = writer.book
            worksheet = writer.sheets['台账明细']
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#66BB6A',
                'font_color': 'white',
                'align': 'center'
            })

            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)

        self.op_logger.log_operation(
            operation_type=OperationTypeEnum.EXPORT_DATA,
            target_type="ledger",
            details={"filename": filename, "count": len(entries)}
        )

        logger.info(f"台账数据导出完成: {export_file}, 共 {len(entries)} 条")
        return str(export_file)

    def batch_export_full_cases(
        self,
        case_ids: List[int],
        filename: Optional[str] = None
    ) -> str:
        if not filename:
            filename = f"full_cases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        export_file = self.export_path / filename

        query_mgr = QueryManager()
        cases_data = []

        with get_db() as db:
            for case_id in case_ids:
                case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
                if case:
                    cases_data.append(query_mgr.query_case_full_lifecycle(case_id))

        basic_data = []
        for data in cases_data:
            ci = data.get("case_info", {})
            ip = data.get("ip_info", {}) or {}
            prod = data.get("product_info", {}) or {}
            party = data.get("infringing_party", {}) or {}

            basic_data.append({
                '案件编号': ci.get('case_number', ''),
                '案件状态': ci.get('status', ''),
                '风险等级': ci.get('risk_level', ''),
                '相似度(%)': round(ci.get('similarity_score', 0) * 100, 1),
                '创建时间': ci.get('created_at', ''),
                '知识产权类型': ip.get('ip_type', ''),
                '知识产权编号': ip.get('ip_number', ''),
                '知识产权名称': ip.get('name', ''),
                '侵权商品': prod.get('title', ''),
                '侵权平台': prod.get('platform', ''),
                '侵权方': party.get('name', ''),
                '投诉次数': party.get('complaint_count', 0),
                '赔偿金额': ci.get('compensation_amount', 0),
                '维权成本': ci.get('cost_amount', 0)
            })

        warning_data = []
        for data in cases_data:
            ci = data.get("case_info", {})
            for letter in data.get("warning_letters", []):
                warning_data.append({
                    '案件编号': ci.get('case_number', ''),
                    '警告函编号': letter.get('letter_number', ''),
                    '收件人': letter.get('send_to', ''),
                    '收件邮箱': letter.get('send_email', ''),
                    '发送时间': letter.get('send_time', ''),
                    '是否已回执': '是' if letter.get('receipt_received') else '否',
                    '回执时间': letter.get('receipt_time', '')
                })

        with pd.ExcelWriter(export_file, engine='xlsxwriter') as writer:
            pd.DataFrame(basic_data).to_excel(writer, sheet_name='案件基本信息', index=False)
            if warning_data:
                pd.DataFrame(warning_data).to_excel(writer, sheet_name='警告函记录', index=False)

        self.op_logger.log_operation(
            operation_type=OperationTypeEnum.EXPORT_DATA,
            target_type="full_cases",
            details={"filename": filename, "case_count": len(case_ids)}
        )

        logger.info(f"全生命周期案件批量导出完成: {export_file}, 共 {len(cases_data)} 个案件")
        return str(export_file)
