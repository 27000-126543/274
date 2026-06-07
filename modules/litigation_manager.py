import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from config.settings import settings
from database.models import (
    InfringementCase, WarningLetter, Litigation,
    InfringementStatusEnum, OperationTypeEnum, RiskLevelEnum
)
from database.connection import get_db
from utils.logger import logger
from modules.operation_logger import OperationLogger


class WarningLetterManager:
    def __init__(self):
        self.op_logger = OperationLogger()

    def _generate_letter_number(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        uuid_part = uuid.uuid4().hex[:6].upper()
        return f"WARN-{date_str}-{uuid_part}"

    def _generate_letter_content(self, case: InfringementCase) -> str:
        ip = case.ip
        product = case.product
        party = case.infringing_party

        content = f"""
知识产权侵权警告函

致：{party.name if party else '相关方'}

本函为 {settings.COMPANY_NAME} （以下简称"我方"）正式发出的知识产权侵权警告函。

经查，贵方在{product.platform.value if product else ''}平台上销售的商品：
- 商品名称：{product.title if product else ''}
- 商品链接：{product.product_url if product else ''}

经我方核实，该商品涉嫌侵犯我方以下知识产权：
- 知识产权类型：{ip.ip_type.value if ip else ''}
- 知识产权编号：{ip.ip_number if ip else ''}
- 知识产权名称：{ip.name if ip else ''}

经专业比对，该商品与我方知识产权的相似度达到 {case.similarity_score * 100:.1f}%，
已构成实质性相似，涉嫌侵犯我方合法权益。

我方在此郑重要求贵方：
1. 立即停止销售、宣传上述侵权商品；
2. 立即删除所有相关的商品链接、图片及宣传资料；
3. 在收到本函后3个工作日内以书面形式回复我方，说明侵权情况并承诺不再发生类似行为；
4. 向我方提供上述侵权商品的销售数据及获利情况。

如贵方未在上述期限内采取有效措施，我方将依法采取包括但不限于向平台投诉、
向市场监管部门举报、提起诉讼等一切必要的法律手段，追究贵方的法律责任。

特此函告。

{settings.COMPANY_NAME}
法务部
{datetime.now().strftime('%Y年%m月%d日')}

联系邮箱：{settings.LEGAL_DEPARTMENT_EMAIL}
        """
        return content.strip()

    def _send_email(
        self,
        to_email: str,
        subject: str,
        content: str,
        attachments: Optional[List[str]] = None
    ) -> bool:
        if not settings.SMTP_PASSWORD:
            logger.warning("SMTP密码未配置，使用模拟发送模式")
            logger.info(f"[模拟发送邮件] 至: {to_email}, 主题: {subject}")
            return True

        try:
            msg = MIMEMultipart()
            msg["From"] = settings.SMTP_USER
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(content, "plain", "utf-8"))

            if attachments:
                for att_path in attachments:
                    if Path(att_path).exists():
                        with open(att_path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=Path(att_path).name)
                        part["Content-Disposition"] = f'attachment; filename="{Path(att_path).name}"'
                        msg.attach(part)

            if settings.SMTP_USE_SSL:
                server = smtplib.SMTP_SSL(settings.SMTP_SERVER, settings.SMTP_PORT)
            else:
                server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
                server.starttls()

            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()

            logger.info(f"警告函邮件已发送至: {to_email}")
            return True

        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False

    def send_warning_letter(self, case_id: int) -> Optional[WarningLetter]:
        with get_db() as db:
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
            if not case:
                logger.error(f"案件 {case_id} 不存在")
                return None

            if case.risk_level != RiskLevelEnum.LOW:
                logger.warning(f"案件 {case.case_number} 风险等级不是低风险，不发送警告函")
                return None

            party = case.infringing_party
            if not party or not party.contact_email:
                contact_email = settings.LEGAL_DEPARTMENT_EMAIL
                logger.warning(f"侵权方联系邮箱不存在，使用默认邮箱")
            else:
                contact_email = party.contact_email

            content = self._generate_letter_content(case)
            letter_number = self._generate_letter_number()

            attachments = []
            if case.evidence_pack_path and Path(case.evidence_pack_path).exists():
                attachments.append(case.evidence_pack_path)

            subject = f"【知识产权侵权警告】{letter_number} - {settings.COMPANY_NAME}"
            send_success = self._send_email(contact_email, subject, content, attachments)

            letter = WarningLetter(
                case_id=case.id,
                letter_number=letter_number,
                send_to=party.name if party else "",
                send_email=contact_email,
                content=content,
                receipt_received=False
            )
            db.add(letter)

            if send_success:
                case.status = InfringementStatusEnum.WARNING_SENT

            db.commit()
            db.refresh(letter)

            self.op_logger.log_operation(
                operation_type=OperationTypeEnum.SEND_WARNING,
                target_id=case.id,
                target_type="infringement_case",
                details={
                    "letter_number": letter_number,
                    "send_to": contact_email,
                    "success": send_success
                }
            )

            logger.info(f"警告函已发送: {letter_number}, 案件: {case.case_number}")
            return letter

    def process_low_risk_cases(self) -> List[WarningLetter]:
        with get_db() as db:
            low_risk_cases = db.query(InfringementCase).filter(
                InfringementCase.risk_level == RiskLevelEnum.LOW,
                InfringementCase.status == InfringementStatusEnum.CONFIRMED
            ).all()

            letters = []
            for case in low_risk_cases:
                try:
                    letter = self.send_warning_letter(case.id)
                    if letter:
                        letters.append(letter)
                except Exception as e:
                    logger.error(f"发送警告函失败 {case.case_number}: {e}")

            logger.info(f"批量处理低风险案件，发送 {len(letters)} 封警告函")
            return letters

    def acknowledge_receipt(self, letter_id: int, response_content: Optional[str] = None) -> bool:
        with get_db() as db:
            letter = db.query(WarningLetter).filter(WarningLetter.id == letter_id).first()
            if not letter:
                return False

            letter.receipt_received = True
            letter.receipt_time = datetime.now()
            letter.response_content = response_content

            case = letter.case
            if case:
                case.status = InfringementStatusEnum.WARNING_ACKNOWLEDGED

            db.commit()

            logger.info(f"警告函 {letter.letter_number} 已确认收到回执")
            return True


class LitigationManager:
    def __init__(self):
        self.op_logger = OperationLogger()

    def _generate_litigation_number(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        uuid_part = uuid.uuid4().hex[:8].upper()
        return f"LIT-{date_str}-{uuid_part}"

    def _generate_litigation_document(self, case: InfringementCase) -> str:
        ip = case.ip
        product = case.product
        party = case.infringing_party

        doc = f"""
民事诉讼起诉状（模板）

原告：{settings.COMPANY_NAME}
住所地：__________________________
法定代表人：______________________
联系电话：________________________
委托代理人：______________________

被告：{party.name if party else '未知'}
住所地：__________________________
法定代表人/经营者：_______________
联系电话：________________________

诉讼请求：
1. 判令被告立即停止侵犯原告 {ip.ip_type.value}（专利号/商标注册号/著作权登记号：{ip.ip_number}）的行为；
2. 判令被告赔偿原告经济损失及合理维权开支共计人民币______万元；
3. 判令被告在其官方网站及相关媒体上公开赔礼道歉、消除影响；
4. 判令被告承担本案全部诉讼费用。

事实与理由：
原告系 {ip.name}（知识产权编号：{ip.ip_number}）的合法权利人。
经原告调查发现，被告在 {product.platform.value if product else ''} 平台上经营的店铺
（店铺名称：{party.name if party else ''}）销售的商品（商品名称：{product.title if product else ''}）
与原告上述知识产权构成实质性相似，相似度达 {case.similarity_score * 100:.1f}%。

被告未经原告许可，擅自生产、销售上述侵权商品的行为，已严重侵犯原告的合法权益，
给原告造成了巨大的经济损失。为维护自身合法权益，原告特向贵院提起诉讼，
请求依法支持原告的全部诉讼请求。

证据清单：
1. 知识产权权利证书
2. 侵权商品网页截图及时间戳
3. 侵权商品购买公证书
4. 相似度比对报告
5. 原告损失及被告获利相关证据
6. 其他相关证据

此致
__________人民法院

具状人：{settings.COMPANY_NAME}（盖章）
{datetime.now().strftime('%Y年%m月%d日')}
        """
        return doc.strip()

    def _generate_pre_analysis(self, case: InfringementCase) -> str:
        analysis = f"""
案件预分析报告

案件编号：{case.case_number}
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

一、案件基本信息
- 涉嫌侵权知识产权：{case.ip.name if case.ip else ''}（{case.ip.ip_number if case.ip else ''}）
- 侵权方：{case.infringing_party.name if case.infringing_party else ''}
- 平台：{case.product.platform.value if case.product else ''}
- 相似度：{case.similarity_score * 100:.1f}%
- 风险等级：{case.risk_level.value}

二、侵权方历史记录
- 历史被投诉次数：{case.infringing_party.complaint_count if case.infringing_party else 0}次

三、案件评估
1. 胜诉概率评估：{self._assess_win_probability(case)}
2. 预计赔偿金额范围：{self._estimate_compensation(case)}
3. 预计诉讼周期：6-18个月
4. 建议诉讼策略：{self._recommend_strategy(case)}

四、成本预估
- 律师费：______元
- 诉讼费：______元
- 公证费：______元
- 其他费用：______元
- 合计：______元

五、处理建议
{self._generate_recommendations(case)}
        """
        return analysis.strip()

    def _assess_win_probability(self, case: InfringementCase) -> str:
        score = case.similarity_score
        if score >= 0.9:
            return "高（90%以上）"
        elif score >= 0.85:
            return "较高（75%-90%）"
        elif score >= 0.8:
            return "中等（60%-75%）"
        else:
            return "一般（50%-60%）"

    def _estimate_compensation(self, case: InfringementCase) -> str:
        sales = case.product.sales_volume if case.product else 0
        price = case.product.price if case.product else 0

        if sales and price:
            estimated = sales * price * 0.1
            return f"约 {estimated:.2f} - {estimated * 3:.2f} 元"
        else:
            return "10万 - 50万元（法定赔偿范围）"

    def _recommend_strategy(self, case: InfringementCase) -> str:
        if case.risk_level == RiskLevelEnum.HIGH:
            return "建议采取强力诉讼策略，同时申请行为保全"
        elif case.risk_level == RiskLevelEnum.MEDIUM:
            return "建议采取谈判+诉讼组合策略，争取和解"
        else:
            return "建议优先采取行政投诉、平台投诉等低成本方式"

    def _generate_recommendations(self, case: InfringementCase) -> str:
        return """
1. 立即固定全部侵权证据，进行网页公证；
2. 对侵权商品进行购买公证，留存实物证据；
3. 调查被告主体信息，明确诉讼主体资格；
4. 准备权利基础证据，确保证据链完整；
5. 评估诉讼成本与预期收益，制定诉讼策略。
        """

    def create_litigation(self, case_id: int) -> Optional[Litigation]:
        with get_db() as db:
            case = db.query(InfringementCase).filter(InfringementCase.id == case_id).first()
            if not case:
                logger.error(f"案件 {case_id} 不存在")
                return None

            litigation_number = self._generate_litigation_number()
            lit_doc = self._generate_litigation_document(case)
            pre_analysis = self._generate_pre_analysis(case)

            case_dir = Path(settings.EVIDENCE_STORAGE_PATH) / case.case_number
            case_dir.mkdir(parents=True, exist_ok=True)

            lit_doc_path = case_dir / f"{litigation_number}_complaint.doc"
            lit_doc_path.write_text(lit_doc, encoding="utf-8")

            pre_analysis_path = case_dir / f"{litigation_number}_pre_analysis.doc"
            pre_analysis_path.write_text(pre_analysis, encoding="utf-8")

            litigation = Litigation(
                case_id=case.id,
                litigation_number=litigation_number,
                litigation_doc_path=str(lit_doc_path),
                pre_analysis_path=str(pre_analysis_path)
            )
            db.add(litigation)

            case.status = InfringementStatusEnum.LITIGATION_PREPARED
            if not case.first_response_due:
                from datetime import timedelta
                case.first_response_due = datetime.now() + timedelta(days=15)

            db.commit()
            db.refresh(litigation)

            self.op_logger.log_operation(
                operation_type=OperationTypeEnum.CREATE_LITIGATION,
                target_id=case.id,
                target_type="infringement_case",
                details={"litigation_number": litigation_number}
            )

            logger.info(f"诉讼文档已生成: {litigation_number}, 案件: {case.case_number}")
            return litigation

    def process_high_risk_cases(self) -> List[Litigation]:
        with get_db() as db:
            high_risk_cases = db.query(InfringementCase).filter(
                InfringementCase.risk_level == RiskLevelEnum.HIGH,
                InfringementCase.status == InfringementStatusEnum.CONFIRMED
            ).all()

            litigations = []
            for case in high_risk_cases:
                try:
                    litigation = self.create_litigation(case.id)
                    if litigation:
                        litigations.append(litigation)
                except Exception as e:
                    logger.error(f"生成诉讼文档失败 {case.case_number}: {e}")

            logger.info(f"批量处理高风险案件，生成 {len(litigations)} 份诉讼文档")
            return litigations

    def update_litigation_status(
        self,
        litigation_id: int,
        court: Optional[str] = None,
        filing_date: Optional = None,
        hearing_date: Optional = None,
        judgment_date: Optional = None,
        judgment_result: Optional[str] = None
    ) -> bool:
        with get_db() as db:
            litigation = db.query(Litigation).filter(Litigation.id == litigation_id).first()
            if not litigation:
                return False

            if court:
                litigation.court = court
            if filing_date:
                litigation.filing_date = filing_date
            if hearing_date:
                litigation.hearing_date = hearing_date
            if judgment_date:
                litigation.judgment_date = judgment_date
            if judgment_result:
                litigation.judgment_result = judgment_result

            db.commit()
            logger.info(f"诉讼信息已更新: {litigation.litigation_number}")
            return True
