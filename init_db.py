#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path
from datetime import date, time as dt_time, timedelta
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))

from attendance_system.config import load_config, get_config
from attendance_system.models import (
    Base, Department, Employee, Shift, Schedule,
    ShiftType, ScheduleStatus
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func


async def main():
    print("=" * 60)
    print("企业考勤智能管理系统 - 数据库初始化")
    print("=" * 60)

    load_config()
    cfg = get_config()
    print(f"数据库: {cfg.database.url}")

    engine_kwargs = {"echo": False}
    db_url = cfg.database.url
    if "sqlite" not in db_url.lower():
        engine_kwargs["pool_size"] = cfg.database.pool_size
        engine_kwargs["max_overflow"] = cfg.database.max_overflow

    engine = create_async_engine(db_url, **engine_kwargs)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✓ 数据库表结构创建完成")

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
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
        else:
            print(f"数据库已有数据: {dept_count} 个部门")
            emps = (await session.execute(select(Employee).limit(5))).scalars().all()
            for e in emps:
                print(f"  - {e.employee_no}: {e.name}")

    await engine.dispose()
    print("\n数据库初始化完成！")


if __name__ == "__main__":
    asyncio.run(main())
