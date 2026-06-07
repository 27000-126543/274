from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from datetime import datetime, date, timedelta
from typing import Optional
from api.auth import get_current_active_user
from api.schemas import (
    APIResponse, OperationTypeEnum, PaginatedResponse,
    DashboardStats, OfflineClueCreate,
    OfflineClueResponse, WeeklyReportResponse
)
from database.connection import get_db
from database.models import (
    OperationLog, InfringementCase, InfringementStatusEnum,
    RiskLevelEnum, IntellectualProperty, IPStatusEnum,
    OfflineClue, WeeklyReport
)
from modules import (
    SpiderManager, SimilarityMatcher, CaseManager,
    OfflineClueManager, ReportGenerator, BatchLitigationManager,
    LedgerManager
)
from utils.logger import logger

router = APIRouter(prefix="/api/system", tags=["系统操作"])


@router.get("/dashboard", response_model=APIResponse)
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())

        total_cases = db.query(InfringementCase).count()
        new_cases_today = db.query(InfringementCase).filter(
            InfringementCase.created_at >= today_start
        ).count()
        pending_cases = db.query(InfringementCase).filter(
            InfringementCase.status.in_([
                InfringementStatusEnum.CONFIRMED,
                InfringementStatusEnum.WARNING_SENT,
                InfringementStatusEnum.LITIGATION_PREPARED,
                InfringementStatusEnum.LITIGATION_IN_PROGRESS
            ])
        ).count()
        high_risk_cases = db.query(InfringementCase).filter(
            InfringementCase.risk_level == RiskLevelEnum.HIGH,
            InfringementCase.status.notin_([
                InfringementStatusEnum.SETTLED,
                InfringementStatusEnum.WON,
                InfringementStatusEnum.CLOSED
            ])
        ).count()

        total_compensation = db.query(InfringementCase).with_entities(
            db.func.sum(InfringementCase.compensation_amount)
        ).scalar() or 0
        total_cost = db.query(InfringementCase).with_entities(
            db.func.sum(InfringementCase.cost_amount)
        ).scalar() or 0

        total_settled = db.query(InfringementCase).filter(
            InfringementCase.status.in_([
                InfringementStatusEnum.SETTLED,
                InfringementStatusEnum.WON
            ])
        ).count()
        total_with_result = db.query(InfringementCase).filter(
            InfringementCase.status.in_([
                InfringementStatusEnum.SETTLED,
                InfringementStatusEnum.WON,
                InfringementStatusEnum.LOST,
                InfringementStatusEnum.CLOSED
            ])
        ).count()
        success_rate = (total_settled / total_with_result * 100) if total_with_result > 0 else 0

        active_ips = db.query(IntellectualProperty).filter(
            IntellectualProperty.status == IPStatusEnum.ACTIVE
        ).count()

        stats = DashboardStats(
            total_cases=total_cases,
            new_cases_today=new_cases_today,
            pending_cases=pending_cases,
            high_risk_cases=high_risk_cases,
            total_compensation=float(total_compensation),
            total_cost=float(total_cost),
            success_rate=round(success_rate, 2),
            active_ips=active_ips
        )

        return APIResponse(success=True, message="获取成功", data=stats)


@router.get("/logs", response_model=PaginatedResponse)
async def list_operation_logs(
    operation_type: Optional[OperationTypeEnum] = None,
    operator: Optional[str] = None,
    target_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        query = db.query(OperationLog)

        if operation_type:
            query = query.filter(OperationLog.operation_type == operation_type)
        if operator:
            query = query.filter(OperationLog.operator.like(f"%{operator}%"))
        if target_type:
            query = query.filter(OperationLog.target_type == target_type)
        if start_date:
            query = query.filter(OperationLog.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            query = query.filter(OperationLog.created_at <= datetime.combine(end_date, datetime.max.time()))

        total = query.count()
        logs = query.order_by(OperationLog.created_at.desc())\
            .offset((page - 1) * page_size)\
            .limit(page_size)\
            .all()

        return PaginatedResponse(
            success=True,
            message="查询成功",
            total=total,
            page=page,
            page_size=page_size,
            items=logs
        )


@router.post("/crawl/start", response_model=APIResponse)
async def start_crawl(
    background_tasks: BackgroundTasks,
    keywords: Optional[list[str]] = None,
    current_user: dict = Depends(get_current_active_user)
):
    spider_mgr = SpiderManager()
    similarity_matcher = SimilarityMatcher()
    case_mgr = CaseManager()

    async def crawl_and_compare():
        try:
            if not keywords:
                from database.models import IPStatusEnum
                with get_db() as db:
                    active_ips = db.query(IntellectualProperty).filter(
                        IntellectualProperty.status == IPStatusEnum.ACTIVE
                    ).all()
                keywords_to_use = []
                for ip in active_ips:
                    if ip.name:
                        keywords_to_use.append(ip.name)
                    if ip.keywords:
                        keywords_to_use.extend(ip.keywords)
                keywords_to_use = list(set(keywords_to_use))[:30]
            else:
                keywords_to_use = keywords

            import asyncio
            products = await spider_mgr.crawl_multiple_keywords(keywords_to_use)
            saved_count = spider_mgr.save_products(products)

            suspected = similarity_matcher.get_suspected_matches()
            if suspected:
                case_mgr.batch_create_cases(suspected)

            logger.info(f"手动触发爬取完成: {saved_count}个商品, {len(suspected)}个疑似侵权")
        except Exception as e:
            logger.error(f"手动爬取任务失败: {e}", exc_info=True)

    background_tasks.add_task(lambda: asyncio.run(crawl_and_compare()))

    return APIResponse(success=True, message="爬取任务已在后台启动，请稍候查看结果")


@router.post("/report/generate", response_model=APIResponse)
async def generate_report(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user)
):
    report_gen = ReportGenerator()

    def generate():
        try:
            report_gen.generate_weekly_report()
        except Exception as e:
            logger.error(f"生成报告失败: {e}")

    background_tasks.add_task(generate)
    return APIResponse(success=True, message="报告生成任务已在后台启动")


@router.get("/reports", response_model=PaginatedResponse)
async def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        query = db.query(WeeklyReport)
        total = query.count()
        reports = query.order_by(WeeklyReport.start_date.desc())\
            .offset((page - 1) * page_size)\
            .limit(page_size)\
            .all()

        return PaginatedResponse(
            success=True,
            message="查询成功",
            total=total,
            page=page,
            page_size=page_size,
            items=[WeeklyReportResponse.model_validate(r) for r in reports]
        )


@router.post("/offline-clues", response_model=APIResponse)
async def add_offline_clue(
    clue_data: OfflineClueCreate,
    current_user: dict = Depends(get_current_active_user)
):
    clue_mgr = OfflineClueManager()
    clue = clue_mgr.add_offline_clue(**clue_data.model_dump())
    return APIResponse(
        success=True,
        message="线索添加成功",
        data=OfflineClueResponse.model_validate(clue)
    )


@router.get("/offline-clues", response_model=PaginatedResponse)
async def list_offline_clues(
    status: Optional[str] = None,
    is_duplicate: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user)
):
    clue_mgr = OfflineClueManager()
    clues = clue_mgr.list_clues(
        status=status,
        is_duplicate=is_duplicate,
        skip=(page - 1) * page_size,
        limit=page_size
    )
    with get_db() as db:
        total = db.query(OfflineClue).count()

    return PaginatedResponse(
        success=True,
        message="查询成功",
        total=total,
        page=page,
        page_size=page_size,
        items=[OfflineClueResponse.model_validate(c) for c in clues]
    )


@router.get("/batch-litigation/check", response_model=APIResponse)
async def check_batch_litigation(
    current_user: dict = Depends(get_current_active_user)
):
    batch_mgr = BatchLitigationManager()
    suggestions = batch_mgr.check_and_generate_batch_suggestions()
    return APIResponse(
        success=True,
        message="批量诉讼检查完成",
        data={"count": len(suggestions), "suggestions": suggestions}
    )


@router.get("/ledger/summary", response_model=APIResponse)
async def get_ledger_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: dict = Depends(get_current_active_user)
):
    ledger_mgr = LedgerManager()
    summary = ledger_mgr.get_ledger_summary(start_date, end_date)
    return APIResponse(success=True, message="获取成功", data=summary)
