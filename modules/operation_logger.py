from typing import Optional, Dict, Any
from database.models import OperationLog, OperationTypeEnum
from database.connection import get_db
from utils.logger import logger


class OperationLogger:
    def __init__(self):
        pass

    def log_operation(
        self,
        operation_type: OperationTypeEnum,
        operator: Optional[str] = "system",
        target_id: Optional[int] = None,
        target_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> OperationLog:
        with get_db() as db:
            log = OperationLog(
                operation_type=operation_type,
                operator=operator,
                target_id=target_id,
                target_type=target_type,
                details=details or {},
                ip_address=ip_address,
                success=success,
                error_message=error_message
            )
            db.add(log)
            db.commit()
            db.refresh(log)

            if success:
                logger.info(f"操作日志: {operation_type.value}, 目标: {target_type}#{target_id}, 操作人: {operator}")
            else:
                logger.error(f"操作日志(失败): {operation_type.value}, 目标: {target_type}#{target_id}, 错误: {error_message}")

            return log

    def get_logs(
        self,
        operation_type: Optional[OperationTypeEnum] = None,
        operator: Optional[str] = None,
        target_type: Optional[str] = None,
        start_time: Optional = None,
        end_time: Optional = None,
        skip: int = 0,
        limit: int = 100
    ):
        with get_db() as db:
            query = db.query(OperationLog)

            if operation_type:
                query = query.filter(OperationLog.operation_type == operation_type)
            if operator:
                query = query.filter(OperationLog.operator == operator)
            if target_type:
                query = query.filter(OperationLog.target_type == target_type)
            if start_time:
                query = query.filter(OperationLog.created_at >= start_time)
            if end_time:
                query = query.filter(OperationLog.created_at <= end_time)

            return query.order_by(OperationLog.created_at.desc()).offset(skip).limit(limit).all()
