from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON, Enum, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .connection import Base


class IPTypeEnum(str, enum.Enum):
    PATENT = "patent"
    TRADEMARK = "trademark"
    COPYRIGHT = "copyright"


class IPStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING = "pending"


class InfringementStatusEnum(str, enum.Enum):
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"
    WARNING_SENT = "warning_sent"
    WARNING_ACKNOWLEDGED = "warning_acknowledged"
    LITIGATION_PREPARED = "litigation_prepared"
    LITIGATION_IN_PROGRESS = "litigation_in_progress"
    SETTLED = "settled"
    WON = "won"
    LOST = "lost"
    CLOSED = "closed"


class RiskLevelEnum(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlatformEnum(str, enum.Enum):
    TAOBAO = "taobao"
    TMALL = "tmall"
    JD = "jd"
    PDD = "pdd"
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    WEIBO = "weibo"
    WECHAT = "wechat"
    OTHER = "other"


class OperationTypeEnum(str, enum.Enum):
    CRAWL = "crawl"
    COMPARE = "compare"
    MARK_INFRINGEMENT = "mark_infringement"
    GENERATE_EVIDENCE = "generate_evidence"
    SEND_WARNING = "send_warning"
    CREATE_LITIGATION = "create_litigation"
    ASSIGN_LAWYER = "assign_lawyer"
    ESCALATE = "escalate"
    UPDATE_STATUS = "update_status"
    MANUAL_ENTRY = "manual_entry"
    MERGE_CLUE = "merge_clue"
    GENERATE_REPORT = "generate_report"
    EXPORT_DATA = "export_data"


class IntellectualProperty(Base):
    __tablename__ = "intellectual_properties"

    id = Column(Integer, primary_key=True, index=True)
    ip_type = Column(Enum(IPTypeEnum), index=True, nullable=False)
    ip_number = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner = Column(String(255), nullable=False)
    application_date = Column(Date, nullable=True)
    grant_date = Column(Date, nullable=True)
    expiration_date = Column(Date, nullable=True)
    status = Column(Enum(IPStatusEnum), default=IPStatusEnum.ACTIVE)
    category = Column(String(100), nullable=True)
    keywords = Column(JSON, default=list)
    image_urls = Column(JSON, default=list)
    document_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    infringements = relationship("InfringementCase", back_populates="ip")


class CrawledProduct(Base):
    __tablename__ = "crawled_products"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(Enum(PlatformEnum), index=True, nullable=False)
    product_id = Column(String(100), index=True, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=True)
    seller_name = Column(String(255), nullable=True)
    seller_id = Column(String(100), nullable=True)
    seller_level = Column(Integer, nullable=True)
    seller_fans = Column(Integer, nullable=True)
    product_url = Column(String(500), nullable=False)
    image_urls = Column(JSON, default=list)
    category = Column(String(200), nullable=True)
    sales_volume = Column(Integer, nullable=True)
    crawl_time = Column(DateTime(timezone=True), server_default=func.now())
    content_hash = Column(String(64), index=True)

    infringements = relationship("InfringementCase", back_populates="product")


class InfringingParty(Base):
    __tablename__ = "infringing_parties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    contact_person = Column(String(100), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    platform = Column(Enum(PlatformEnum), nullable=True)
    shop_url = Column(String(500), nullable=True)
    shop_level = Column(Integer, nullable=True)
    fans_count = Column(Integer, nullable=True)
    complaint_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    cases = relationship("InfringementCase", back_populates="infringing_party")


class InfringementCase(Base):
    __tablename__ = "infringement_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_number = Column(String(50), unique=True, index=True, nullable=False)
    ip_id = Column(Integer, ForeignKey("intellectual_properties.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("crawled_products.id"), nullable=True)
    infringing_party_id = Column(Integer, ForeignKey("infringing_parties.id"), nullable=True)
    similarity_score = Column(Float, nullable=False, index=True)
    status = Column(Enum(InfringementStatusEnum), default=InfringementStatusEnum.SUSPECTED, index=True)
    risk_level = Column(Enum(RiskLevelEnum), default=RiskLevelEnum.LOW, index=True)
    source_type = Column(String(50), default="auto_crawl")
    evidence_pack_path = Column(String(500), nullable=True)
    assigned_lawyer = Column(String(100), nullable=True)
    assigned_lawyer_email = Column(String(255), nullable=True)
    first_response_due = Column(DateTime(timezone=True), nullable=True)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)
    compensation_amount = Column(Float, nullable=True)
    cost_amount = Column(Float, nullable=True)
    settlement_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    ip = relationship("IntellectualProperty", back_populates="infringements")
    product = relationship("CrawledProduct", back_populates="infringements")
    infringing_party = relationship("InfringingParty", back_populates="cases")
    warning_letters = relationship("WarningLetter", back_populates="case")
    litigations = relationship("Litigation", back_populates="case")
    evidences = relationship("Evidence", back_populates="case")
    ledger_entries = relationship("RightsProtectionLedger", back_populates="case")


class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("infringement_cases.id"), nullable=False)
    evidence_type = Column(String(50), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    md5_hash = Column(String(32), nullable=True)
    description = Column(Text, nullable=True)

    case = relationship("InfringementCase", back_populates="evidences")


class WarningLetter(Base):
    __tablename__ = "warning_letters"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("infringement_cases.id"), nullable=False)
    letter_number = Column(String(50), unique=True, index=True, nullable=False)
    send_to = Column(String(255), nullable=False)
    send_email = Column(String(255), nullable=False)
    send_time = Column(DateTime(timezone=True), server_default=func.now())
    content = Column(Text, nullable=False)
    receipt_received = Column(Boolean, default=False)
    receipt_time = Column(DateTime(timezone=True), nullable=True)
    response_content = Column(Text, nullable=True)

    case = relationship("InfringementCase", back_populates="warning_letters")


class Litigation(Base):
    __tablename__ = "litigations"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("infringement_cases.id"), nullable=False)
    litigation_number = Column(String(50), unique=True, index=True, nullable=False)
    court = Column(String(255), nullable=True)
    filing_date = Column(Date, nullable=True)
    hearing_date = Column(Date, nullable=True)
    judgment_date = Column(Date, nullable=True)
    judgment_result = Column(String(500), nullable=True)
    litigation_doc_path = Column(String(500), nullable=True)
    pre_analysis_path = Column(String(500), nullable=True)
    is_batch = Column(Boolean, default=False)
    batch_id = Column(String(50), nullable=True)

    case = relationship("InfringementCase", back_populates="litigations")


class RightsProtectionLedger(Base):
    __tablename__ = "rights_protection_ledgers"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("infringement_cases.id"), nullable=False)
    record_date = Column(Date, nullable=False)
    compensation_amount = Column(Float, default=0)
    attorney_fee = Column(Float, default=0)
    court_fee = Column(Float, default=0)
    evidence_fee = Column(Float, default=0)
    other_cost = Column(Float, default=0)
    total_cost = Column(Float, default=0)
    net_amount = Column(Float, default=0)
    payment_status = Column(String(50), default="pending")
    notes = Column(Text, nullable=True)

    case = relationship("InfringementCase", back_populates="ledger_entries")


class OfflineClue(Base):
    __tablename__ = "offline_clues"

    id = Column(Integer, primary_key=True, index=True)
    clue_number = Column(String(50), unique=True, index=True, nullable=False)
    infringing_party_name = Column(String(255), nullable=False)
    infringing_content = Column(Text, nullable=False)
    infringing_location = Column(String(255), nullable=True)
    discovery_date = Column(Date, nullable=True)
    reporter = Column(String(100), nullable=True)
    contact_info = Column(String(255), nullable=True)
    is_duplicate = Column(Boolean, default=False)
    merged_to_clue_id = Column(Integer, nullable=True)
    case_id = Column(Integer, ForeignKey("infringement_cases.id"), nullable=True)
    status = Column(String(50), default="pending")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("InfringementCase")


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    operation_type = Column(Enum(OperationTypeEnum), index=True, nullable=False)
    operator = Column(String(100), nullable=True)
    target_id = Column(Integer, nullable=True)
    target_type = Column(String(50), nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(50), nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_week = Column(String(20), unique=True, index=True, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_cases = Column(Integer, default=0)
    new_cases = Column(Integer, default=0)
    closed_cases = Column(Integer, default=0)
    success_rate = Column(Float, default=0)
    avg_response_time_hours = Column(Float, default=0)
    low_risk_count = Column(Integer, default=0)
    medium_risk_count = Column(Integer, default=0)
    high_risk_count = Column(Integer, default=0)
    total_compensation = Column(Float, default=0)
    total_cost = Column(Float, default=0)
    pdf_path = Column(String(500), nullable=True)
    excel_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Lawyer(Base):
    __tablename__ = "lawyers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50), nullable=True)
    position = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    case_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
