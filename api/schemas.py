from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Generic, TypeVar, Optional, Generic
from enum import Enum


class IPTypeEnum(str, Enum):
    PATENT = "patent"
    TRADEMARK = "trademark"
    COPYRIGHT = "copyright"


class IPStatusEnum(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING = "pending"


class InfringementStatusEnum(str, Enum):
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


class RiskLevelEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlatformEnum(str, Enum):
    TAOBAO = "taobao"
    TMALL = "tmall"
    JD = "jd"
    PDD = "pdd"
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    WEIBO = "weibo"
    WECHAT = "wechat"
    OTHER = "other"


class OperationTypeEnum(str, Enum):
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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    role: str
    email: Optional[str] = None


class IntellectualPropertyBase(BaseModel):
    ip_type: IPTypeEnum
    ip_number: str
    name: str
    owner: str
    description: Optional[str] = None
    application_date: Optional[date] = None
    grant_date: Optional[date] = None
    expiration_date: Optional[date] = None
    status: Optional[IPStatusEnum] = IPStatusEnum.ACTIVE
    category: Optional[str] = None
    keywords: Optional[List[str]] = None
    image_urls: Optional[List[str]] = None


class IntellectualPropertyCreate(IntellectualPropertyBase):
    pass


class IntellectualPropertyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IPStatusEnum] = None
    category: Optional[str] = None
    keywords: Optional[List[str]] = None


class IntellectualPropertyResponse(IntellectualPropertyBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InfringementCaseBase(BaseModel):
    pass


class InfringementCaseResponse(BaseModel):
    id: int
    case_number: str
    similarity_score: float
    status: InfringementStatusEnum
    risk_level: RiskLevelEnum
    source_type: str
    evidence_pack_path: Optional[str] = None
    assigned_lawyer: Optional[str] = None
    first_response_due: Optional[datetime] = None
    compensation_amount: Optional[float] = None
    cost_amount: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    ip_info: Optional[Dict[str, Any]] = None
    product_info: Optional[Dict[str, Any]] = None
    party_info: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    total: int
    items: List[InfringementCaseResponse]


class CaseStatusUpdate(BaseModel):
    status: InfringementStatusEnum
    notes: Optional[str] = None


class LawyerAssign(BaseModel):
    lawyer_id: int


class CrawlRequest(BaseModel):
    keywords: List[str]


class OperationLogResponse(BaseModel):
    id: int
    operation_type: OperationTypeEnum
    operator: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    success: bool
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LogListResponse(BaseModel):
    total: int
    items: List[OperationLogResponse]


class DashboardStats(BaseModel):
    total_cases: int
    new_cases_today: int
    pending_cases: int
    high_risk_cases: int
    total_compensation: float
    total_cost: float
    success_rate: float
    active_ips: int


class OfflineClueCreate(BaseModel):
    infringing_party_name: str
    infringing_content: str
    infringing_location: Optional[str] = None
    discovery_date: Optional[date] = None
    reporter: Optional[str] = None
    contact_info: Optional[str] = None
    notes: Optional[str] = None


class OfflineClueResponse(BaseModel):
    id: int
    clue_number: str
    infringing_party_name: str
    infringing_content: str
    is_duplicate: bool
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WeeklyReportResponse(BaseModel):
    id: int
    report_week: str
    start_date: date
    end_date: date
    new_cases: int
    closed_cases: int
    success_rate: float
    total_compensation: float
    pdf_path: Optional[str] = None
    excel_path: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class APIResponse(BaseModel):
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None


PaginatedData = TypeVar("PaginatedData")


class PaginatedResponse(BaseModel, Generic[PaginatedData]):
    success: bool = True
    message: str = "查询成功"
    total: int
    page: int
    page_size: int
    items: List[PaginatedData]
