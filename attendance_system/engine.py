import asyncio
import logging
import os
import csv
import json
import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Base, Employee, Department, PunchRecord, AnomalyRecord, AnomalyType, AnomalyStatus,
    OperationLog, Schedule, ScheduleStatus, Shift, PunchSource, PunchType,
)
from .config import get_config, SystemConfig

logger = logging.getLogger(__name__)


def setup_logging(config: SystemConfig = None):
    config = config or get_config()
    log_dir = os.path.dirname(config.log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger("attendance_system")
    root_logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        config.log_file,
        maxBytes=config.log_file_max_size_mb * 1024 * 1024 if hasattr(config, "log_file_max_size_mb") else 100 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return root_logger


try:
    import logging.handlers
except ImportError:
    pass


class AsyncTaskQueue:
    def __init__(self, max_workers: int = 4, config: SystemConfig = None):
        self.config = config or get_config()
        self.max_workers = max_workers
        self._queue: asyncio.Queue = None
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._results: Dict[str, Any] = {}

    async def start(self):
        self._queue = asyncio.Queue(maxsize=10000)
        self._running = True
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        logger.info("异步任务队列已启动，%d 个工作协程", self.max_workers)

    async def stop(self):
        self._running = False
        for _ in range(self.max_workers):
            await self._queue.put(None)
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()
        logger.info("异步任务队列已停止")

    async def submit(self, task_name: str, coro_factory, **kwargs) -> str:
        task_id = f"{task_name}_{uuid.uuid4().hex[:8]}"
        await self._queue.put({
            "task_id": task_id,
            "task_name": task_name,
            "coro_factory": coro_factory,
            "kwargs": kwargs,
        })
        logger.debug("任务已提交: %s (%s)", task_name, task_id)
        return task_id

    async def _worker(self, worker_id: int):
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if task is None:
                break

            task_id = task["task_id"]
            task_name = task["task_name"]
            try:
                coro = task["coro_factory"](**task["kwargs"])
                result = await coro
                self._results[task_id] = {"status": "success", "result": result}
                logger.info("任务完成: %s (%s)", task_name, task_id)
            except Exception as e:
                self._results[task_id] = {"status": "error", "error": str(e)}
                logger.error("任务失败: %s (%s): %s", task_name, task_id, e)
            finally:
                self._queue.task_done()

    def get_result(self, task_id: str) -> Optional[Dict]:
        return self._results.pop(task_id, None)


class BatchPunchProcessor:
    def __init__(self, batch_size: int = 5000):
        self.batch_size = batch_size

    async def batch_insert_punches(
        self, punch_data: List[Dict], session: AsyncSession,
    ) -> Tuple[int, int]:
        inserted = 0
        skipped = 0

        for i in range(0, len(punch_data), self.batch_size):
            batch = punch_data[i:i + self.batch_size]
            records = []

            for item in batch:
                emp_id = item.get("employee_id")
                punch_time = item.get("punch_time")
                punch_date = item.get("punch_date") or punch_time.date() if isinstance(punch_time, datetime) else None

                if not all([emp_id, punch_time, punch_date]):
                    skipped += 1
                    continue

                stmt_check = select(func.count()).where(
                    and_(
                        PunchRecord.employee_id == emp_id,
                        PunchRecord.punch_date == punch_date,
                        PunchRecord.punch_type == PunchType(item.get("punch_type", "clock_in")),
                        PunchRecord.source == PunchSource(item.get("source", "access_control")),
                    )
                )
                result = await session.execute(stmt_check)
                if result.scalar() > 0:
                    skipped += 1
                    continue

                record = PunchRecord(
                    employee_id=emp_id,
                    punch_time=punch_time if isinstance(punch_time, datetime) else datetime.fromisoformat(punch_time),
                    punch_date=punch_date if isinstance(punch_date, date) else date.fromisoformat(punch_date),
                    punch_type=PunchType(item.get("punch_type", "clock_in")),
                    source=PunchSource(item.get("source", "access_control")),
                    device_id=item.get("device_id"),
                    location_lat=item.get("latitude"),
                    location_lng=item.get("longitude"),
                    location_address=item.get("address"),
                    batch_id=item.get("batch_id"),
                    raw_data=item.get("raw_data"),
                )
                records.append(record)

            if records:
                session.add_all(records)
                inserted += len(records)

        await session.flush()
        logger.info("批量插入打卡: %d 成功, %d 跳过", inserted, skipped)
        return inserted, skipped


class AuditLogger:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        operation_type: str,
        operator_id: int = None,
        operator_name: str = None,
        target_type: str = None,
        target_id: int = None,
        detail: Dict = None,
        ip_address: str = None,
    ):
        log_entry = OperationLog(
            operator_id=operator_id,
            operator_name=operator_name,
            operation_type=operation_type,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            ip_address=ip_address,
        )
        self.session.add(log_entry)
        await session.flush()


class AttendanceQueryEngine:
    def __init__(self, config: SystemConfig = None):
        self.config = config or get_config()

    async def query_attendance_detail(
        self,
        session: AsyncSession,
        employee_id: int = None,
        department_id: int = None,
        start_date: date = None,
        end_date: date = None,
        anomaly_type: AnomalyType = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict:
        conditions = []
        if employee_id:
            conditions.append(PunchRecord.employee_id == employee_id)
        if start_date:
            conditions.append(PunchRecord.punch_date >= start_date)
        if end_date:
            conditions.append(PunchRecord.punch_date <= end_date)

        if department_id:
            stmt_emp = select(Employee.id).where(Employee.department_id == department_id)
            result_emp = await session.execute(stmt_emp)
            emp_ids = [r for r in result_emp.scalars().all()]
            conditions.append(PunchRecord.employee_id.in_(emp_ids))

        where_clause = and_(*conditions) if conditions else True

        count_stmt = select(func.count()).select_from(PunchRecord).where(where_clause)
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = select(PunchRecord).where(where_clause).order_by(
            PunchRecord.punch_date.desc(), PunchRecord.punch_time
        ).offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(stmt)
        records = list(result.scalars().all())

        items = []
        for r in records:
            emp = await session.get(Employee, r.employee_id)
            dept = await session.get(Department, emp.department_id) if emp else None
            items.append({
                "id": r.id,
                "employee_id": r.employee_id,
                "employee_no": emp.employee_no if emp else "",
                "employee_name": emp.name if emp else "",
                "department": dept.name if dept else "",
                "punch_date": r.punch_date.isoformat(),
                "punch_time": r.punch_time.strftime("%H:%M:%S"),
                "punch_type": r.punch_type.value,
                "source": r.source.value,
                "is_supplementary": r.is_supplementary,
                "is_valid": r.is_valid,
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": items,
        }

    async def query_anomaly_detail(
        self,
        session: AsyncSession,
        employee_id: int = None,
        department_id: int = None,
        start_date: date = None,
        end_date: date = None,
        anomaly_type: AnomalyType = None,
        status: AnomalyStatus = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict:
        conditions = []
        if employee_id:
            conditions.append(AnomalyRecord.employee_id == employee_id)
        if start_date:
            conditions.append(AnomalyRecord.anomaly_date >= start_date)
        if end_date:
            conditions.append(AnomalyRecord.anomaly_date <= end_date)
        if anomaly_type:
            conditions.append(AnomalyRecord.anomaly_type == anomaly_type)
        if status:
            conditions.append(AnomalyRecord.status == status)

        if department_id:
            stmt_emp = select(Employee.id).where(Employee.department_id == department_id)
            result_emp = await session.execute(stmt_emp)
            emp_ids = [r for r in result_emp.scalars().all()]
            conditions.append(AnomalyRecord.employee_id.in_(emp_ids))

        where_clause = and_(*conditions) if conditions else True

        count_stmt = select(func.count()).select_from(AnomalyRecord).where(where_clause)
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = select(AnomalyRecord).where(where_clause).order_by(
            AnomalyRecord.anomaly_date.desc()
        ).offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(stmt)
        records = list(result.scalars().all())

        items = []
        for r in records:
            emp = await session.get(Employee, r.employee_id)
            dept = await session.get(Department, emp.department_id) if emp else None
            items.append({
                "id": r.id,
                "employee_id": r.employee_id,
                "employee_no": emp.employee_no if emp else "",
                "employee_name": emp.name if emp else "",
                "department": dept.name if dept else "",
                "anomaly_date": r.anomaly_date.isoformat(),
                "anomaly_type": r.anomaly_type.value,
                "status": r.status.value,
                "deviation_minutes": r.deviation_minutes,
                "description": r.description,
                "auto_detected": r.auto_detected,
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": items,
        }

    async def export_attendance_csv(
        self,
        session: AsyncSession,
        employee_id: int = None,
        department_id: int = None,
        start_date: date = None,
        end_date: date = None,
        output_path: str = None,
    ) -> str:
        result = await self.query_attendance_detail(
            session, employee_id, department_id, start_date, end_date,
            page=1, page_size=100000,
        )

        if not output_path:
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(
                output_dir,
                f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            )

        headers = [
            "ID", "工号", "姓名", "部门", "日期", "时间", "打卡类型", "数据源", "补卡", "有效",
        ]

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for item in result["items"]:
                writer.writerow([
                    item["id"],
                    item["employee_no"],
                    item["employee_name"],
                    item["department"],
                    item["punch_date"],
                    item["punch_time"],
                    item["punch_type"],
                    item["source"],
                    "是" if item["is_supplementary"] else "否",
                    "是" if item["is_valid"] else "否",
                ])

        logger.info("考勤明细已导出: %s (%d 条)", output_path, result["total"])
        return output_path

    async def export_anomaly_csv(
        self,
        session: AsyncSession,
        employee_id: int = None,
        department_id: int = None,
        start_date: date = None,
        end_date: date = None,
        anomaly_type: AnomalyType = None,
        output_path: str = None,
    ) -> str:
        result = await self.query_anomaly_detail(
            session, employee_id, department_id, start_date, end_date, anomaly_type,
            page=1, page_size=100000,
        )

        if not output_path:
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(
                output_dir,
                f"anomaly_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            )

        type_labels = {
            "late": "迟到", "early_leave": "早退", "missing_punch_in": "上班缺卡",
            "missing_punch_out": "下班缺卡", "absent": "缺勤", "overtime_exceed": "超时加班",
        }
        status_labels = {
            "pending": "待确认", "confirmed": "已确认", "appealed": "已申诉",
            "approved": "已通过", "rejected": "已驳回", "auto_corrected": "已自动修正",
        }

        headers = [
            "ID", "工号", "姓名", "部门", "日期", "异常类型", "状态", "偏差(分钟)", "描述",
        ]

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for item in result["items"]:
                writer.writerow([
                    item["id"],
                    item["employee_no"],
                    item["employee_name"],
                    item["department"],
                    item["anomaly_date"],
                    type_labels.get(item["anomaly_type"], item["anomaly_type"]),
                    status_labels.get(item["status"], item["status"]),
                    item["deviation_minutes"] or "",
                    item["description"],
                ])

        logger.info("异常明细已导出: %s (%d 条)", output_path, result["total"])
        return output_path


class AttendanceEngine:
    def __init__(self, config: SystemConfig = None):
        self.config = config or get_config()
        self.task_queue = AsyncTaskQueue(config=self.config)
        self.batch_processor = BatchPunchProcessor()
        self.query_engine = AttendanceQueryEngine(self.config)

    async def start(self):
        await self.task_queue.start()
        logger.info("考勤引擎已启动")

    async def stop(self):
        await self.task_queue.stop()
        logger.info("考勤引擎已停止")

    async def submit_batch_punches(self, punch_data: List[Dict], session: AsyncSession) -> Tuple[int, int]:
        return await self.batch_processor.batch_insert_punches(punch_data, session)

    async def query_attendance(self, session: AsyncSession, **kwargs) -> Dict:
        return await self.query_engine.query_attendance_detail(session, **kwargs)

    async def query_anomalies(self, session: AsyncSession, **kwargs) -> Dict:
        return await self.query_engine.query_anomaly_detail(session, **kwargs)

    async def export_attendance(self, session: AsyncSession, **kwargs) -> str:
        return await self.query_engine.export_attendance_csv(session, **kwargs)

    async def export_anomalies(self, session: AsyncSession, **kwargs) -> str:
        return await self.query_engine.export_anomaly_csv(session, **kwargs)
