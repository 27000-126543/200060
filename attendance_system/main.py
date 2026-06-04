import asyncio
import json
from datetime import datetime, date, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .config import load_config
from .core import AttendanceCore
from .scheduler import SchedulingOptimizer, HolidayManager
from .reports import ReportGenerator, DashboardGenerator
from .engine import AttendanceEngine, setup_logging

console = Console()


def get_month_start() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


@click.group()
@click.option("--config", "-c", default=None, help="配置文件路径")
@click.pass_context
def cli(ctx, config):
    ctx.ensure_object(dict)
    cfg = load_config(config)
    ctx.obj["config"] = cfg
    setup_logging(cfg)


@cli.command(name="init", help="初始化系统数据库和示例数据")
@click.pass_context
def init_system(ctx):
    async def _init():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        async with core.get_session() as session:
            from sqlalchemy import select, func
            from .models import Department, Employee, Shift, Schedule, ShiftType, ScheduleStatus
            from datetime import time as dt_time
            from decimal import Decimal

            dept_count = (await session.execute(select(func.count()).select_from(Department))).scalar()
            if dept_count == 0:
                departments = [
                    Department(name="技术研发部", code="TECH"),
                    Department(name="市场营销部", code="MKT"),
                    Department(name="人力资源部", code="HR"),
                    Department(name="财务部", code="FIN"),
                    Department(name="运营管理部", code="OPS"),
                ]
                session.add_all(departments)
                await session.flush()

                shift_defs = [
                    ("早班", ShiftType.MORNING, dt_time(8, 0), dt_time(16, 0), 60, 5, False),
                    ("晚班", ShiftType.AFTERNOON, dt_time(13, 0), dt_time(21, 0), 60, 5, False),
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

                emp_idx = 1
                for dept in departments:
                    for j in range(10):
                        emp = Employee(
                            employee_no=f"EMP{emp_idx:04d}",
                            name=f"员工{emp_idx:03d}",
                            department_id=dept.id,
                            phone=f"1380000{emp_idx:04d}",
                            email=f"emp{emp_idx:03d}@company.com",
                            hire_date=date(2024, 1, 15),
                            shift_type=ShiftType.FULL_DAY,
                            hourly_rate=Decimal("50.00"),
                        )
                        session.add(emp)
                        emp_idx += 1
                await session.flush()

                all_emps = (await session.execute(select(Employee))).scalars().all()
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

                await session.flush()
                await session.commit()
                console.print("[green]✓ 示例数据初始化完成[/green]")
                console.print(f"  部门: {len(departments)} 个")
                console.print(f"  班次: {len(shift_objs)} 个")
                console.print(f"  员工: {len(all_emps)} 人")
            else:
                console.print("[yellow]数据库已有数据，跳过初始化[/yellow]")

        await core.shutdown()

    asyncio.run(_init())


@cli.command(name="collect", help="执行每日打卡数据采集")
@click.option("--date", "-d", "date_str", default=None, help="目标日期 (YYYY-MM-DD)")
@click.pass_context
def collect_data(ctx, date_str):
    async def _collect():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        target = date.fromisoformat(date_str) if date_str else date.today()
        with console.status(f"采集 {target} 打卡数据..."):
            await core.daily_data_collection(target)

        console.print(f"[green]✓ 数据采集完成: {target}[/green]")
        await core.shutdown()

    asyncio.run(_collect())


@cli.command(name="detect", help="执行异常检测与通知")
@click.option("--date", "-d", "date_str", default=None, help="目标日期 (YYYY-MM-DD)")
@click.pass_context
def detect_anomalies(ctx, date_str):
    async def _detect():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        target = date.fromisoformat(date_str) if date_str else date.today()
        with console.status(f"检测 {target} 考勤异常..."):
            anomalies = await core.daily_anomaly_detection(target)

        if anomalies:
            table = Table(title=f"异常检测结果 - {target}")
            table.add_column("类型", style="cyan")
            table.add_column("数量", style="red")

            from collections import Counter
            type_counts = Counter(a.anomaly_type.value for a in anomalies)
            type_labels = {
                "late": "迟到", "early_leave": "早退", "missing_punch_in": "上班缺卡",
                "missing_punch_out": "下班缺卡", "absent": "缺勤", "overtime_exceed": "超时加班",
            }
            for atype, count in type_counts.items():
                table.add_row(type_labels.get(atype, atype), str(count))

            console.print(table)
        else:
            console.print(f"[green]✓ {target} 无考勤异常[/green]")

        await core.shutdown()

    asyncio.run(_detect())


@cli.command(name="daily", help="执行每日全量任务（采集+检测+看板+预警）")
@click.option("--date", "-d", "date_str", default=None, help="目标日期 (YYYY-MM-DD)")
@click.pass_context
def daily_job(ctx, date_str):
    async def _daily():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        target = date.fromisoformat(date_str) if date_str else date.today()

        console.print(Panel(f"[bold]每日考勤任务 - {target}[/bold]", style="blue"))

        with console.status("[1/4] 采集打卡数据..."):
            await core.daily_data_collection(target)
        console.print("[green]  ✓ 数据采集完成[/green]")

        with console.status("[2/4] 检测考勤异常..."):
            anomalies = await core.daily_anomaly_detection(target)
        console.print(f"[green]  ✓ 异常检测完成: {len(anomalies)} 条异常[/green]")

        async with core.get_session() as session:
            dashboard_gen = DashboardGenerator(cfg)
            with console.status("[3/4] 生成看板数据..."):
                metrics = await dashboard_gen.generate_daily_metrics(target, session)
                await session.commit()
        console.print(f"[green]  ✓ 看板数据生成完成: {len(metrics)} 个部门[/green]")

        with console.status("[4/4] 检查连续加班预警..."):
            async with core.get_session() as session:
                alerts = await core.overtime_monitor.check_consecutive_overtime(target, session)
                await session.commit()
        console.print(f"[green]  ✓ 加班预警检查完成: {len(alerts)} 条预警[/green]")

        await core.shutdown()
        console.print(Panel("[bold green]每日任务全部完成[/bold green]"))

    asyncio.run(_daily())


@cli.command(name="monthly", help="执行月度统计与报告生成")
@click.option("--month", "-m", default=None, help="目标月份 (YYYY-MM)")
@click.option("--department", "-dept", default=None, type=int, help="部门ID")
@click.option("--format", "-f", "fmt", default="both", type=click.Choice(["pdf", "excel", "both"]), help="报告格式")
@click.pass_context
def monthly_report(ctx, month, department, fmt):
    async def _monthly():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        year_month = month or get_month_start()
        dept_id = department

        console.print(Panel(f"[bold]月度考勤统计 - {year_month}[/bold]", style="blue"))

        with console.status("计算月度统计数据..."):
            async with core.get_session() as session:
                report_gen = ReportGenerator(cfg)
                if fmt in ("excel", "both"):
                    excel_path = await report_gen.generate_excel_report(year_month, session, dept_id)
                    await session.commit()
                    if excel_path:
                        console.print(f"[green]  ✓ Excel报告: {excel_path}[/green]")

        with console.status("生成PDF报告..."):
            async with core.get_session() as session:
                if fmt in ("pdf", "both"):
                    pdf_path = await report_gen.generate_pdf_report(year_month, session, dept_id)
                    await session.commit()
                    if pdf_path:
                        console.print(f"[green]  ✓ PDF报告: {pdf_path}[/green]")

        await core.shutdown()
        console.print(Panel("[bold green]月度报告生成完成[/bold green]"))

    asyncio.run(_monthly())


@cli.command(name="dashboard", help="查看看板数据")
@click.option("--date", "-d", "date_str", default=None, help="目标日期 (YYYY-MM-DD)")
@click.pass_context
def show_dashboard(ctx, date_str):
    async def _dashboard():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        target = date.fromisoformat(date_str) if date_str else date.today()

        async with core.get_session() as session:
            dashboard_gen = DashboardGenerator(cfg)
            data = await dashboard_gen.get_dashboard_data(target, session)

        overview = data["company_overview"]
        console.print(Panel(
            f"[bold]公司出勤概览 - {data['date']}[/bold]\n\n"
            f"  总人数: {overview['total_employees']}  |  "
            f"已到岗: {overview['total_present']}  |  "
            f"出勤率: {overview['overall_attendance_rate']}  |  "
            f"未打卡: {overview['total_no_punch']}  |  "
            f"异常: {overview['total_anomalies']}",
            style="blue",
        ))

        table = Table(title="部门出勤明细")
        table.add_column("部门", style="cyan")
        table.add_column("总人数", justify="right")
        table.add_column("已到岗", justify="right")
        table.add_column("出勤率", justify="right")
        table.add_column("未打卡", justify="right", style="red")
        table.add_column("迟到", justify="right", style="yellow")
        table.add_column("早退", justify="right", style="yellow")
        table.add_column("异常", justify="right", style="red")

        for dept in data["department_details"]:
            table.add_row(
                dept["department_name"],
                str(dept["total_employees"]),
                str(dept["present_employees"]),
                dept["attendance_rate"],
                str(dept["no_punch_count"]),
                str(dept["late_count"]),
                str(dept["early_leave_count"]),
                str(dept["anomaly_count"]),
            )

        console.print(table)
        await core.shutdown()

    asyncio.run(_dashboard())


@cli.command(name="optimize", help="触发排班优化流程")
@click.option("--department", "-dept", required=True, type=int, help="部门ID")
@click.option("--month", "-m", default=None, help="目标月份 (YYYY-MM)")
@click.pass_context
def optimize_schedule(ctx, department, month):
    async def _optimize():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        year_month = month or get_month_start()
        year, m = int(year_month[:4]), int(year_month[5:7])
        target_month = date(year, m, 1)

        async with core.get_session() as session:
            optimizer = SchedulingOptimizer(cfg)

            should_trigger = await optimizer.check_optimization_trigger(department, session)
            if not should_trigger:
                console.print("[yellow]未达到排班优化触发条件（连续两个月工时达标率 < 90%）[/yellow]")
                console.print("[dim]使用 --force 参数可强制生成[/dim]")
                await core.shutdown()
                return

            console.print(Panel(f"[bold]排班优化 - 部门 {department} - {year_month}[/bold]", style="blue"))

            with console.status("生成排班方案..."):
                plans = await optimizer.generate_scheduling_plans(department, target_month, session)
                await session.commit()

        if plans:
            table = Table(title="排班方案对比")
            table.add_column("方案", style="cyan")
            table.add_column("业务匹配", justify="right")
            table.add_column("成本评分", justify="right")
            table.add_column("偏好评分", justify="right")
            table.add_column("综合评分", justify="right", style="bold")
            table.add_column("推荐", justify="center")

            for plan in plans:
                table.add_row(
                    plan.plan_name,
                    f"{plan.score_business:.1f}",
                    f"{plan.score_cost:.1f}",
                    f"{plan.score_preference:.1f}",
                    f"{plan.score_total:.1f}",
                    "⭐" if plan.is_recommended else "",
                )

            console.print(table)
            console.print(f"\n使用 [bold]apply-plan[/bold] 命令应用推荐方案")
        else:
            console.print("[red]未能生成排班方案[/red]")

        await core.shutdown()

    asyncio.run(_optimize())


@cli.command(name="apply-plan", help="应用排班方案")
@click.option("--plan-id", "-p", required=True, type=int, help="排班方案ID")
@click.pass_context
def apply_plan(ctx, plan_id):
    async def _apply():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        async with core.get_session() as session:
            optimizer = SchedulingOptimizer(cfg)
            count = await optimizer.apply_plan(plan_id, session)
            await session.commit()
            console.print(f"[green]✓ 排班方案已应用，创建 {count} 条排班记录[/green]")

        await core.shutdown()

    asyncio.run(_apply())


@cli.command(name="import-holidays", help="批量导入节假日模板")
@click.option("--file", "-f", "filepath", required=True, help="节假日JSON文件路径")
@click.pass_context
def import_holidays(ctx, filepath):
    async def _import():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()

        with open(filepath, "r", encoding="utf-8") as f:
            holidays = json.load(f)

        async with core.get_session() as session:
            async with session.begin():
                manager = HolidayManager(session)
                added, skipped = await manager.batch_import(holidays)

        console.print(f"[green]✓ 节假日导入完成: 新增 {added} 个, 跳过 {skipped} 个[/green]")
        await core.shutdown()

    asyncio.run(_import())


@cli.command(name="export", help="导出考勤或异常明细")
@click.option("--type", "-t", "export_type", default="attendance", type=click.Choice(["attendance", "anomaly"]), help="导出类型")
@click.option("--employee", "-e", default=None, type=int, help="员工ID")
@click.option("--department", "-dept", default=None, type=int, help="部门ID")
@click.option("--start", "-s", "start_date_str", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end", "-nd", "end_date_str", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option("--output", "-o", default=None, help="输出文件路径")
@click.pass_context
def export_data(ctx, export_type, employee, department, start_date_str, end_date_str, output):
    async def _export():
        cfg = ctx.obj["config"]
        engine = AttendanceEngine(cfg)
        core = AttendanceCore(cfg)
        await core.initialize()

        start_date = date.fromisoformat(start_date_str) if start_date_str else None
        end_date = date.fromisoformat(end_date_str) if end_date_str else None

        async with core.get_session() as session:
            if export_type == "attendance":
                path = await engine.export_attendance(
                    session, employee_id=employee, department_id=department,
                    start_date=start_date, end_date=end_date, output_path=output,
                )
            else:
                path = await engine.export_anomalies(
                    session, employee_id=employee, department_id=department,
                    start_date=start_date, end_date=end_date, output_path=output,
                )

        console.print(f"[green]✓ 导出完成: {path}[/green]")
        await core.shutdown()

    asyncio.run(_export())


@cli.command(name="query", help="查询考勤明细")
@click.option("--employee", "-e", default=None, type=int, help="员工ID")
@click.option("--department", "-dept", default=None, type=int, help="部门ID")
@click.option("--start", "-s", "start_date_str", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end", "-nd", "end_date_str", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option("--page", "-p", default=1, type=int, help="页码")
@click.option("--size", "-n", default=20, type=int, help="每页条数")
@click.pass_context
def query_attendance(ctx, employee, department, start_date_str, end_date_str, page, size):
    async def _query():
        cfg = ctx.obj["config"]
        engine = AttendanceEngine(cfg)
        core = AttendanceCore(cfg)
        await core.initialize()

        start_date = date.fromisoformat(start_date_str) if start_date_str else None
        end_date = date.fromisoformat(end_date_str) if end_date_str else None

        async with core.get_session() as session:
            result = await engine.query_attendance(
                session, employee_id=employee, department_id=department,
                start_date=start_date, end_date=end_date, page=page, page_size=size,
            )

        table = Table(title=f"考勤明细 (第{result['page']}/{result['total_pages']}页, 共{result['total']}条)")
        table.add_column("工号", style="cyan")
        table.add_column("姓名")
        table.add_column("部门")
        table.add_column("日期")
        table.add_column("时间")
        table.add_column("类型")
        table.add_column("来源")
        table.add_column("补卡", justify="center")

        for item in result["items"]:
            table.add_row(
                item["employee_no"],
                item["employee_name"],
                item["department"],
                item["punch_date"],
                item["punch_time"],
                "上班" if item["punch_type"] == "clock_in" else "下班",
                item["source"],
                "✓" if item["is_supplementary"] else "",
            )

        console.print(table)
        await core.shutdown()

    asyncio.run(_query())


@cli.command(name="serve", help="启动定时任务服务（守护进程模式）")
@click.option("--collect-time", default="08:30", help="每日数据采集时间 (HH:MM)")
@click.option("--detect-time", default="09:00", help="每日异常检测时间 (HH:MM)")
@click.option("--report-day", default=1, type=int, help="每月报告生成日")
@click.pass_context
def serve(ctx, collect_time, detect_time, report_day):
    async def _serve():
        cfg = ctx.obj["config"]
        core = AttendanceCore(cfg)
        await core.initialize()
        engine = AttendanceEngine(cfg)
        await engine.start()

        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()

        ct_h, ct_m = map(int, collect_time.split(":"))
        dt_h, dt_m = map(int, detect_time.split(":"))

        async def scheduled_collect():
            console.print(f"[dim]{datetime.now()} 执行定时数据采集...[/dim]")
            await core.daily_data_collection()

        async def scheduled_detect():
            console.print(f"[dim]{datetime.now()} 执行定时异常检测...[/dim]")
            await core.daily_anomaly_detection()

        async def scheduled_dashboard():
            console.print(f"[dim]{datetime.now()} 生成看板数据...[/dim]")
            async with core.get_session() as session:
                gen = DashboardGenerator(cfg)
                await gen.generate_daily_metrics(date.today(), session)
                await session.commit()

        async def scheduled_monthly_report():
            today = date.today()
            if today.day == report_day:
                year_month = get_month_start()
                console.print(f"[bold]月度报告生成: {year_month}[/bold]")
                async with core.get_session() as session:
                    gen = ReportGenerator(cfg)
                    await gen.generate_excel_report(year_month, session)
                    await gen.generate_pdf_report(year_month, session)
                    await session.commit()

        scheduler.add_job(scheduled_collect, "cron", hour=ct_h, minute=ct_m, id="daily_collect")
        scheduler.add_job(scheduled_detect, "cron", hour=dt_h, minute=dt_m, id="daily_detect")
        scheduler.add_job(scheduled_dashboard, "cron", hour=dt_h, minute=dt_m + 10, id="daily_dashboard")
        scheduler.add_job(scheduled_monthly_report, "cron", hour=10, minute=0, id="monthly_report")

        scheduler.start()
        console.print(Panel(
            f"[bold green]考勤定时服务已启动[/bold green]\n\n"
            f"  数据采集: 每天 {collect_time}\n"
            f"  异常检测: 每天 {detect_time}\n"
            f"  月度报告: 每月 {report_day} 日 10:00\n\n"
            f"  按 Ctrl+C 停止服务",
            style="green",
        ))

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            console.print("\n[yellow]正在停止服务...[/yellow]")
            scheduler.shutdown()
            await engine.stop()
            await core.shutdown()
            console.print("[green]服务已停止[/green]")

    asyncio.run(_serve())


def main():
    cli()


if __name__ == "__main__":
    main()
