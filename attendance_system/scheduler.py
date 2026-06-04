import asyncio
import logging
import random
import math
from datetime import datetime, date, timedelta, time as dt_time
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

from sqlalchemy import select, and_, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Employee, Department, Shift, Schedule, BusinessVolume, Holiday, HolidayType,
    MonthlyAttendanceSummary, SchedulingPlan, ScheduleStatus, ShiftType,
)
from .config import get_config, SystemConfig

logger = logging.getLogger(__name__)


class BusinessVolumeAnalyzer:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_hourly_pattern(self, department_id: int, weeks: int = 12) -> Dict[int, float]:
        end_date = date.today()
        start_date = end_date - timedelta(weeks=weeks)

        stmt = select(
            BusinessVolume.hour,
            func.avg(BusinessVolume.customer_count).label("avg_customers"),
        ).where(
            and_(
                BusinessVolume.department_id == department_id,
                BusinessVolume.record_date >= start_date,
                BusinessVolume.record_date <= end_date,
            )
        ).group_by(BusinessVolume.hour)

        result = await self.session.execute(stmt)
        hourly_pattern = {}
        for row in result:
            hourly_pattern[row.hour] = float(row.avg_customers)

        if not hourly_pattern:
            hourly_pattern = self._default_pattern()
        return hourly_pattern

    async def get_weekday_pattern(self, department_id: int, weeks: int = 12) -> Dict[int, float]:
        end_date = date.today()
        start_date = end_date - timedelta(weeks=weeks)

        stmt = select(
            func.strftime("%w", BusinessVolume.record_date).label("weekday"),
            func.avg(BusinessVolume.customer_count).label("avg_customers"),
        ).where(
            and_(
                BusinessVolume.department_id == department_id,
                BusinessVolume.record_date >= start_date,
                BusinessVolume.record_date <= end_date,
            )
        ).group_by("weekday")

        result = await self.session.execute(stmt)
        weekday_pattern = {}
        for row in result:
            weekday_pattern[int(row.weekday)] = float(row.avg_customers)

        if not weekday_pattern:
            weekday_pattern = {i: 100.0 for i in range(7)}
            weekday_pattern[5] = 150.0
            weekday_pattern[6] = 180.0
        return weekday_pattern

    def _default_pattern(self) -> Dict[int, float]:
        return {
            7: 20, 8: 50, 9: 80, 10: 120, 11: 150,
            12: 180, 13: 160, 14: 130, 15: 100, 16: 110,
            17: 140, 18: 170, 19: 160, 20: 120, 21: 60,
        }

    async def estimate_staff_need(self, department_id: int, customers_per_staff: float = 15.0) -> Dict[int, int]:
        hourly = await self.get_hourly_pattern(department_id)
        staff_need = {}
        for hour, customers in hourly.items():
            staff_need[hour] = max(2, math.ceil(customers / customers_per_staff))
        return staff_need


class SchedulingOptimizer:
    def __init__(self, config: SystemConfig = None):
        self.config = config or get_config()
        self.threshold = self.config.scheduling.optimization_trigger_threshold
        self.bv_weight = self.config.scheduling.business_volume_weight
        self.cost_weight = self.config.scheduling.labor_cost_weight
        self.pref_weight = self.config.scheduling.employee_preference_weight

    async def check_optimization_trigger(self, department_id: int, session: AsyncSession) -> bool:
        current_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        prev_month_date = date.today().replace(day=1) - timedelta(days=1)
        prev_prev_month = (prev_month_date.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

        stmt = select(MonthlyAttendanceSummary.compliance_rate).where(
            and_(
                MonthlyAttendanceSummary.department_id == department_id,
                MonthlyAttendanceSummary.year_month.in_([prev_prev_month, current_month]),
            )
        )
        result = await session.execute(stmt)
        rates = [float(r) for r in result.scalars().all() if r is not None]

        consecutive_below = 0
        for rate in rates:
            if rate < self.threshold:
                consecutive_below += 1
            else:
                consecutive_below = 0

        if consecutive_below >= 2:
            logger.warning(
                "部门 %d 连续 %d 个月工时达标率低于 %.0f%%，触发排班优化",
                department_id, consecutive_below, self.threshold * 100,
            )
            return True
        return False

    async def generate_scheduling_plans(
        self, department_id: int, target_month: date, session: AsyncSession, num_plans: int = 3,
    ) -> List[SchedulingPlan]:
        analyzer = BusinessVolumeAnalyzer(session)
        staff_need = await analyzer.estimate_staff_need(department_id)

        stmt = select(Employee).where(
            and_(Employee.department_id == department_id, Employee.is_active == True)
        )
        result = await session.execute(stmt)
        employees = list(result.scalars().all())

        stmt_shift = select(Shift).where(Shift.is_active == True)
        result_shift = await session.execute(stmt_shift)
        available_shifts = list(result_shift.scalars().all())

        if not employees or not available_shifts:
            logger.warning("部门 %d 无可用员工或班次", department_id)
            return []

        days_in_month = (target_month.replace(month=target_month.month % 12 + 1, day=1) - timedelta(days=1)).day if target_month.month < 12 else 31
        if target_month.month == 12:
            days_in_month = 31

        plans = []
        strategies = ["business_first", "cost_first", "balanced"]

        for i, strategy in enumerate(strategies[:num_plans]):
            plan_data = await self._generate_plan(
                department_id, employees, available_shifts,
                target_month, days_in_month, staff_need, strategy,
                session,
            )

            scores = self._score_plan(plan_data, staff_need, employees, strategy)

            plan = SchedulingPlan(
                department_id=department_id,
                plan_name=f"{target_month.strftime('%Y年%m月')}排班方案-{['业务优先', '成本优先', '均衡方案'][i]}",
                trigger_reason=f"部门连续两个月工时达标率低于{self.threshold * 100:.0f}%",
                plan_data=plan_data,
                score_business=scores["business"],
                score_cost=scores["cost"],
                score_preference=scores["preference"],
                score_total=scores["total"],
                is_recommended=(i == 2),
                status="draft",
            )
            session.add(plan)
            plans.append(plan)

        best_idx = max(range(len(plans)), key=lambda i: plans[i].score_total)
        for i, plan in enumerate(plans):
            plan.is_recommended = (i == best_idx)

        await session.flush()
        logger.info("部门 %d 生成 %d 套排班方案，推荐方案 #%d", department_id, len(plans), best_idx + 1)
        return plans

    async def _generate_plan(
        self, department_id: int, employees: List[Employee],
        shifts: List[Shift], target_month: date, days_in_month: int,
        staff_need: Dict[int, int], strategy: str, session: AsyncSession,
    ) -> Dict:
        schedule_data = {}
        weekly_assignments = defaultdict(lambda: defaultdict(int))
        employee_shift_counts = defaultdict(lambda: defaultdict(int))
        employee_last_shift = {}

        for day in range(1, days_in_month + 1):
            current_date = date(target_month.year, target_month.month, day)
            weekday = current_date.weekday()
            day_key = current_date.isoformat()

            daily_schedule = []
            available_employees = [e for e in employees]

            for shift in shifts:
                shift_hours = self._calculate_shift_hours(shift)
                shift_start_hour = shift.start_time.hour
                shift_end_hour = shift.end_time.hour if not shift.is_cross_day else shift.end_time.hour + 24

                required_staff = max(2, len(employees) // len(shifts))
                if strategy == "business_first":
                    peak_hours = range(shift_start_hour, min(shift_end_hour, 22))
                    avg_need = sum(staff_need.get(h, 3) for h in peak_hours) / max(len(peak_hours), 1)
                    required_staff = max(required_staff, int(avg_need))
                elif strategy == "cost_first":
                    required_staff = max(2, len(employees) // len(shifts) - 1)
                else:
                    peak_hours = range(shift_start_hour, min(shift_end_hour, 22))
                    avg_need = sum(staff_need.get(h, 3) for h in peak_hours) / max(len(peak_hours), 1)
                    required_staff = max(2, int((len(employees) // len(shifts) + avg_need) / 2))

                assigned = []
                for emp in available_employees:
                    if len(assigned) >= required_staff:
                        break

                    if emp.id in employee_last_shift:
                        last_date, last_shift_id = employee_last_shift[emp.id]
                        if (current_date - last_date).days == 0 and last_shift_id == shift.id:
                            continue
                        if (current_date - last_date).days == 1:
                            last_shift_obj = next((s for s in shifts if s.id == last_shift_id), None)
                            if last_shift_obj and last_shift_obj.shift_type == ShiftType.NIGHT and shift.shift_type == ShiftType.MORNING:
                                continue

                    weekly_hours = weekly_assignments[emp.id].get("hours", 0)
                    if weekly_hours + shift_hours > self.config.scheduling.max_weekly_hours:
                        continue

                    shift_count = employee_shift_counts[emp.id].get(shift.shift_type.value, 0)
                    if shift_count >= 6:
                        continue

                    assigned.append(emp.id)

                if len(assigned) < required_staff:
                    for emp in available_employees:
                        if emp.id not in assigned and len(assigned) < required_staff:
                            assigned.append(emp.id)

                for emp_id in assigned:
                    employee_last_shift[emp_id] = (current_date, shift.id)
                    weekly_assignments[emp_id]["hours"] = weekly_assignments[emp_id].get("hours", 0) + shift_hours
                    employee_shift_counts[emp_id][shift.shift_type.value] += 1

                daily_schedule.append({
                    "shift_id": shift.id,
                    "shift_name": shift.name,
                    "shift_type": shift.shift_type.value,
                    "start_time": shift.start_time.isoformat(),
                    "end_time": shift.end_time.isoformat(),
                    "required_staff": required_staff,
                    "assigned_employee_ids": assigned,
                    "assigned_count": len(assigned),
                })

            schedule_data[day_key] = daily_schedule

            if weekday == 6:
                for emp_id in weekly_assignments:
                    weekly_assignments[emp_id] = {}

        return {
            "department_id": department_id,
            "target_month": target_month.strftime("%Y-%m"),
            "strategy": strategy,
            "total_employees": len(employees),
            "total_days": days_in_month,
            "daily_schedules": schedule_data,
        }

    def _calculate_shift_hours(self, shift: Shift) -> float:
        start_mins = shift.start_time.hour * 60 + shift.start_time.minute
        end_mins = shift.end_time.hour * 60 + shift.end_time.minute
        if shift.is_cross_day:
            end_mins += 24 * 60
        total_mins = end_mins - start_mins - shift.rest_minutes
        return max(0, total_mins / 60)

    def _score_plan(
        self, plan_data: Dict, staff_need: Dict[int, int],
        employees: List[Employee], strategy: str,
    ) -> Dict[str, float]:
        daily_schedules = plan_data.get("daily_schedules", {})
        total_days = len(daily_schedules)

        business_score = 0
        coverage_count = 0
        for day_key, day_schedule in daily_schedules.items():
            for shift_info in day_schedule:
                required = shift_info.get("required_staff", 0)
                assigned = shift_info.get("assigned_count", 0)
                if required > 0:
                    coverage_count += 1
                    ratio = min(1.0, assigned / required)
                    business_score += ratio

        business_score = (business_score / max(coverage_count, 1)) * 100

        cost_score = 100
        total_assignments = 0
        for day_schedule in daily_schedules.values():
            for shift_info in day_schedule:
                total_assignments += shift_info.get("assigned_count", 0)

        ideal_assignments = len(employees) * total_days
        if ideal_assignments > 0:
            over_staffing_ratio = total_assignments / ideal_assignments
            if over_staffing_ratio > 1.3:
                cost_score = max(0, 100 - (over_staffing_ratio - 1.0) * 100)
            elif over_staffing_ratio < 0.8:
                cost_score = over_staffing_ratio / 0.8 * 80
            else:
                cost_score = 90 + (1.0 - abs(over_staffing_ratio - 1.0)) * 10

        preference_score = 70 + random.uniform(0, 20)

        total = (
            business_score * self.bv_weight
            + cost_score * self.cost_weight
            + preference_score * self.pref_weight
        )

        return {
            "business": round(business_score, 2),
            "cost": round(cost_score, 2),
            "preference": round(preference_score, 2),
            "total": round(total, 2),
        }

    async def apply_plan(self, plan_id: int, session: AsyncSession) -> int:
        plan = await session.get(SchedulingPlan, plan_id)
        if not plan:
            raise ValueError(f"排班方案不存在: {plan_id}")

        plan_data = plan.plan_data
        daily_schedules = plan_data.get("daily_schedules", {})
        created_count = 0

        for day_key, day_schedule in daily_schedules.items():
            current_date = date.fromisoformat(day_key)
            for shift_info in day_schedule:
                shift_id = shift_info["shift_id"]
                for emp_id in shift_info.get("assigned_employee_ids", []):
                    existing = await session.execute(
                        select(Schedule).where(
                            and_(
                                Schedule.employee_id == emp_id,
                                Schedule.schedule_date == current_date,
                            )
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    schedule = Schedule(
                        employee_id=emp_id,
                        department_id=plan.department_id,
                        shift_id=shift_id,
                        schedule_date=current_date,
                        status=ScheduleStatus.PUBLISHED,
                        note=f"排班优化方案#{plan.id}",
                    )
                    session.add(schedule)
                    created_count += 1

        plan.status = "applied"
        await session.flush()
        logger.info("排班方案 #%d 已应用，创建 %d 条排班记录", plan_id, created_count)
        return created_count


class HolidayManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def batch_import(self, holidays: List[Dict], batch_id: str = None) -> Tuple[int, int]:
        import uuid
        batch_id = batch_id or f"holiday_{uuid.uuid4().hex[:8]}"
        added = 0
        skipped = 0

        for h in holidays:
            holiday_date = h["date"] if isinstance(h["date"], date) else date.fromisoformat(h["date"])

            stmt = select(Holiday).where(Holiday.holiday_date == holiday_date)
            result = await self.session.execute(stmt)
            if result.scalar_one_or_none():
                skipped += 1
                continue

            holiday = Holiday(
                name=h["name"],
                holiday_date=holiday_date,
                holiday_type=HolidayType(h.get("type", "national")),
                is_day_off=h.get("is_day_off", True),
                makeup_work_date=date.fromisoformat(h["makeup_work_date"]) if h.get("makeup_work_date") else None,
                batch_import_id=batch_id,
            )
            self.session.add(holiday)
            added += 1

        await self.session.flush()
        logger.info("节假日批量导入: batch=%s, 新增=%d, 跳过=%d", batch_id, added, skipped)
        return added, skipped

    async def generate_company_calendar(self, year: int) -> List[Dict]:
        stmt = select(Holiday).where(
            and_(
                func.strftime("%Y", Holiday.holiday_date) == str(year),
            )
        ).order_by(Holiday.holiday_date)
        result = await self.session.execute(stmt)
        holidays = list(result.scalars().all())

        calendar = []
        for h in holidays:
            entry = {
                "date": h.holiday_date.isoformat(),
                "name": h.name,
                "type": h.holiday_type.value,
                "is_day_off": h.is_day_off,
                "makeup_work_date": h.makeup_work_date.isoformat() if h.makeup_work_date else None,
            }
            calendar.append(entry)

        logger.info("生成 %d 年公司日历: %d 个节假日", year, len(calendar))
        return calendar

    async def is_holiday(self, check_date: date) -> Optional[Holiday]:
        stmt = select(Holiday).where(Holiday.holiday_date == check_date)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_workday(self, check_date: date) -> bool:
        holiday = await self.is_holiday(check_date)
        if holiday:
            if holiday.is_day_off:
                return False
            return True

        if holiday and holiday.makeup_work_date == check_date:
            return True

        makeup_stmt = select(Holiday).where(Holiday.makeup_work_date == check_date)
        makeup_result = await self.session.execute(makeup_stmt)
        if makeup_result.scalar_one_or_none():
            return True

        return check_date.weekday() < 5
