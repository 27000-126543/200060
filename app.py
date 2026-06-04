#!/usr/bin/env python3
"""
企业考勤智能管理系统 - FastAPI 启动入口

启动方式:
    python app.py

或使用 uvicorn:
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload

API文档:
    http://localhost:8000/docs
    http://localhost:8000/redoc
"""

import os
import sys
import asyncio
import argparse
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from attendance_system.config import load_config, get_config
from attendance_system.api import create_app
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import date, time as dt_time, timedelta, datetime
from decimal import Decimal


app = create_app()


async def init_database():
    """初始化数据库结构和示例数据"""
    print("=" * 60)
    print("企业考勤智能管理系统 - 数据库初始化")
    print("=" * 60)

    cfg = get_config()
    print(f"数据库: {cfg.database.url}")

    engine_kwargs = {"echo": False}
    db_url = cfg.database.url
    if "sqlite" not in db_url.lower():
        engine_kwargs["pool_size"] = cfg.database.pool_size
        engine_kwargs["max_overflow"] = cfg.database.max_overflow

    engine = create_async_engine(db_url, **engine_kwargs)

    from attendance_system.models import (
        Base, init_db, Department, Employee, Shift, Schedule, ShiftType, ScheduleStatus,
        PunchRecord, AnomalyRecord, DashboardMetric, PunchSource, PunchType, AnomalyType, AnomalyStatus,
    )
    await init_db(engine)
    print("✓ 数据库表结构创建完成")

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def generate_punch_data(session: AsyncSession, employee: Employee, punch_date: date, shift: Shift):
        is_weekend = punch_date.weekday() >= 5
        if is_weekend:
            return

        base_hour = shift.start_time.hour
        base_minute = shift.start_time.minute
        
        late_minutes = random.choices([0, 0, 0, 0, 1, 3, 5, 8, 12, 20], weights=[40, 20, 10, 10, 5, 5, 3, 3, 2, 2])[0]
        clock_in_time = datetime.combine(punch_date, dt_time(base_hour, base_minute + late_minutes))
        
        end_hour = shift.end_time.hour
        end_minute = shift.end_time.minute
        early_minutes = random.choices([0, 0, 0, 0, 0, 2, 5, 10], weights=[50, 20, 10, 10, 5, 2, 2, 1])[0]
        clock_out_time = datetime.combine(punch_date, dt_time(end_hour, end_minute - early_minutes)) if early_minutes > 0 else datetime.combine(punch_date, dt_time(end_hour, end_minute))

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
        late = random.randint(0, max(1, anomalies))
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

    async with async_session() as session:
        from sqlalchemy import select, func

        dept_count = (await session.execute(select(func.count()).select_from(Department))).scalar()

        if dept_count == 0:
            print("\n开始初始化示例数据...")

            departments = [
                Department(name="技术研发部", code="TECH"),
                Department(name="市场营销部", code="MKT"),
                Department(name="人力资源部", code="HR"),
                Department(name="财务部", code="FIN"),
                Department(name="运营管理部", code="OPS"),
                Department(name="门店运营部", code="STORE"),
            ]
            session.add_all(departments)
            await session.flush()
            print(f"  ✓ 部门: {len(departments)} 个")

            shift_defs = [
                ("早班", ShiftType.MORNING, dt_time(8, 0), dt_time(16, 0), 60, 5, False),
                ("中班", ShiftType.AFTERNOON, dt_time(13, 0), dt_time(21, 0), 60, 5, False),
                ("全天班", ShiftType.FULL_DAY, dt_time(9, 0), dt_time(18, 0), 60, 5, False),
                ("夜班", ShiftType.NIGHT, dt_time(22, 0), dt_time(6, 0), 60, 5, True),
            ]
            shift_objs = []
            for name, st, start, end, rest, grace, cross in shift_defs:
                shift_objs.append(Shift(
                    name=name, shift_type=st,
                    start_time=start, end_time=end,
                    rest_minutes=rest, grace_period_minutes=grace,
                    is_cross_day=cross,
                ))
            session.add_all(shift_objs)
            await session.flush()
            print(f"  ✓ 班次: {len(shift_objs)} 个")

            emp_idx = 1
            for dept in departments:
                for j in range(8):
                    emp = Employee(
                        employee_no=f"EMP{emp_idx:04d}",
                        name=f"{dept.name[:2]}员工{j+1:02d}",
                        department_id=dept.id,
                        position="工程师" if dept.code == "TECH" else "专员",
                        phone=f"138{emp_idx:08d}",
                        email=f"emp{emp_idx:03d}@company.com",
                        wechat_work_id=f"wx_{emp_idx:04d}",
                        hire_date=date(2024, 1, 15),
                        shift_type=ShiftType.FULL_DAY,
                        hourly_rate=Decimal("50.00"),
                    )
                    session.add(emp)
                    emp_idx += 1
            await session.flush()
            print(f"  ✓ 员工: {emp_idx - 1} 人")

            all_emps = (await session.execute(select(Employee))).scalars().all()
            sched_count = 0
            for emp in all_emps:
                for day_offset in range(30):
                    sched_date = date.today() - timedelta(days=30 - day_offset)
                    if sched_date.weekday() >= 5:
                        continue
                    schedule = Schedule(
                        employee_id=emp.id,
                        department_id=emp.department_id,
                        shift_id=shift_objs[2].id,
                        schedule_date=sched_date,
                        status=ScheduleStatus.PUBLISHED,
                    )
                    session.add(schedule)
                    sched_count += 1
            print(f"  ✓ 排班: {sched_count} 条")

            await session.commit()
            print("\n✓ 示例数据初始化完成")

            print("\n开始生成过去30天的打卡、异常和看板数据...")
            stmt = select(Department)
            depts = (await session.execute(stmt)).scalars().all()
            print(f"部门数量: {len(depts)}")

            stmt = select(Shift)
            shifts = (await session.execute(stmt)).scalars().all()
            default_shift = shifts[2] if len(shifts) > 2 else None
            print(f"班次数量: {len(shifts)}")

            today = date.today()
            
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
            print("\n✓ 过去30天打卡、异常和看板数据生成完成！")
        else:
            print("数据库已有数据，跳过初始化")

    await engine.dispose()
    print("\n数据库初始化完成！")


def main():
    parser = argparse.ArgumentParser(description="企业考勤智能管理系统")
    parser.add_argument("--init-db", action="store_true", help="初始化数据库（建表+示例数据）")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="自动重载（开发模式）")

    args = parser.parse_args()

    load_config()

    if args.init_db:
        asyncio.run(init_database())
        return

    print("=" * 60)
    print("企业考勤智能管理系统 v1.0.0")
    print("=" * 60)
    print(f"API 文档: http://{args.host}:{args.port}/docs")
    print(f"Redoc:    http://{args.host}:{args.port}/redoc")
    print(f"默认登录: 工号 EMP0001 / 密码 123456")
    print("=" * 60)

    import uvicorn
    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
