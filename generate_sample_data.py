#!/usr/bin/env python3
import asyncio
import sys
import random
from pathlib import Path
from datetime import datetime, date, time as dt_time, timedelta
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))

from attendance_system.config import load_config, get_config
from attendance_system.models import (
    Base, Employee, Department, Shift, Schedule, PunchRecord,
    AnomalyRecord, MonthlyAttendanceSummary, DashboardMetric,
    PunchSource, PunchType, AnomalyType, AnomalyStatus, ScheduleStatus,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func


async def generate_punch_data(session: AsyncSession, employee: Employee, punch_date: date, shift: Shift):
    is_weekend = punch_date.weekday() >= 5
    if is_weekend:
        return

    base_hour = shift.start_time.hour
    base_minute = shift.start_time.minute
    
    late_minutes = random.choices([0, 0, 0, 0, 1, 3, 5, 8, 12, 20], weights=[40, 20, 10, 10, 5, 5, 3, 3, 2, 2])[0]
    total_in_minutes = base_hour * 60 + base_minute + late_minutes
    clock_in_time = datetime.combine(punch_date, dt_time(total_in_minutes // 60, total_in_minutes % 60))
    
    end_hour = shift.end_time.hour
    end_minute = shift.end_time.minute
    early_minutes = random.choices([0, 0, 0, 0, 0, 2, 5, 10], weights=[50, 20, 10, 10, 5, 2, 2, 1])[0]
    total_end_minutes = end_hour * 60 + end_minute - early_minutes
    clock_out_time = datetime.combine(punch_date, dt_time(total_end_minutes // 60, total_end_minutes % 60))

    punch_in = PunchRecord(
        employee_id=employee.id,
        punch_date=punch_date,
        punch_time=clock_in_time,
        punch_type=PunchType.CLOCK_IN,
        source=PunchSource.ACCESS_CONTROL,
        is_valid=True,
        is_supplementary=False,
    )
    session.add(punch_in)

    punch_out = PunchRecord(
        employee_id=employee.id,
        punch_date=punch_date,
        punch_time=clock_out_time,
        punch_type=PunchType.CLOCK_OUT,
        source=PunchSource.ACCESS_CONTROL,
        is_valid=True,
        is_supplementary=False,
    )
    session.add(punch_out)

    anomalies = []
    if late_minutes >= 5:
        anomalies.append(AnomalyRecord(
            employee_id=employee.id,
            anomaly_date=punch_date,
            anomaly_type=AnomalyType.LATE,
            deviation_minutes=late_minutes,
            status=AnomalyStatus.PENDING,
            description=f"迟到 {late_minutes} 分钟",
        ))
    
    if early_minutes >= 5:
        anomalies.append(AnomalyRecord(
            employee_id=employee.id,
            anomaly_date=punch_date,
            anomaly_type=AnomalyType.EARLY_LEAVE,
            deviation_minutes=early_minutes,
            status=AnomalyStatus.PENDING,
            description=f"早退 {early_minutes} 分钟",
        ))

    for anomaly in anomalies:
        session.add(anomaly)


async def generate_dashboard_metric(session: AsyncSession, metric_date: date, dept: Department, employees: list):
    total = len(employees)
    present = int(total * random.uniform(0.85, 0.98))
    rate = present / max(total, 1)
    
    anomalies = random.randint(0, max(1, int(total * 0.15)))
    late = random.randint(0, anomalies)
    early_leave = anomalies - late
    
    metric = DashboardMetric(
        department_id=dept.id,
        metric_date=metric_date,
        total_employees=total,
        present_employees=present,
        attendance_rate=Decimal(str(rate)),
        no_punch_count=random.randint(0, 3),
        anomaly_count=anomalies,
        late_count=late,
        early_leave_count=early_leave,
    )
    session.add(metric)


async def main():
    print("=" * 60)
    print("生成示例打卡和异常数据")
    print("=" * 60)

    load_config()
    cfg = get_config()

    engine = create_async_engine(cfg.database.url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        stmt = select(Department)
        depts = (await session.execute(stmt)).scalars().all()
        print(f"部门数量: {len(depts)}")

        stmt = select(Shift)
        shifts = (await session.execute(stmt)).scalars().all()
        default_shift = shifts[2] if len(shifts) > 2 else None
        print(f"班次数量: {len(shifts)}")

        today = date.today()
        
        print("\n开始生成过去30天的打卡数据...")
        for day_offset in range(30):
            punch_date = today - timedelta(days=30 - day_offset)
            
            for dept in depts:
                stmt_emp = select(Employee).where(Employee.department_id == dept.id)
                emps = (await session.execute(stmt_emp)).scalars().all()
                
                for emp in emps:
                    if random.random() < 0.95:
                        await generate_punch_data(session, emp, punch_date, default_shift)
                
                await generate_dashboard_metric(session, punch_date, dept, emps)
            
            if (day_offset + 1) % 5 == 0:
                print(f"  已生成 {day_offset + 1}/30 天的数据")
                await session.commit()

        await session.commit()

    await engine.dispose()
    print("\n✓ 示例数据生成完成！")


if __name__ == "__main__":
    asyncio.run(main())
