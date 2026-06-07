import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import pandas as pd
from config.settings import settings
from database.models import (
    InfringementCase, WeeklyReport, InfringingParty,
    InfringementStatusEnum, RiskLevelEnum, Litigation,
    RightsProtectionLedger, OperationTypeEnum
)
from database.connection import get_db
from sqlalchemy.orm import joinedload
from utils.logger import logger
from modules.operation_logger import OperationLogger


sns.set_style("whitegrid")

def _setup_chinese_fonts():
    available_fonts = []
    try:
        import matplotlib.font_manager as fm
        system_fonts = [f.name for f in fm.fontManager.ttflist]

        preferred_fonts = [
            'Microsoft YaHei', 'SimHei', 'PingFang SC', 'Hiragino Sans GB',
            'WenQuanYi Micro Hei', 'Noto Sans CJK SC',
            'Source Han Sans CN', 'WenQuanYi Zen Hei',
            'Arial Unicode MS', 'STHeiti', 'STSong',
            'KaiTi', 'FangSong', 'DejaVu Sans'
        ]

        for font in preferred_fonts:
            if font in system_fonts:
                available_fonts.append(font)

        if not available_fonts:
            available_fonts = ['DejaVu Sans']

        plt.rcParams['font.sans-serif'] = available_fonts
        plt.rcParams['axes.unicode_minus'] = False
        logger.info(f"图表字体配置完成，使用字体: {available_fonts[:3]}")
    except Exception as e:
        logger.warning(f"字体检测失败，使用默认字体: {e}")
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

_setup_chinese_fonts()


class ReportGenerator:
    def __init__(self):
        self.op_logger = OperationLogger()
        self.report_path = Path(settings.EVIDENCE_STORAGE_PATH) / "reports"
        self.report_path.mkdir(parents=True, exist_ok=True)

    def _get_week_range(self, ref_date: Optional[date] = None) -> Tuple[date, date]:
        if ref_date is None:
            ref_date = date.today()

        start = ref_date - timedelta(days=ref_date.weekday())
        end = start + timedelta(days=6)
        return start, end

    def _generate_charts(self, data: Dict[str, Any], week_label: str) -> List[str]:
        chart_paths = []

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'知识产权维权周报 - {week_label}', fontsize=16, fontweight='bold')

        ax1 = axes[0, 0]
        risk_labels = ['低风险', '中风险', '高风险']
        risk_values = [
            data.get('low_risk_count', 0),
            data.get('medium_risk_count', 0),
            data.get('high_risk_count', 0)
        ]
        colors = ['#66BB6A', '#FFA726', '#EF5350']
        ax1.pie(risk_values, labels=risk_labels, autopct='%1.1f%%', colors=colors, startangle=90)
        ax1.set_title('案件风险等级分布')

        ax2 = axes[0, 1]
        status_counts = data.get('status_counts', {})
        if status_counts:
            statuses = list(status_counts.keys())
            counts = list(status_counts.values())
            bars = ax2.bar(statuses, counts, color='#42A5F5')
            ax2.set_title('案件处理状态分布')
            ax2.set_ylabel('案件数量')
            plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
            for bar in bars:
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(height)}', ha='center', va='bottom')

        ax3 = axes[1, 0]
        if 'trend_data' in data and data['trend_data']:
            trend_df = pd.DataFrame(data['trend_data'])
            if not trend_df.empty:
                ax3.plot(trend_df['date'], trend_df['new_cases'], marker='o', label='新增案件', color='#42A5F5')
                ax3.plot(trend_df['date'], trend_df['closed_cases'], marker='s', label='结案数量', color='#66BB6A')
                ax3.set_title('近8周案件趋势')
                ax3.set_ylabel('案件数量')
                ax3.legend()
                ax3.grid(True, alpha=0.3)
                plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')

        ax4 = axes[1, 1]
        platform_data = data.get('platform_counts', {})
        if platform_data:
            platforms = list(platform_data.keys())
            plat_counts = list(platform_data.values())
            bars = ax4.barh(platforms, plat_counts, color='#AB47BC')
            ax4.set_title('侵权平台分布')
            ax4.set_xlabel('案件数量')
            for bar in bars:
                width = bar.get_width()
                ax4.text(width, bar.get_y() + bar.get_height()/2.,
                        f'{int(width)}', ha='left', va='center')

        plt.tight_layout()
        chart_path = self.report_path / f"week_report_charts_{week_label}.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close()
        chart_paths.append(str(chart_path))

        return chart_paths

    def _generate_pdf_report(
        self,
        data: Dict[str, Any],
        week_label: str,
        chart_paths: List[str],
        start_date: date,
        end_date: date
    ) -> str:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
        from reportlab.lib import colors

        pdf_path = self.report_path / f"week_report_{week_label}.pdf"
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, alignment=1, spaceAfter=20)
        section_style = ParagraphStyle('CustomSection', parent=styles['Heading2'], fontSize=14, spaceBefore=15, spaceAfter=10)
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=10, leading=14)

        story = []

        story.append(Paragraph(f"知识产权维权周报", title_style))
        story.append(Paragraph(f"统计周期：{start_date.strftime('%Y年%m月%d日')} - {end_date.strftime('%Y年%m月%d日')}", ParagraphStyle('Center', parent=normal_style, alignment=1)))
        story.append(Spacer(1, 0.5*cm))

        story.append(Paragraph("一、核心指标概览", section_style))
        summary_data = [
            ['指标', '数值'],
            ['新增案件数', str(data.get('new_cases', 0))],
            ['结案数', str(data.get('closed_cases', 0))],
            ['在办案件总数', str(data.get('total_cases', 0))],
            ['维权成功率', f"{data.get('success_rate', 0):.1f}%"],
            ['平均响应时长', f"{data.get('avg_response_time_hours', 0):.1f} 小时"],
            ['累计赔偿金额', f"¥ {data.get('total_compensation', 0):,.2f}"],
            ['累计维权成本', f"¥ {data.get('total_cost', 0):,.2f}"],
        ]
        summary_table = Table(summary_data, colWidths=[8*cm, 6*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#42A5F5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 1, colors.gray),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.5*cm))

        if chart_paths:
            story.append(Paragraph("二、图表分析", section_style))
            for chart_path in chart_paths:
                img = Image(chart_path, width=16*cm, height=11*cm)
                story.append(img)
                story.append(Spacer(1, 0.3*cm))

        story.append(Paragraph("三、重点关注事项", section_style))
        high_risk = data.get('high_risk_count', 0)
        repeat_offenders = data.get('repeat_offenders', 0)
        overdue = data.get('overdue_cases', 0)

        issues = []
        if high_risk > 0:
            issues.append(f"• 本周新增高风险案件 {high_risk} 件，建议优先处理")
        if repeat_offenders > 0:
            issues.append(f"• 发现重复侵权方 {repeat_offenders} 个，累计投诉3次以上，建议发起批量诉讼")
        if overdue > 0:
            issues.append(f"• 有 {overdue} 件案件超期未处理，已升级至法务总监")
        if not issues:
            issues.append("• 本周无特别关注事项")

        for issue in issues:
            story.append(Paragraph(issue, normal_style))

        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))

        doc.build(story)
        return str(pdf_path)

    def _generate_excel_report(
        self,
        data: Dict[str, Any],
        week_label: str
    ) -> str:
        excel_path = self.report_path / f"week_report_{week_label}.xlsx"

        with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
            summary_df = pd.DataFrame([{
                '统计周期': f"{data.get('start_date', '')} - {data.get('end_date', '')}",
                '新增案件数': data.get('new_cases', 0),
                '结案数': data.get('closed_cases', 0),
                '在办案件总数': data.get('total_cases', 0),
                '维权成功率(%)': round(data.get('success_rate', 0), 1),
                '平均响应时长(小时)': round(data.get('avg_response_time_hours', 0), 1),
                '累计赔偿金额(元)': round(data.get('total_compensation', 0), 2),
                '累计维权成本(元)': round(data.get('total_cost', 0), 2),
                '低风险案件数': data.get('low_risk_count', 0),
                '中风险案件数': data.get('medium_risk_count', 0),
                '高风险案件数': data.get('high_risk_count', 0),
            }])
            summary_df.to_excel(writer, sheet_name='统计概览', index=False)

            case_data_list = data.get('case_data_list', [])
            if case_data_list:
                cases_df = pd.DataFrame(case_data_list)
                cases_df.to_excel(writer, sheet_name='案件明细', index=False)

            ledger_entries = data.get('ledger_entries', [])
            if ledger_entries:
                ledger_df = pd.DataFrame(ledger_entries)
                ledger_df.to_excel(writer, sheet_name='台账明细', index=False)

            workbook = writer.book
            worksheet = writer.sheets['统计概览']
            header_format = workbook.add_format({'bold': True, 'bg_color': '#42A5F5', 'font_color': 'white', 'align': 'center'})
            for col_num, value in enumerate(summary_df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            worksheet.set_column('A:A', 30)
            worksheet.set_column('B:L', 15)

        return str(excel_path)

    def generate_weekly_report(self, ref_date: Optional[date] = None) -> WeeklyReport:
        start_date, end_date = self._get_week_range(ref_date)
        week_label = start_date.strftime('%Y%m%d')

        with get_db() as db:
            existing = db.query(WeeklyReport).filter(WeeklyReport.report_week == week_label).first()
            if existing:
                logger.info(f"周报 {week_label} 已存在，跳过生成")
                return existing

            week_cases = db.query(InfringementCase).options(
                joinedload(InfringementCase.ip),
                joinedload(InfringementCase.product),
                joinedload(InfringementCase.infringing_party)
            ).filter(
                InfringementCase.created_at >= datetime.combine(start_date, datetime.min.time()),
                InfringementCase.created_at <= datetime.combine(end_date, datetime.max.time())
            ).all()

            new_cases = len(week_cases)
            closed_cases = sum(1 for c in week_cases if c.status in [
                InfringementStatusEnum.SETTLED,
                InfringementStatusEnum.WON,
                InfringementStatusEnum.CLOSED
            ])

            total_cases = db.query(InfringementCase).count()

            success_cases = sum(1 for c in week_cases if c.status in [
                InfringementStatusEnum.SETTLED,
                InfringementStatusEnum.WON,
                InfringementStatusEnum.WARNING_ACKNOWLEDGED
            ])
            success_rate = (success_cases / new_cases * 100) if new_cases > 0 else 0

            response_times = []
            for c in week_cases:
                if c.first_response_due and c.created_at:
                    time_diff = c.first_response_due - c.created_at
                    response_times.append(time_diff.total_seconds() / 3600)
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0

            low_risk = sum(1 for c in week_cases if c.risk_level == RiskLevelEnum.LOW)
            medium_risk = sum(1 for c in week_cases if c.risk_level == RiskLevelEnum.MEDIUM)
            high_risk = sum(1 for c in week_cases if c.risk_level == RiskLevelEnum.HIGH)

            total_compensation = sum(c.compensation_amount or 0 for c in week_cases)
            total_cost = sum(c.cost_amount or 0 for c in week_cases)

            status_counts = {}
            for c in week_cases:
                status = c.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            platform_counts = {}
            for c in week_cases:
                if c.product:
                    plat = c.product.platform.value
                    platform_counts[plat] = platform_counts.get(plat, 0) + 1

            repeat_offenders = db.query(InfringingParty).filter(
                InfringingParty.complaint_count >= 3
            ).count()

            overdue_cases = db.query(InfringementCase).filter(
                InfringementCase.first_response_due < datetime.now(),
                InfringementCase.status.in_([
                    InfringementStatusEnum.LITIGATION_PREPARED,
                    InfringementStatusEnum.LITIGATION_IN_PROGRESS
                ])
            ).count()

            trend_data = []
            for i in range(7, -1, -1):
                week_start = start_date - timedelta(weeks=i)
                week_end = week_start + timedelta(days=6)
                week_new = db.query(InfringementCase).filter(
                    InfringementCase.created_at >= datetime.combine(week_start, datetime.min.time()),
                    InfringementCase.created_at <= datetime.combine(week_end, datetime.max.time())
                ).count()
                week_closed = db.query(InfringementCase).filter(
                    InfringementCase.settlement_date >= week_start,
                    InfringementCase.settlement_date <= week_end
                ).count()
                trend_data.append({
                    'date': week_start,
                    'new_cases': week_new,
                    'closed_cases': week_closed
                })

            ledger_entries = []
            ledgers = db.query(RightsProtectionLedger).options(
                joinedload(RightsProtectionLedger.case)
            ).filter(
                RightsProtectionLedger.record_date >= start_date,
                RightsProtectionLedger.record_date <= end_date
            ).all()
            for entry in ledgers:
                ledger_entries.append({
                    '案件编号': entry.case.case_number if entry.case else '',
                    '记录日期': entry.record_date.strftime('%Y-%m-%d'),
                    '赔偿金额': entry.compensation_amount,
                    '律师费': entry.attorney_fee,
                    '诉讼费': entry.court_fee,
                    '取证费': entry.evidence_fee,
                    '其他费用': entry.other_cost,
                    '总成本': entry.total_cost,
                    '净收益': entry.net_amount,
                    '支付状态': entry.payment_status,
                })

            case_data_list = []
            for case in week_cases:
                case_data_list.append({
                    '案件编号': case.case_number,
                    '知识产权类型': case.ip.ip_type.value if case.ip else '',
                    '知识产权编号': case.ip.ip_number if case.ip else '',
                    '知识产权名称': case.ip.name if case.ip else '',
                    '侵权商品': case.product.title if case.product else '',
                    '侵权平台': case.product.platform.value if case.product else '',
                    '侵权方': case.infringing_party.name if case.infringing_party else '',
                    '相似度(%)': round(case.similarity_score * 100, 1),
                    '风险等级': case.risk_level.value,
                    '案件状态': case.status.value,
                    '创建时间': case.created_at.strftime('%Y-%m-%d %H:%M') if case.created_at else '',
                    '赔偿金额(元)': case.compensation_amount or 0,
                    '维权成本(元)': case.cost_amount or 0,
                })

        data = {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'new_cases': new_cases,
            'closed_cases': closed_cases,
            'total_cases': total_cases,
            'success_rate': success_rate,
            'avg_response_time_hours': avg_response_time,
            'low_risk_count': low_risk,
            'medium_risk_count': medium_risk,
            'high_risk_count': high_risk,
            'total_compensation': total_compensation,
            'total_cost': total_cost,
            'status_counts': status_counts,
            'platform_counts': platform_counts,
            'repeat_offenders': repeat_offenders,
            'overdue_cases': overdue_cases,
            'trend_data': trend_data,
            'ledger_entries': ledger_entries,
            'case_data_list': case_data_list
        }

        chart_paths = self._generate_charts(data, week_label)
        pdf_path = self._generate_pdf_report(data, week_label, chart_paths, start_date, end_date)
        excel_path = self._generate_excel_report(data, week_label)

        with get_db() as db:
            report = WeeklyReport(
                report_week=week_label,
                start_date=start_date,
                end_date=end_date,
                total_cases=total_cases,
                new_cases=new_cases,
                closed_cases=closed_cases,
                success_rate=success_rate,
                avg_response_time_hours=avg_response_time,
                low_risk_count=low_risk,
                medium_risk_count=medium_risk,
                high_risk_count=high_risk,
                total_compensation=total_compensation,
                total_cost=total_cost,
                pdf_path=pdf_path,
                excel_path=excel_path
            )
            db.add(report)
            db.commit()
            db.refresh(report)

        self.op_logger.log_operation(
            operation_type=OperationTypeEnum.GENERATE_REPORT,
            target_id=report.id,
            target_type="weekly_report",
            details={"report_week": week_label, "new_cases": new_cases}
        )

        logger.info(f"周报生成完成: {week_label}, PDF: {pdf_path}, Excel: {excel_path}")
        return report


class BatchLitigationManager:
    def __init__(self):
        self.op_logger = OperationLogger()

    def _generate_batch_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        uuid_part = uuid.uuid4().hex[:6].upper()
        return f"BATCH-{date_str}-{uuid_part}"

    def detect_repeat_offenders(self, min_complaints: int = 3) -> List[InfringingParty]:
        with get_db() as db:
            repeat_parties = db.query(InfringingParty).filter(
                InfringingParty.complaint_count >= min_complaints
            ).all()

            logger.info(f"发现 {len(repeat_parties)} 个累计被投诉 {min_complaints} 次以上的侵权方")
            return repeat_parties

    def generate_batch_litigation_suggestion(self, party_id: int) -> Dict[str, Any]:
        with get_db() as db:
            party = db.query(InfringingParty).filter(InfringingParty.id == party_id).first()
            if not party:
                raise ValueError(f"侵权方 {party_id} 不存在")

            cases = db.query(InfringementCase).filter(
                InfringementCase.infringing_party_id == party_id
            ).order_by(InfringementCase.created_at.desc()).all()

            batch_id = self._generate_batch_id()

            total_sales = sum(c.product.sales_volume or 0 for c in cases if c.product)
            estimated_loss = total_sales * (cases[0].product.price or 100) * 0.1 if cases and cases[0].product else 0

            suggestion = {
                "batch_id": batch_id,
                "infringing_party": {
                    "id": party.id,
                    "name": party.name,
                    "platform": party.platform.value if party.platform else "",
                    "complaint_count": party.complaint_count,
                    "shop_url": party.shop_url
                },
                "related_cases": [
                    {
                        "case_number": c.case_number,
                        "ip_number": c.ip.ip_number if c.ip else "",
                        "ip_name": c.ip.name if c.ip else "",
                        "similarity": c.similarity_score,
                        "status": c.status.value,
                        "created_at": c.created_at.isoformat() if c.created_at else ""
                    }
                    for c in cases
                ],
                "analysis": {
                    "total_cases": len(cases),
                    "total_sales_estimate": total_sales,
                    "estimated_loss": estimated_loss,
                    "recommended_action": "发起批量诉讼",
                    "win_probability": "高" if party.complaint_count >= 5 else "较高",
                    "estimated_compensation": f"{estimated_loss * 2:,.2f} - {estimated_loss * 5:,.2f} 元"
                }
            }

            for case in cases:
                litigations = db.query(Litigation).filter(Litigation.case_id == case.id).all()
                for lit in litigations:
                    lit.is_batch = True
                    lit.batch_id = batch_id

            db.commit()

            suggestion_path = Path(settings.EVIDENCE_STORAGE_PATH) / "batch_suggestions"
            suggestion_path.mkdir(parents=True, exist_ok=True)
            import json
            with open(suggestion_path / f"{batch_id}.json", "w", encoding="utf-8") as f:
                json.dump(suggestion, f, ensure_ascii=False, indent=2)

            logger.info(f"生成批量诉讼建议: {batch_id}, 侵权方: {party.name}, 关联案件: {len(cases)}件")
            return suggestion

    def check_and_generate_batch_suggestions(self) -> List[Dict[str, Any]]:
        repeat_offenders = self.detect_repeat_offenders(min_complaints=3)
        suggestions = []

        for party in repeat_offenders:
            with get_db() as db:
                has_batch = db.query(Litigation).filter(
                    Litigation.case.has(infringing_party_id=party.id),
                    Litigation.is_batch == True
                ).first()

                if not has_batch:
                    try:
                        suggestion = self.generate_batch_litigation_suggestion(party.id)
                        suggestions.append(suggestion)
                    except Exception as e:
                        logger.error(f"生成批量诉讼建议失败 {party.name}: {e}")

        logger.info(f"批量诉讼建议检查完成，新生成 {len(suggestions)} 份建议")
        return suggestions
