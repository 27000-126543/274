from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy.orm import joinedload
from api.auth import get_current_active_user
from api.schemas import (
    InfringementCaseResponse, CaseListResponse, APIResponse,
    CaseStatusUpdate, LawyerAssign, PaginatedResponse
)
from database.connection import get_db
from database.models import (
    InfringementCase, InfringementStatusEnum, RiskLevelEnum,
    IntellectualProperty, CrawledProduct, InfringingParty
)
from modules import (
    EvidenceGenerator, CaseManager, WarningLetterManager,
    LitigationManager, QueryManager, ExportManager
)
from utils.logger import logger

router = APIRouter(prefix="/api/cases", tags=["案件管理"])


@router.get("", response_model=PaginatedResponse)
async def list_cases(
    status: Optional[InfringementStatusEnum] = None,
    risk_level: Optional[RiskLevelEnum] = None,
    infringing_party: Optional[str] = None,
    ip_number: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        query = db.query(InfringementCase).options(
            joinedload(InfringementCase.ip),
            joinedload(InfringementCase.product),
            joinedload(InfringementCase.infringing_party)
        )

        if status:
            query = query.filter(InfringementCase.status == status)
        if risk_level:
            query = query.filter(InfringementCase.risk_level == risk_level)
        if infringing_party:
            query = query.join(InfringingParty).filter(
                InfringingParty.name.like(f"%{infringing_party}%")
            )
        if ip_number:
            query = query.join(IntellectualProperty).filter(
                IntellectualProperty.ip_number.like(f"%{ip_number}%")
            )
        if start_date:
            query = query.filter(InfringementCase.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            query = query.filter(InfringementCase.created_at <= datetime.combine(end_date, datetime.max.time()))

        total = query.count()
        cases = query.order_by(InfringementCase.created_at.desc())\
            .offset((page - 1) * page_size)\
            .limit(page_size)\
            .all()

        items = []
        for case in cases:
            case_data = {
                "id": case.id,
                "case_number": case.case_number,
                "similarity_score": case.similarity_score,
                "status": case.status,
                "risk_level": case.risk_level,
                "source_type": case.source_type,
                "evidence_pack_path": case.evidence_pack_path,
                "assigned_lawyer": case.assigned_lawyer,
                "first_response_due": case.first_response_due,
                "compensation_amount": case.compensation_amount,
                "cost_amount": case.cost_amount,
                "created_at": case.created_at,
                "updated_at": case.updated_at,
                "ip_info": {
                    "ip_type": case.ip.ip_type.value if case.ip else "",
                    "ip_number": case.ip.ip_number if case.ip else "",
                    "name": case.ip.name if case.ip else ""
                } if case.ip else None,
                "product_info": {
                    "platform": case.product.platform.value if case.product else "",
                    "title": case.product.title if case.product else "",
                    "seller_name": case.product.seller_name if case.product else ""
                } if case.product else None,
                "party_info": {
                    "name": case.infringing_party.name if case.infringing_party else "",
                    "complaint_count": case.infringing_party.complaint_count if case.infringing_party else 0
                } if case.infringing_party else None
            }
            items.append(case_data)

        return PaginatedResponse(
            success=True,
            message="查询成功",
            total=total,
            page=page,
            page_size=page_size,
            items=items
        )


@router.get("/{case_id}", response_model=APIResponse)
async def get_case_detail(
    case_id: int,
    current_user: dict = Depends(get_current_active_user)
):
    query_mgr = QueryManager()
    lifecycle = query_mgr.query_case_full_lifecycle(case_id)
    if not lifecycle:
        raise HTTPException(status_code=404, detail="案件不存在")
    return APIResponse(success=True, message="获取成功", data=lifecycle)


@router.patch("/{case_id}/status", response_model=APIResponse)
async def update_case_status(
    case_id: int,
    status_update: CaseStatusUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    case_mgr = CaseManager()
    case = case_mgr.update_case_status(case_id, status_update.status, status_update.notes)
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    return APIResponse(success=True, message="状态更新成功")


@router.post("/{case_id}/assign-lawyer", response_model=APIResponse)
async def assign_lawyer(
    case_id: int,
    lawyer_data: LawyerAssign,
    current_user: dict = Depends(get_current_active_user)
):
    case_mgr = CaseManager()
    case = case_mgr.assign_lawyer(case_id, lawyer_data.lawyer_id)
    if not case:
        raise HTTPException(status_code=404, detail="案件或律师不存在")
    return APIResponse(success=True, message="律师指派成功")


@router.post("/{case_id}/generate-evidence", response_model=APIResponse)
async def generate_evidence(
    case_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user)
):
    evidence_gen = EvidenceGenerator()

    def generate():
        try:
            evidence_gen.generate_evidence_pack(case_id)
        except Exception as e:
            logger.error(f"生成证据包失败: {e}")

    background_tasks.add_task(generate)
    return APIResponse(success=True, message="证据包正在后台生成，请稍后查看")


@router.post("/{case_id}/send-warning", response_model=APIResponse)
async def send_warning_letter(
    case_id: int,
    current_user: dict = Depends(get_current_active_user)
):
    warning_mgr = WarningLetterManager()
    letter = warning_mgr.send_warning_letter(case_id)
    if not letter:
        raise HTTPException(status_code=400, detail="警告函发送失败，可能是风险等级不符合或案件不存在")
    return APIResponse(success=True, message="警告函已发送", data={"letter_number": letter.letter_number})


@router.post("/{case_id}/create-litigation", response_model=APIResponse)
async def create_litigation(
    case_id: int,
    current_user: dict = Depends(get_current_active_user)
):
    litigation_mgr = LitigationManager()
    litigation = litigation_mgr.create_litigation(case_id)
    if not litigation:
        raise HTTPException(status_code=400, detail="诉讼文档生成失败")
    return APIResponse(
        success=True,
        message="诉讼文档已生成",
        data={
            "litigation_number": litigation.litigation_number,
            "doc_path": litigation.litigation_doc_path,
            "analysis_path": litigation.pre_analysis_path
        }
    )


@router.get("/export/download")
async def export_cases(
    status: Optional[InfringementStatusEnum] = None,
    risk_level: Optional[RiskLevelEnum] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: dict = Depends(get_current_active_user)
):
    from fastapi.responses import FileResponse
    import os

    query_mgr = QueryManager()
    cases = query_mgr.query_cases(
        status=status,
        risk_level=risk_level,
        start_date=start_date,
        end_date=end_date,
        limit=10000
    )

    export_mgr = ExportManager()
    export_path = export_mgr.export_cases_to_excel(cases)

    if os.path.exists(export_path):
        return FileResponse(
            export_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=os.path.basename(export_path)
        )
    raise HTTPException(status_code=500, detail="导出失败")
