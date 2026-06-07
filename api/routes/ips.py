from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date
from typing import Optional, List
from api.auth import get_current_active_user
from api.schemas import (
    IntellectualPropertyCreate, IntellectualPropertyUpdate,
    IntellectualPropertyResponse, PaginatedResponse, APIResponse,
    IPTypeEnum, IPStatusEnum
)
from database.connection import get_db
from database.models import IntellectualProperty
from modules import IntellectualPropertyManager

router = APIRouter(prefix="/api/ips", tags=["知识产权库"])


@router.get("", response_model=PaginatedResponse)
async def list_ips(
    ip_type: Optional[IPTypeEnum] = None,
    status: Optional[IPStatusEnum] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        ip_mgr = IntellectualPropertyManager(db)
        ips = ip_mgr.list_ips(
            ip_type=ip_type,
            status=status,
            category=category,
            keyword=keyword,
            skip=(page - 1) * page_size,
            limit=page_size
        )

        total = db.query(IntellectualProperty).count()

        return PaginatedResponse(
            success=True,
            message="查询成功",
            total=total,
            page=page,
            page_size=page_size,
            items=[IntellectualPropertyResponse.model_validate(ip) for ip in ips]
        )


@router.get("/{ip_id}", response_model=APIResponse)
async def get_ip(
    ip_id: int,
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        ip_mgr = IntellectualPropertyManager(db)
        ip = ip_mgr.get_ip_by_id(ip_id)
        if not ip:
            raise HTTPException(status_code=404, detail="知识产权不存在")
        return APIResponse(
            success=True,
            message="获取成功",
            data=IntellectualPropertyResponse.model_validate(ip)
        )


@router.post("", response_model=APIResponse)
async def create_ip(
    ip_data: IntellectualPropertyCreate,
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        ip_mgr = IntellectualPropertyManager(db)
        ip = ip_mgr.add_ip(**ip_data.model_dump())
        return APIResponse(
            success=True,
            message="添加成功",
            data=IntellectualPropertyResponse.model_validate(ip)
        )


@router.patch("/{ip_id}", response_model=APIResponse)
async def update_ip(
    ip_id: int,
    ip_update: IntellectualPropertyUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        ip_mgr = IntellectualPropertyManager(db)
        ip = ip_mgr.update_ip(ip_id, **ip_update.model_dump(exclude_unset=True))
        if not ip:
            raise HTTPException(status_code=404, detail="知识产权不存在")
        return APIResponse(
            success=True,
            message="更新成功",
            data=IntellectualPropertyResponse.model_validate(ip)
        )


@router.delete("/{ip_id}", response_model=APIResponse)
async def delete_ip(
    ip_id: int,
    current_user: dict = Depends(get_current_active_user)
):
    with get_db() as db:
        ip_mgr = IntellectualPropertyManager(db)
        success = ip_mgr.delete_ip(ip_id)
        if not success:
            raise HTTPException(status_code=404, detail="知识产权不存在")
        return APIResponse(success=True, message="删除成功")
