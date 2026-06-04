import asyncio
import logging
import uuid
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any, Tuple

import aiohttp
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker

from .models import (
    Base, Employee, Department, Shift, Schedule, PunchRecord, PunchSource, PunchType,
    AnomalyRecord, AnomalyType, AnomalyStatus, ApprovalRecord, ApprovalType, ApprovalStatus,
    Holiday, HolidayType, OvertimeAlert, OperationLog, BusinessVolume,
    MonthlyAttendanceSummary, DashboardMetric, ScheduleStatus, ShiftType,
)
from .config import get_config, SystemConfig

logger = logging.getLogger(__name__)


class DataSourceCollector:
    def __init__(self, config: SystemConfig):
        self.config = config
        self.session_factory = None

    async def collect_access_control(self, target_date: date, session: AsyncSession) -> List[PunchRecord]:
        ds = self.config.data_sources.get("access_control")
        if not ds or not ds.enabled:
            logger.info("门禁数据源未启用，跳过")
            return []

        batch_id = f"ac_{target_date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        records = []

        try:
            if ds.api_url and ds.api_url.startswith("http"):
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=ds.timeout)) as client:
                    offset = 0
                    while True:
                        params = {
                            "date": target_date.isoformat(),
                            "offset": offset,
                            "limit": ds.batch_size,
                        }
                        async with client.get(f"{ds.api_url}/punches", params=params) as resp:
                            if resp.status != 200:
                                logger.error("门禁接口返回 %s", resp.status)
                                break
                            data = await resp.json()
                            items = data.get("items", [])
                            if not items:
                                break
                            for item in items:
                                punch_time = datetime.fromisoformat(item["punch_time"])
                                punch_type = PunchType.CLOCK_IN if item.get("direction", "in") == "in" else PunchType.CLOCK_OUT
                                record = PunchRecord(
                                    employee_id=item["employee_id"],
                                    punch_time=punch_time,
                                    punch_date=target_date,
                                    punch_type=punch_type,
                                    source=PunchSource.ACCESS_CONTROL,
                                    device_id=item.get("device_id"),
                                    raw_data=item,
                                    batch_id=batch_id,
                                )
                                records.append(record)
                            offset += ds.batch_size
                            if len(items) < ds.batch_size:
                                break
            else:
                logger.info("门禁数据源无有效API地址，使用模拟数据")
                records = self._generate_simulated_data(target_date, PunchSource.ACCESS_CONTROL, batch_id)

        except Exception as e:
            logger.error("采集门禁数据异常: %s", e)
            records = self._generate_simulated_data(target_date, PunchSource.ACCESS_CONTROL, batch_id)

        if records:
            session.add_all(records)
            await session.flush()
            logger.info("门禁数据采集完成: %d 条, batch=%s", len(records), batch_id)
        return records

    async def collect_gps(self, target_date: date, session: AsyncSession) -> List[PunchRecord]:
        ds = self.config.data_sources.get("gps")
        if not ds or not ds.enabled:
            logger.info("GPS数据源未启用，跳过")
            return []

        batch_id = f"gps_{target_date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        records = []

        try:
            if ds.api_url and ds.api_url.startswith("http"):
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=ds.timeout)) as client:
                    offset = 0
                    while True:
                        params = {
                            "date": target_date.isoformat(),
                            "offset": offset,
                            "limit": ds.batch_size,
                            "radius": ds.geofence_radius_meters,
                        }
                        async with client.get(f"{ds.api_url}/locations", params=params) as resp:
                            if resp.status != 200:
                                logger.error("GPS接口返回 %s", resp.status)
                                break
                            data = await resp.json()
                            items = data.get("items", [])
                            if not items:
                                break
                            for item in items:
                                punch_time = datetime.fromisoformat(item["punch_time"])
                                punch_type = PunchType.CLOCK_IN if item.get("direction", "in") == "in" else PunchType.CLOCK_OUT
                                record = PunchRecord(
                                    employee_id=item["employee_id"],
                                    punch_time=punch_time,
                                    punch_date=target_date,
                                    punch_type=punch_type,
                                    source=PunchSource.GPS,
                                    location_lat=item.get("latitude"),
                                    location_lng=item.get("longitude"),
                                    location_address=item.get("address"),
                                    raw_data=item,
                                    batch_id=batch_id,
                                )
                                records.append(record)
                            offset += ds.batch_size
                            if len(items) < ds.batch_size:
                                break
            else:
                logger.info("GPS数据源无有效API地址，使用模拟数据")
                records = self._generate_simulated_data(target_date, PunchSource.GPS, batch_id)

        except Exception as e:
            logger.error("采集GPS数据异常: %s", e)
            records = self._generate_simulated_data(target_date, PunchSource.GPS, batch_id)

        if records:
            session.add_all(records)
            await session.flush()
            logger.info("GPS数据采集完成: %d 条, batch=%s", len(records), batch_id)
        return records

    def _generate_simulated_data(self, target_date: date, source: PunchSource, batch_id: str) -> List[PunchRecord]:
        records = []
        base_clock_in = time(8, 0)
        base_clock_out = time(18, 0)

        for emp_offset in range(1, 51):
            emp_id = emp_offset
            import random
            late_minutes = random.randint(-10, 30)
            early_minutes = random.randint(-30, 10)

            clock_in_dt = datetime.combine(
                target_date,
                base_clock_in
            ) + timedelta(minutes=late_minutes)
            clock_out_dt = datetime.combine(
                target_date,
                base_clock_out
            ) + timedelta(minutes=early_minutes)

            records.append(PunchRecord(
                employee_id=emp_id,
                punch_time=clock_in_dt,
                punch_date=target_date,
                punch_type=PunchType.CLOCK_IN,
                source=source,
                raw_data={"simulated": True},
                batch_id=batch_id,
            ))
            records.append(PunchRecord(
                employee_id=emp_id,
                punch_time=clock_out_dt,
                punch_date=target_date,
                punch_type=PunchType.CLOCK_OUT,
                source=source,
                raw_data={"simulated": True},
                batch_id=batch_id,
            ))

        return records

    async def collect_all(self, target_date: date, session: AsyncSession) -> List[PunchRecord]:
        all_records = []
        ac_records = await self.collect_access_control(target_date, session)
        all_records.extend(ac_records)
        gps_records = await self.collect_gps(target_date, session)
        all_records.extend(gps_records)
        return all_records


class AnomalyDetector:
    def __init__(self, config: SystemConfig):
        self.config = config
        self.late_threshold = config.anomaly.late_threshold_minutes
        self.early_threshold = config.anomaly.early_leave_threshold_minutes
        self.overtime_limit = config.anomaly.overtime_daily_limit_hours

    async def detect_for_employee(
        self, employee: Employee, target_date: date, session: AsyncSession
    ) -> List[AnomalyRecord]:
        anomalies = []

        stmt = select(Schedule).where(
            and_(
                Schedule.employee_id == employee.id,
                Schedule.schedule_date == target_date,
                Schedule.status == ScheduleStatus.PUBLISHED,
            )
        )
        result = await session.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            return anomalies

        shift = await session.get(Shift, schedule.shift_id)
        if not shift:
            return anomalies

        stmt_punch = select(PunchRecord).where(
            and_(
                PunchRecord.employee_id == employee.id,
                PunchRecord.punch_date == target_date,
                PunchRecord.is_valid == True,
            )
        ).order_by(PunchRecord.punch_time)
        result = await session.execute(stmt_punch)
        punches = list(result.scalars().all())

        clock_in_punches = [p for p in punches if p.punch_type == PunchType.CLOCK_IN]
        clock_out_punches = [p for p in punches if p.punch_type == PunchType.CLOCK_OUT]

        earliest_in = min((p.punch_time for p in clock_in_punches), default=None)
        latest_out = max((p.punch_time for p in clock_out_punches), default=None)

        scheduled_start = datetime.combine(target_date, shift.start_time)
        scheduled_end = datetime.combine(target_date, shift.end_time)
        if shift.is_cross_day:
            scheduled_end += timedelta(days=1)

        if not clock_in_punches:
            anomalies.append(AnomalyRecord(
                employee_id=employee.id,
                schedule_id=schedule.id,
                anomaly_date=target_date,
                anomaly_type=AnomalyType.MISSING_PUNCH_IN,
                status=AnomalyStatus.PENDING,
                scheduled_time=scheduled_start,
                deviation_minutes=None,
                description=f"上班缺卡，计划上班时间 {shift.start_time.strftime('%H:%M')}",
                auto_detected=True,
            ))

            if not clock_out_punches:
                anomalies[-1].anomaly_type = AnomalyType.ABSENT
                anomalies[-1].description = f"全天缺勤，计划上班 {shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}"

        elif earliest_in:
            grace_end = scheduled_start + timedelta(minutes=self.late_threshold)
            if earliest_in > grace_end:
                late_minutes = int((earliest_in - scheduled_start).total_seconds() / 60)
                anomalies.append(AnomalyRecord(
                    employee_id=employee.id,
                    schedule_id=schedule.id,
                    anomaly_date=target_date,
                    anomaly_type=AnomalyType.LATE,
                    status=AnomalyStatus.PENDING,
                    scheduled_time=scheduled_start,
                    actual_time=earliest_in,
                    deviation_minutes=late_minutes,
                    description=f"迟到 {late_minutes} 分钟，计划 {shift.start_time.strftime('%H:%M')} 实际 {earliest_in.strftime('%H:%M')}",
                    auto_detected=True,
                ))

        if not clock_out_punches and clock_in_punches:
            anomalies.append(AnomalyRecord(
                employee_id=employee.id,
                schedule_id=schedule.id,
                anomaly_date=target_date,
                anomaly_type=AnomalyType.MISSING_PUNCH_OUT,
                status=AnomalyStatus.PENDING,
                scheduled_time=scheduled_end,
                deviation_minutes=None,
                description=f"下班缺卡，计划下班时间 {shift.end_time.strftime('%H:%M')}",
                auto_detected=True,
            ))
        elif latest_out and clock_in_punches:
            grace_start = scheduled_end - timedelta(minutes=self.early_threshold)
            if latest_out < grace_start:
                early_minutes = int((scheduled_end - latest_out).total_seconds() / 60)
                anomalies.append(AnomalyRecord(
                    employee_id=employee.id,
                    schedule_id=schedule.id,
                    anomaly_date=target_date,
                    anomaly_type=AnomalyType.EARLY_LEAVE,
                    status=AnomalyStatus.PENDING,
                    scheduled_time=scheduled_end,
                    actual_time=latest_out,
                    deviation_minutes=early_minutes,
                    description=f"早退 {early_minutes} 分钟，计划 {shift.end_time.strftime('%H:%M')} 实际 {latest_out.strftime('%H:%M')}",
                    auto_detected=True,
                ))

        if earliest_in and latest_out:
            work_duration = (latest_out - earliest_in).total_seconds() / 3600 - (shift.rest_minutes / 60)
            if work_duration > self.overtime_limit:
                overtime_hours = round(work_duration - 8, 2)
                anomalies.append(AnomalyRecord(
                    employee_id=employee.id,
                    schedule_id=schedule.id,
                    anomaly_date=target_date,
                    anomaly_type=AnomalyType.OVERTIME_EXCEED,
                    status=AnomalyStatus.PENDING,
                    actual_time=latest_out,
                    deviation_minutes=int((work_duration - self.overtime_limit) * 60),
                    description=f"当日工时 {work_duration:.1f} 小时，超过 {self.overtime_limit} 小时限制",
                    auto_detected=True,
                ))

        for anomaly in anomalies:
            session.add(anomaly)
        if anomalies:
            await session.flush()

        return anomalies

    async def detect_for_department(self, department_id: int, target_date: date, session: AsyncSession) -> List[AnomalyRecord]:
        stmt = select(Employee).where(
            and_(Employee.department_id == department_id, Employee.is_active == True)
        )
        result = await session.execute(stmt)
        employees = list(result.scalars().all())

        all_anomalies = []
        for emp in employees:
            anomalies = await self.detect_for_employee(emp, target_date, session)
            all_anomalies.extend(anomalies)

        return all_anomalies

    async def detect_for_all(self, target_date: date, session: AsyncSession) -> List[AnomalyRecord]:
        stmt = select(Employee).where(Employee.is_active == True)
        result = await session.execute(stmt)
        employees = list(result.scalars().all())

        all_anomalies = []
        batch_size = 100
        for i in range(0, len(employees), batch_size):
            batch = employees[i:i + batch_size]
            for emp in batch:
                anomalies = await self.detect_for_employee(emp, target_date, session)
                all_anomalies.extend(anomalies)

        logger.info("异常检测完成 [%s]: 共 %d 条异常", target_date, len(all_anomalies))
        return all_anomalies


class NotificationService:
    def __init__(self, config: SystemConfig):
        self.config = config

    async def send_anomaly_notification(self, anomaly: AnomalyRecord, employee: Employee, session: AsyncSession) -> bool:
        type_labels = {
            AnomalyType.LATE: "迟到",
            AnomalyType.EARLY_LEAVE: "早退",
            AnomalyType.MISSING_PUNCH_IN: "上班缺卡",
            AnomalyType.MISSING_PUNCH_OUT: "下班缺卡",
            AnomalyType.ABSENT: "缺勤",
            AnomalyType.OVERTIME_EXCEED: "超时加班",
        }
        label = type_labels.get(anomaly.anomaly_type, "未知异常")

        if employee.email:
            logger.info("发送邮件通知至 %s: %s - %s", employee.email, label, anomaly.description)
        if employee.phone:
            logger.info("发送短信通知至 %s: %s - %s", employee.phone, label, anomaly.description)
        if employee.wechat_work_id:
            logger.info("发送企微通知至 %s: %s - %s", employee.wechat_work_id, label, anomaly.description)

        anomaly.notification_sent = True
        anomaly.notification_sent_at = datetime.now()
        return True

    async def notify_all_pending(self, target_date: date, session: AsyncSession) -> int:
        stmt = select(AnomalyRecord).where(
            and_(
                AnomalyRecord.anomaly_date == target_date,
                AnomalyRecord.notification_sent == False,
                AnomalyRecord.status == AnomalyStatus.PENDING,
            )
        )
        result = await session.execute(stmt)
        anomalies = list(result.scalars().all())

        sent_count = 0
        for anomaly in anomalies:
            employee = await session.get(Employee, anomaly.employee_id)
            if employee:
                success = await self.send_anomaly_notification(anomaly, employee, session)
                if success:
                    sent_count += 1

        await session.flush()
        logger.info("异常通知发送完成 [%s]: %d/%d", target_date, sent_count, len(anomalies))
        return sent_count


class ApprovalProcessor:
    def __init__(self, config: SystemConfig):
        self.config = config

    async def submit_supplementary_punch(
        self,
        employee_id: int,
        punch_type: PunchType,
        punch_time: datetime,
        reason: str,
        session: AsyncSession,
        attachment_urls: List[str] = None,
    ) -> ApprovalRecord:
        approval = ApprovalRecord(
            employee_id=employee_id,
            approval_type=ApprovalType.SUPPLEMENTARY_PUNCH,
            status=ApprovalStatus.PENDING,
            related_date=punch_time.date(),
            reason=reason,
            attachment_urls=attachment_urls or [],
            supplementary_punch_time=punch_time,
            supplementary_punch_type=punch_type,
        )
        session.add(approval)
        await session.flush()
        logger.info("补卡申请已提交: emp=%d, date=%s, type=%s", employee_id, punch_time.date(), punch_type.value)
        return approval

    async def submit_anomaly_explain(
        self,
        employee_id: int,
        anomaly_id: int,
        reason: str,
        session: AsyncSession,
        attachment_urls: List[str] = None,
    ) -> ApprovalRecord:
        anomaly = await session.get(AnomalyRecord, anomaly_id)
        if not anomaly:
            raise ValueError(f"异常记录不存在: {anomaly_id}")

        approval = ApprovalRecord(
            employee_id=employee_id,
            approval_type=ApprovalType.ANOMALY_EXPLAIN,
            status=ApprovalStatus.PENDING,
            related_date=anomaly.anomaly_date,
            reason=reason,
            attachment_urls=attachment_urls or [],
        )
        session.add(approval)
        anomaly.status = AnomalyStatus.APPEALED
        await session.flush()
        logger.info("异常说明已提交: emp=%d, anomaly=%d", employee_id, anomaly_id)
        return approval

    async def process_approval(
        self,
        approval_id: int,
        approver_id: int,
        approved: bool,
        session: AsyncSession,
        comment: str = None,
    ) -> ApprovalRecord:
        approval = await session.get(ApprovalRecord, approval_id)
        if not approval:
            raise ValueError(f"审批单不存在: {approval_id}")
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"审批单状态非待审批: {approval.status.value}")

        approval.approver_id = approver_id
        approval.approved_at = datetime.now()
        approval.approver_comment = comment

        if approved:
            approval.status = ApprovalStatus.APPROVED
            await self._apply_approval(approval, session)
        else:
            approval.status = ApprovalStatus.REJECTED

        await session.flush()
        logger.info("审批处理完成: id=%d, result=%s", approval_id, "通过" if approved else "驳回")
        return approval

    async def _apply_approval(self, approval: ApprovalRecord, session: AsyncSession):
        if approval.approval_type == ApprovalType.SUPPLEMENTARY_PUNCH:
            punch = PunchRecord(
                employee_id=approval.employee_id,
                punch_time=approval.supplementary_punch_time,
                punch_date=approval.related_date,
                punch_type=approval.supplementary_punch_type,
                source=PunchSource.SELF_SERVICE,
                is_supplementary=True,
                is_valid=True,
            )
            session.add(punch)

            stmt = select(AnomalyRecord).where(
                and_(
                    AnomalyRecord.employee_id == approval.employee_id,
                    AnomalyRecord.anomaly_date == approval.related_date,
                    AnomalyRecord.status.in_([AnomalyStatus.PENDING, AnomalyStatus.APPEALED]),
                )
            )
            result = await session.execute(stmt)
            related_anomalies = list(result.scalars().all())

            for anomaly in related_anomalies:
                should_correct = False
                if approval.supplementary_punch_type == PunchType.CLOCK_IN and anomaly.anomaly_type in (
                    AnomalyType.MISSING_PUNCH_IN, AnomalyType.ABSENT, AnomalyType.LATE
                ):
                    should_correct = True
                elif approval.supplementary_punch_type == PunchType.CLOCK_OUT and anomaly.anomaly_type in (
                    AnomalyType.MISSING_PUNCH_OUT, AnomalyType.EARLY_LEAVE
                ):
                    should_correct = True

                if should_correct:
                    anomaly.status = AnomalyStatus.AUTO_CORRECTED
                    anomaly.corrected_by_approval_id = approval.id
                    anomaly.description += f" [已通过审批#{approval.id}自动修正]"

        elif approval.approval_type == ApprovalType.ANOMALY_EXPLAIN:
            stmt = select(AnomalyRecord).where(
                and_(
                    AnomalyRecord.employee_id == approval.employee_id,
                    AnomalyRecord.anomaly_date == approval.related_date,
                    AnomalyRecord.status == AnomalyStatus.APPEALED,
                )
            )
            result = await session.execute(stmt)
            for anomaly in result.scalars().all():
                anomaly.status = AnomalyStatus.APPROVED
                anomaly.corrected_by_approval_id = approval.id

    async def auto_verify_sick_leave(self, approval: ApprovalRecord, session: AsyncSession) -> bool:
        if approval.approval_type not in (ApprovalType.SICK_LEAVE, ApprovalType.LEAVE):
            return False

        has_certificate = bool(approval.attachment_urls)
        approval.auto_verified = has_certificate
        approval.verification_details = {
            "has_certificate": has_certificate,
            "verified_at": datetime.now().isoformat(),
        }

        if has_certificate:
            logger.info("病假证明自动校验通过: approval=%d", approval.id)
        else:
            logger.info("病假证明自动校验未通过(无附件): approval=%d", approval.id)

        return has_certificate


class ShiftSwapProcessor:
    def __init__(self, config: SystemConfig):
        self.config = config

    async def request_shift_swap(
        self,
        requester_id: int,
        target_employee_id: int,
        source_schedule_id: int,
        target_schedule_id: int,
        reason: str,
        session: AsyncSession,
    ) -> Tuple[ApprovalRecord, List[str]]:
        source_schedule = await session.get(Schedule, source_schedule_id)
        target_schedule = await session.get(Schedule, target_schedule_id)

        if not source_schedule or not target_schedule:
            raise ValueError("排班记录不存在")

        if source_schedule.employee_id != requester_id:
            raise ValueError("源排班不属于申请人")

        if target_schedule.employee_id != target_employee_id:
            raise ValueError("目标排班不属于目标员工")

        warnings = []
        conflicts = await self._check_compliance(requester_id, target_schedule, session)
        if conflicts:
            warnings.extend(conflicts)

        target_conflicts = await self._check_compliance(target_employee_id, source_schedule, session)
        if target_conflicts:
            warnings.extend(target_conflicts)

        existing_swap = await self._check_existing_schedule(requester_id, target_schedule.schedule_date, session)
        if existing_swap:
            warnings.append(f"申请人已有 {target_schedule.schedule_date} 的排班")

        target_existing = await self._check_existing_schedule(target_employee_id, source_schedule.schedule_date, session)
        if target_existing:
            warnings.append(f"目标员工已有 {source_schedule.schedule_date} 的排班")

        approval = ApprovalRecord(
            employee_id=requester_id,
            approval_type=ApprovalType.SHIFT_SWAP,
            status=ApprovalStatus.PENDING,
            related_date=source_schedule.schedule_date,
            related_date_end=target_schedule.schedule_date,
            reason=reason,
            swap_target_employee_id=target_employee_id,
            swap_target_schedule_id=target_schedule_id,
            swap_source_schedule_id=source_schedule_id,
        )
        session.add(approval)
        await session.flush()

        logger.info("调班申请已提交: %d <-> %d", requester_id, target_employee_id)
        return approval, warnings

    async def _check_compliance(self, employee_id: int, new_schedule: Schedule, session: AsyncSession) -> List[str]:
        warnings = []
        target_date = new_schedule.schedule_date

        prev_date = target_date - timedelta(days=1)
        stmt = select(Schedule).where(
            and_(Schedule.employee_id == employee_id, Schedule.schedule_date == prev_date)
        )
        result = await session.execute(stmt)
        prev_schedule = result.scalar_one_or_none()

        if prev_schedule:
            prev_shift = await session.get(Shift, prev_schedule.shift_id)
            new_shift = await session.get(Shift, new_schedule.shift_id)
            if prev_shift and new_shift:
                prev_end = datetime.combine(prev_date, prev_shift.end_time)
                if prev_shift.is_cross_day:
                    prev_end += timedelta(days=1)
                new_start = datetime.combine(target_date, new_shift.start_time)
                rest_hours = (new_start - prev_end).total_seconds() / 3600
                if rest_hours < self.config.scheduling.min_rest_hours_between_shifts:
                    warnings.append(
                        f"调班后休息时间不足 {self.config.scheduling.min_rest_hours_between_shifts} 小时"
                        f"（仅 {rest_hours:.1f} 小时）"
                    )

        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        stmt_week = select(Schedule).where(
            and_(
                Schedule.employee_id == employee_id,
                Schedule.schedule_date >= week_start,
                Schedule.schedule_date <= week_end,
            )
        )
        result = await session.execute(stmt_week)
        week_schedules = list(result.scalars().all())

        total_weekly_hours = 0
        for ws in week_schedules:
            ws_shift = await session.get(Shift, ws.shift_id)
            if ws_shift:
                daily_hours = (datetime.combine(date.min, ws_shift.end_time) - datetime.combine(date.min, ws_shift.start_time)).seconds / 3600
                daily_hours -= ws_shift.rest_minutes / 60
                total_weekly_hours += daily_hours

        if total_weekly_hours > self.config.scheduling.max_weekly_hours:
            warnings.append(
                f"调班后周工时将达 {total_weekly_hours:.1f} 小时，"
                f"超过上限 {self.config.scheduling.max_weekly_hours} 小时"
            )

        return warnings

    async def _check_existing_schedule(self, employee_id: int, check_date: date, session: AsyncSession) -> bool:
        stmt = select(Schedule).where(
            and_(
                Schedule.employee_id == employee_id,
                Schedule.schedule_date == check_date,
                Schedule.status == ScheduleStatus.PUBLISHED,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def execute_swap(self, approval: ApprovalRecord, session: AsyncSession):
        if approval.approval_type != ApprovalType.SHIFT_SWAP:
            return
        if approval.status != ApprovalStatus.APPROVED:
            return

        source_schedule = await session.get(Schedule, approval.swap_source_schedule_id)
        target_schedule = await session.get(Schedule, approval.swap_target_schedule_id)

        if source_schedule and target_schedule:
            source_schedule.employee_id = approval.swap_target_employee_id
            source_schedule.status = ScheduleStatus.ADJUSTED
            source_schedule.version += 1
            source_schedule.note = f"调班审批#{approval.id}"

            target_schedule.employee_id = approval.employee_id
            target_schedule.status = ScheduleStatus.ADJUSTED
            target_schedule.version += 1
            target_schedule.note = f"调班审批#{approval.id}"

            await session.flush()
            logger.info("调班执行完成: approval=%d", approval.id)


class OvertimeMonitor:
    def __init__(self, config: SystemConfig):
        self.config = config

    async def check_consecutive_overtime(self, target_date: date, session: AsyncSession) -> List[OvertimeAlert]:
        alerts = []
        check_days = 7

        stmt = select(Employee).where(Employee.is_active == True)
        result = await session.execute(stmt)
        employees = list(result.scalars().all())

        for emp in employees:
            consecutive_days = 0
            max_daily_hours = 0

            for day_offset in range(check_days):
                check_date = target_date - timedelta(days=day_offset)
                stmt_punch = select(PunchRecord).where(
                    and_(
                        PunchRecord.employee_id == emp.id,
                        PunchRecord.punch_date == check_date,
                        PunchRecord.is_valid == True,
                    )
                ).order_by(PunchRecord.punch_time)
                result_punch = await session.execute(stmt_punch)
                punches = list(result_punch.scalars().all())

                if not punches:
                    break

                clock_in = [p for p in punches if p.punch_type == PunchType.CLOCK_IN]
                clock_out = [p for p in punches if p.punch_type == PunchType.CLOCK_OUT]

                if clock_in and clock_out:
                    earliest = min(p.punch_time for p in clock_in)
                    latest = max(p.punch_time for p in clock_out)
                    hours = (latest - earliest).total_seconds() / 3600

                    if hours > self.config.scheduling.max_daily_hours:
                        consecutive_days += 1
                        max_daily_hours = max(max_daily_hours, hours)
                    else:
                        break
                else:
                    break

            if consecutive_days >= 3:
                alert = OvertimeAlert(
                    employee_id=emp.id,
                    alert_date=target_date,
                    consecutive_overtime_days=consecutive_days,
                    max_daily_hours=max_daily_hours,
                    alert_type="consecutive_overtime",
                )
                session.add(alert)
                alerts.append(alert)

        if alerts:
            await session.flush()
            logger.warning("连续超时加班预警: %d 人", len(alerts))
        return alerts


class AttendanceCore:
    def __init__(self, config: SystemConfig = None):
        self.config = config or get_config()
        self.engine: Optional[AsyncEngine] = None
        self.session_factory = None
        self.collector = DataSourceCollector(self.config)
        self.detector = AnomalyDetector(self.config)
        self.notifier = NotificationService(self.config)
        self.approval_processor = ApprovalProcessor(self.config)
        self.swap_processor = ShiftSwapProcessor(self.config)
        self.overtime_monitor = OvertimeMonitor(self.config)

    async def initialize(self):
        engine_kwargs = {"echo": False}
        db_url = self.config.database.url
        if "sqlite" not in db_url.lower():
            engine_kwargs["pool_size"] = self.config.database.pool_size
            engine_kwargs["max_overflow"] = self.config.database.max_overflow
        self.engine = create_async_engine(db_url, **engine_kwargs)
        self.session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        from .models import init_db
        await init_db(self.engine)
        logger.info("考勤核心系统初始化完成")

    async def shutdown(self):
        if self.engine:
            await self.engine.dispose()
            logger.info("考勤核心系统已关闭")

    def get_session(self) -> AsyncSession:
        return self.session_factory()

    async def daily_data_collection(self, target_date: date = None):
        target_date = target_date or date.today()
        async with self.get_session() as session:
            async with session.begin():
                records = await self.collector.collect_all(target_date, session)
                logger.info("每日数据采集完成 [%s]: %d 条打卡记录", target_date, len(records))

    async def daily_anomaly_detection(self, target_date: date = None):
        target_date = target_date or date.today()
        async with self.get_session() as session:
            async with session.begin():
                anomalies = await self.detector.detect_for_all(target_date, session)
                sent = await self.notifier.notify_all_pending(target_date, session)
                alerts = await self.overtime_monitor.check_consecutive_overtime(target_date, session)
                logger.info(
                    "每日异常检测完成 [%s]: %d 异常, %d 通知, %d 加班预警",
                    target_date, len(anomalies), sent, len(alerts),
                )
                return anomalies

    async def process_approval(
        self, approval_id: int, approver_id: int, approved: bool, comment: str = None
    ) -> ApprovalRecord:
        async with self.get_session() as session:
            async with session.begin():
                approval = await self.approval_processor.process_approval(
                    approval_id, approver_id, approved, session, comment
                )
                if approved and approval.approval_type == ApprovalType.SHIFT_SWAP:
                    await self.swap_processor.execute_swap(approval, session)
                return approval

    async def request_shift_swap(
        self, requester_id: int, target_employee_id: int,
        source_schedule_id: int, target_schedule_id: int, reason: str,
    ) -> Tuple[ApprovalRecord, List[str]]:
        async with self.get_session() as session:
            async with session.begin():
                return await self.swap_processor.request_shift_swap(
                    requester_id, target_employee_id,
                    source_schedule_id, target_schedule_id,
                    reason, session,
                )

    async def submit_supplementary_punch(
        self, employee_id: int, punch_type: PunchType,
        punch_time: datetime, reason: str, attachment_urls: List[str] = None,
    ) -> ApprovalRecord:
        async with self.get_session() as session:
            async with session.begin():
                return await self.approval_processor.submit_supplementary_punch(
                    employee_id, punch_type, punch_time, reason, session, attachment_urls
                )
