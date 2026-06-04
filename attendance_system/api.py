import os
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, and_, func, or_

from .config import load_config, get_config, SystemConfig
from .models import (
    Base, Employee, Department, Shift, Schedule, PunchRecord, AnomalyRecord,
    ApprovalRecord, MonthlyAttendanceSummary, DashboardMetric,
    SchedulingPlan, Holiday, PunchSource, PunchType, AnomalyType,
    AnomalyStatus, ApprovalType, ApprovalStatus, ScheduleStatus,
)
from .reports import ReportGenerator, DashboardGenerator
from .scheduler import SchedulingOptimizer, HolidayManager
from .engine import AttendanceEngine


SECRET_KEY = os.getenv("SECRET_KEY", "attendance-system-secret-key-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480


class Token(BaseModel):
    access_token: str
    token_type: str
    employee_id: int
    name: str
    role: str
    department_id: int


class TokenData(BaseModel):
    employee_id: Optional[int] = None


class ApprovalRequest(BaseModel):
    approval_type: str
    related_date: str
    reason: str
    attachment_urls: List[str] = []
    supplementary_punch_time: Optional[str] = None
    supplementary_punch_type: Optional[str] = None


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

async def get_token(
    token: Optional[str] = Depends(oauth2_scheme),
    token_query: Optional[str] = None
):
    return token or token_query

_config = None
_engine = None
_session_factory = None


def get_config_cached():
    global _config
    if _config is None:
        _config = load_config()
    return _config


async def get_db_engine():
    global _engine, _session_factory
    if _engine is None:
        cfg = get_config_cached()
        db_url = cfg.database.url
        engine_kwargs = {"echo": False}
        if "sqlite" not in db_url.lower():
            engine_kwargs["pool_size"] = cfg.database.pool_size
            engine_kwargs["max_overflow"] = cfg.database.max_overflow

        _engine = create_async_engine(db_url, **engine_kwargs)
        _session_factory = sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _engine, _session_factory


async def get_session():
    _, session_factory = await get_db_engine()
    async with session_factory() as session:
        yield session


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: Optional[str] = Depends(get_token),
    db: AsyncSession = Depends(get_session)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        employee_id_str = payload.get("sub")
        if employee_id_str is None:
            raise credentials_exception
        employee_id: int = int(employee_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    stmt = select(Employee).where(Employee.id == employee_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


def create_app():
    cfg = get_config_cached()
    app = FastAPI(title="企业考勤智能管理系统 API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup():
        engine, _ = await get_db_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    class LoginRequest(BaseModel):
        username: str
        password: str

    @app.post("/api/auth/login", response_model=Token)
    async def login(
        request: Request,
        db: AsyncSession = Depends(get_session)
    ):
        username = ""
        password = ""
        
        try:
            body = await request.json()
            username = body.get("username", "")
            password = body.get("password", "")
        except Exception:
            pass

        if not username or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请提供用户名和密码",
            )

        stmt = select(Employee).where(Employee.employee_no == username)
        result = await db.execute(stmt)
        employee = result.scalar_one_or_none()

        if not employee:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="工号或密码错误",
            )

        if password != "123456":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="工号或密码错误",
            )

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        role = "admin" if username in ("ADMIN001", "EMP0001", "admin") else "employee"

        access_token = create_access_token(
            data={"sub": str(employee.id), "role": role},
            expires_delta=access_token_expires,
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "employee_id": employee.id,
            "name": employee.name,
            "role": role,
            "department_id": employee.department_id,
        }

    @app.get("/api/auth/me")
    async def get_current_user_info(
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        dept_stmt = select(Department).where(Department.id == current_user.department_id)
        dept_result = await db.execute(dept_stmt)
        dept = dept_result.scalar_one_or_none()

        role = "admin" if current_user.employee_no in ("ADMIN001", "EMP0001", "admin") else "employee"

        return {
            "id": current_user.id,
            "employee_no": current_user.employee_no,
            "name": current_user.name,
            "department_id": current_user.department_id,
            "department_name": dept.name if dept else "",
            "position": current_user.position,
            "email": current_user.email,
            "phone": current_user.phone,
            "role": role,
        }

    @app.get("/api/employee/dashboard")
    async def get_employee_dashboard(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        today = date.today()
        start = date.fromisoformat(start_date) if start_date else today - timedelta(days=30)
        end = date.fromisoformat(end_date) if end_date else today

        punch_count_stmt = select(func.count()).where(
            and_(
                PunchRecord.employee_id == current_user.id,
                PunchRecord.punch_date >= start,
                PunchRecord.punch_date <= end,
                PunchRecord.is_valid == True,
            )
        )
        punch_count = (await db.execute(punch_count_stmt)).scalar() or 0

        anomaly_count_stmt = select(func.count()).where(
            and_(
                AnomalyRecord.employee_id == current_user.id,
                AnomalyRecord.anomaly_date >= start,
                AnomalyRecord.anomaly_date <= end,
            )
        )
        anomaly_count = (await db.execute(anomaly_count_stmt)).scalar() or 0

        pending_anomaly_stmt = select(func.count()).where(
            and_(
                AnomalyRecord.employee_id == current_user.id,
                AnomalyRecord.status == AnomalyStatus.PENDING,
            )
        )
        pending_anomalies = (await db.execute(pending_anomaly_stmt)).scalar() or 0

        pending_approval_stmt = select(func.count()).where(
            and_(
                ApprovalRecord.employee_id == current_user.id,
                ApprovalRecord.status == ApprovalStatus.PENDING,
            )
        )
        pending_approvals = (await db.execute(pending_approval_stmt)).scalar() or 0

        anomaly_types = {
            AnomalyType.LATE: 0,
            AnomalyType.EARLY_LEAVE: 0,
            AnomalyType.MISSING_PUNCH_IN: 0,
            AnomalyType.MISSING_PUNCH_OUT: 0,
            AnomalyType.ABSENT: 0,
        }
        anomaly_stmt = select(AnomalyRecord.anomaly_type, func.count()).where(
            and_(
                AnomalyRecord.employee_id == current_user.id,
                AnomalyRecord.anomaly_date >= start,
                AnomalyRecord.anomaly_date <= end,
            )
        ).group_by(AnomalyRecord.anomaly_type)
        anomaly_result = await db.execute(anomaly_stmt)
        for atype, cnt in anomaly_result.all():
            anomaly_types[atype] = cnt

        type_labels = {
            AnomalyType.LATE: "迟到",
            AnomalyType.EARLY_LEAVE: "早退",
            AnomalyType.MISSING_PUNCH_IN: "上班缺卡",
            AnomalyType.MISSING_PUNCH_OUT: "下班缺卡",
            AnomalyType.ABSENT: "缺勤",
        }
        anomaly_distribution = [
            {"type": type_labels.get(k, k.value), "count": v}
            for k, v in anomaly_types.items() if v > 0
        ]

        return {
            "period": f"{start} 至 {end}",
            "punch_count": punch_count,
            "anomaly_count": anomaly_count,
            "pending_anomalies": pending_anomalies,
            "pending_approvals": pending_approvals,
            "anomaly_distribution": anomaly_distribution,
        }

    @app.get("/api/employee/punches")
    async def get_employee_punches(
        page: int = 1,
        page_size: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        today = date.today()
        start = date.fromisoformat(start_date) if start_date else today - timedelta(days=30)
        end = date.fromisoformat(end_date) if end_date else today

        conditions = [
            PunchRecord.employee_id == current_user.id,
            PunchRecord.is_valid == True,
            PunchRecord.punch_date >= start,
            PunchRecord.punch_date <= end,
        ]

        count_stmt = select(func.count()).select_from(PunchRecord).where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(PunchRecord).where(and_(*conditions)).order_by(
            PunchRecord.punch_date.desc(), PunchRecord.punch_time
        ).offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        punches = list(result.scalars().all())

        type_labels = {"clock_in": "上班", "clock_out": "下班"}
        source_labels = {"access_control": "门禁", "gps": "GPS", "wifi": "WiFi", "self_service": "自助补卡"}

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [
                {
                    "id": p.id,
                    "punch_date": p.punch_date.isoformat(),
                    "punch_time": p.punch_time.strftime("%H:%M:%S"),
                    "punch_type": type_labels.get(p.punch_type.value, p.punch_type.value),
                    "punch_type_code": p.punch_type.value,
                    "source": source_labels.get(p.source.value, p.source.value),
                    "source_code": p.source.value,
                    "is_supplementary": p.is_supplementary,
                }
                for p in punches
            ],
        }

    @app.get("/api/employee/anomalies")
    async def get_employee_anomalies(
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        conditions = [AnomalyRecord.employee_id == current_user.id]
        if status:
            conditions.append(AnomalyRecord.status == AnomalyStatus(status))

        count_stmt = select(func.count()).select_from(AnomalyRecord).where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(AnomalyRecord).where(and_(*conditions)).order_by(
            AnomalyRecord.anomaly_date.desc()
        ).offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        anomalies = list(result.scalars().all())

        type_labels = {
            "late": "迟到", "early_leave": "早退", "missing_punch_in": "上班缺卡",
            "missing_punch_out": "下班缺卡", "absent": "缺勤", "overtime_exceed": "超时加班",
        }
        status_labels = {
            "pending": "待确认", "confirmed": "已确认", "appealed": "已申诉",
            "approved": "已通过", "rejected": "已驳回", "auto_corrected": "已自动修正",
        }

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [
                {
                    "id": a.id,
                    "anomaly_date": a.anomaly_date.isoformat(),
                    "anomaly_type": a.anomaly_type.value,
                    "anomaly_type_label": type_labels.get(a.anomaly_type.value, a.anomaly_type.value),
                    "status": a.status.value,
                    "status_label": status_labels.get(a.status.value, a.status.value),
                    "deviation_minutes": a.deviation_minutes,
                    "description": a.description,
                }
                for a in anomalies
            ],
        }

    @app.get("/api/employee/approvals")
    async def get_employee_approvals(
        page: int = 1,
        page_size: int = 20,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        conditions = [ApprovalRecord.employee_id == current_user.id]

        count_stmt = select(func.count()).select_from(ApprovalRecord).where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(ApprovalRecord).where(and_(*conditions)).order_by(
            ApprovalRecord.created_at.desc()
        ).offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        approvals = list(result.scalars().all())

        type_labels = {
            "supplementary_punch": "补卡申请", "leave": "请假", "sick_leave": "病假",
            "business_trip": "出差", "shift_swap": "调班申请", "overtime_apply": "加班申请",
            "anomaly_explain": "异常说明",
        }
        status_labels = {
            "pending": "审批中", "approved": "已通过", "rejected": "已驳回", "cancelled": "已取消",
        }

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [
                {
                    "id": a.id,
                    "approval_type": a.approval_type.value,
                    "approval_type_label": type_labels.get(a.approval_type.value, a.approval_type.value),
                    "status": a.status.value,
                    "status_label": status_labels.get(a.status.value, a.status.value),
                    "related_date": a.related_date.isoformat(),
                    "reason": a.reason or "",
                    "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                }
                for a in approvals
            ],
        }

    @app.post("/api/employee/approvals")
    async def submit_approval(
        req: ApprovalRequest,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        approval_type = ApprovalType(req.approval_type)
        related_date = date.fromisoformat(req.related_date)

        approval = ApprovalRecord(
            employee_id=current_user.id,
            approval_type=approval_type,
            status=ApprovalStatus.PENDING,
            related_date=related_date,
            reason=req.reason,
            attachment_urls=req.attachment_urls,
        )

        if req.supplementary_punch_time:
            approval.supplementary_punch_time = datetime.fromisoformat(req.supplementary_punch_time)
        if req.supplementary_punch_type:
            approval.supplementary_punch_type = PunchType(req.supplementary_punch_type)

        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        if approval_type == ApprovalType.ANOMALY_EXPLAIN:
            anomaly_stmt = select(AnomalyRecord).where(
                and_(
                    AnomalyRecord.employee_id == current_user.id,
                    AnomalyRecord.anomaly_date == related_date,
                    AnomalyRecord.status == AnomalyStatus.PENDING,
                )
            )
            anomaly_result = await db.execute(anomaly_stmt)
            for anomaly in anomaly_result.scalars().all():
                anomaly.status = AnomalyStatus.APPEALED
            await db.commit()

        return {"success": True, "approval_id": approval.id}

    @app.get("/api/employee/monthly-summary")
    async def get_employee_monthly_summary(
        year_month: Optional[str] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        ym = year_month or date.today().strftime("%Y-%m")

        stmt = select(MonthlyAttendanceSummary).where(
            and_(
                MonthlyAttendanceSummary.employee_id == current_user.id,
                MonthlyAttendanceSummary.year_month == ym,
            )
        )
        result = await db.execute(stmt)
        summary = result.scalar_one_or_none()

        if not summary:
            from .reports import MonthlyCalculator
            calc = MonthlyCalculator(get_config_cached())
            summary = await calc.calculate_employee_summary(current_user.id, ym, db)

        return {
            "year_month": ym,
            "total_work_days": summary.total_work_days,
            "actual_work_days": summary.actual_work_days,
            "late_count": summary.late_count,
            "early_leave_count": summary.early_leave_count,
            "absent_count": summary.absent_count,
            "missing_punch_count": summary.missing_punch_count,
            "total_work_hours": float(summary.total_work_hours),
            "overtime_hours_weekday": float(summary.overtime_hours_weekday),
            "overtime_hours_weekend": float(summary.overtime_hours_weekend),
            "overtime_hours_holiday": float(summary.overtime_hours_holiday),
            "salary_deduction": float(summary.salary_deduction),
            "overtime_allowance": float(summary.overtime_allowance),
            "net_adjustment": float(summary.net_adjustment),
            "compliance_rate": f"{float(summary.compliance_rate) * 100:.1f}%",
        }

    @app.get("/api/admin/dashboard-overview")
    async def get_admin_dashboard_overview(
        dashboard_date: Optional[str] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        today = date.fromisoformat(dashboard_date) if dashboard_date else date.today()

        stmt = select(DashboardMetric).where(DashboardMetric.metric_date == today)
        result = await db.execute(stmt)
        metrics = list(result.scalars().all())

        if not metrics:
            generator = DashboardGenerator(get_config_cached())
            metrics = await generator.generate_daily_metrics(today, db)
            await db.commit()

        total_employees = sum(m.total_employees for m in metrics)
        total_present = sum(m.present_employees for m in metrics)
        overall_rate = round(total_present / max(total_employees, 1), 4)

        return {
            "date": today.isoformat(),
            "total_employees": total_employees,
            "present_employees": total_present,
            "overall_attendance_rate": f"{overall_rate * 100:.1f}%",
            "overall_attendance_rate_value": overall_rate,
            "no_punch_count": sum(m.no_punch_count for m in metrics),
            "anomaly_count": sum(m.anomaly_count for m in metrics),
            "late_count": sum(m.late_count for m in metrics),
            "early_leave_count": sum(m.early_leave_count for m in metrics),
            "overtime_employees": sum(getattr(m, "overtime_employees", 0) for m in metrics),
        }

    @app.get("/api/admin/departments-dashboard")
    async def get_departments_dashboard(
        dashboard_date: Optional[str] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        today = date.fromisoformat(dashboard_date) if dashboard_date else date.today()

        stmt = select(DashboardMetric, Department).join(
            Department, DashboardMetric.department_id == Department.id
        ).where(DashboardMetric.metric_date == today)
        result = await db.execute(stmt)
        rows = result.all()

        items = []
        for metric, dept in rows:
            items.append({
                "department_id": dept.id,
                "department_name": dept.name,
                "total_employees": metric.total_employees,
                "present_employees": metric.present_employees,
                "attendance_rate": f"{float(metric.attendance_rate) * 100:.1f}%",
                "attendance_rate_value": float(metric.attendance_rate),
                "no_punch_count": metric.no_punch_count,
                "anomaly_count": metric.anomaly_count,
                "late_count": metric.late_count,
                "early_leave_count": metric.early_leave_count,
            })

        items.sort(key=lambda x: x["attendance_rate_value"], reverse=True)
        return items

    @app.get("/api/admin/attendance-trend")
    async def get_attendance_trend(
        days: int = 7,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        stmt = select(DashboardMetric).where(
            and_(
                DashboardMetric.metric_date >= start_date,
                DashboardMetric.metric_date <= end_date,
            )
        )
        result = await db.execute(stmt)
        metrics = list(result.scalars().all())

        from collections import defaultdict
        daily_stats = defaultdict(lambda: {"total": 0, "present": 0, "late": 0, "early": 0})
        for m in metrics:
            daily_stats[m.metric_date.isoformat()]["total"] += m.total_employees
            daily_stats[m.metric_date.isoformat()]["present"] += m.present_employees
            daily_stats[m.metric_date.isoformat()]["late"] += m.late_count
            daily_stats[m.metric_date.isoformat()]["early"] += m.early_leave_count

        trend = []
        for i in range(days):
            d = start_date + timedelta(days=i)
            ds = daily_stats.get(d.isoformat(), {"total": 0, "present": 0, "late": 0, "early": 0})
            rate = ds["present"] / max(ds["total"], 1)
            trend.append({
                "date": d.isoformat(),
                "attendance_rate": round(rate, 4),
                "attendance_rate_display": f"{rate * 100:.1f}%",
                "late_count": ds["late"],
                "early_leave_count": ds["early"],
            })

        return trend

    @app.get("/api/admin/monthly-reports")
    async def get_monthly_reports(
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        stmt = select(MonthlyAttendanceSummary.year_month, func.count()).group_by(
            MonthlyAttendanceSummary.year_month
        ).order_by(MonthlyAttendanceSummary.year_month.desc()).limit(12)
        result = await db.execute(stmt)
        reports = []
        for ym, count in result.all():
            year, month = ym.split("-")
            reports.append({
                "year_month": ym,
                "month_label": f"{year}年{int(month)}月",
                "employee_count": count,
            })
        return reports

    @app.post("/api/admin/generate-report")
    async def generate_monthly_report_endpoint(
        data: Dict[str, Any],
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        generator = ReportGenerator(get_config_cached())
        year_month = data.get("year_month")
        report_type = data.get("report_type", "both")

        if report_type in ("excel", "both"):
            await generator.generate_excel_report(year_month, db)
            await db.commit()

        if report_type in ("pdf", "both"):
            await generator.generate_pdf_report(year_month, db)
            await db.commit()

        return {"success": True, "year_month": year_month, "report_type": report_type}

    @app.get("/api/admin/reports/download/{report_type}/{year_month}")
    async def download_report(
        report_type: str,
        year_month: str,
        current_user: Employee = Depends(get_current_user)
    ):
        cfg = get_config_cached()
        ext = ".xlsx" if report_type == "excel" else ".pdf"
        filename = f"attendance_report_{year_month}{ext}"
        filepath = os.path.join(cfg.reports_output_dir, filename)

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="报告文件不存在，请先生成报告")

        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if report_type == "excel" else "application/pdf"
        
        from fastapi.responses import FileResponse
        import urllib.parse
        encoded_filename = urllib.parse.quote(filename)
        
        return FileResponse(
            filepath,
            filename=filename,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )

    @app.get("/api/admin/scheduling-plans")
    async def get_scheduling_plans_endpoint(
        department_id: Optional[int] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        stmt = select(SchedulingPlan, Department).join(
            Department, SchedulingPlan.department_id == Department.id
        )
        if department_id:
            stmt = stmt.where(SchedulingPlan.department_id == department_id)
        stmt = stmt.order_by(SchedulingPlan.created_at.desc()).limit(20)
        result = await db.execute(stmt)
        rows = result.all()

        return [
            {
                "id": plan.id,
                "department_id": plan.department_id,
                "department_name": dept.name,
                "plan_name": plan.plan_name,
                "status": plan.status,
                "score_business": float(plan.score_business or 0),
                "score_cost": float(plan.score_cost or 0),
                "score_preference": float(plan.score_preference or 0),
                "score_total": float(plan.score_total or 0),
                "is_recommended": plan.is_recommended,
                "created_at": plan.created_at.strftime("%Y-%m-%d %H:%M") if plan.created_at else "",
            }
            for plan, dept in rows
        ]

    @app.post("/api/admin/scheduling-plans/{plan_id}/apply")
    async def apply_scheduling_plan_endpoint(
        plan_id: int,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        optimizer = SchedulingOptimizer(get_config_cached())
        count = await optimizer.apply_plan(plan_id, db)
        await db.commit()
        return {"success": True, "schedules_created": count}

    @app.get("/api/admin/employees")
    async def get_employees_endpoint(
        department_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        conditions = [Employee.is_active == True]
        if department_id:
            conditions.append(Employee.department_id == department_id)

        count_stmt = select(func.count()).select_from(Employee).where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(Employee, Department).join(
            Department, Employee.department_id == Department.id
        ).where(and_(*conditions)).order_by(Employee.employee_no).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(stmt)
        rows = result.all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [
                {
                    "id": emp.id,
                    "employee_no": emp.employee_no,
                    "name": emp.name,
                    "department_id": emp.department_id,
                    "department_name": dept.name,
                    "position": emp.position,
                    "phone": emp.phone,
                    "email": emp.email,
                }
                for emp, dept in rows
            ],
        }

    @app.get("/api/admin/departments")
    async def get_departments_endpoint(
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        stmt = select(Department).where(Department.is_active == True).order_by(Department.name)
        result = await db.execute(stmt)
        depts = list(result.scalars().all())

        return [
            {
                "id": d.id,
                "name": d.name,
                "code": d.code,
            }
            for d in depts
        ]

    @app.get("/api/admin/holidays")
    async def get_holidays_endpoint(
        year: Optional[int] = None,
        current_user: Employee = Depends(get_current_user),
        db: AsyncSession = Depends(get_session)
    ):
        y = year or date.today().year
        stmt = select(Holiday).where(
            func.strftime("%Y", Holiday.holiday_date) == str(y)
        ).order_by(Holiday.holiday_date)
        result = await db.execute(stmt)
        holidays = list(result.scalars().all())

        type_labels = {"national": "法定假日", "company": "公司假日", "makeup": "补班"}

        return [
            {
                "id": h.id,
                "name": h.name,
                "date": h.holiday_date.isoformat(),
                "type": h.holiday_type.value,
                "type_label": type_labels.get(h.holiday_type.value, h.holiday_type.value),
                "is_day_off": h.is_day_off,
            }
            for h in holidays
        ]

    return app
