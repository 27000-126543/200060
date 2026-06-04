import enum
from datetime import datetime, date, time, timedelta
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, Date, DateTime, Time,
    Text, Enum, ForeignKey, Index, UniqueConstraint, JSON, Numeric, Date as SADate
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func


Base = declarative_base()


class PunchSource(enum.Enum):
    ACCESS_CONTROL = "access_control"
    GPS = "gps"
    WIFI = "wifi"
    MANUAL = "manual"
    SELF_SERVICE = "self_service"


class PunchType(enum.Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"


class AnomalyType(enum.Enum):
    LATE = "late"
    EARLY_LEAVE = "early_leave"
    MISSING_PUNCH_IN = "missing_punch_in"
    MISSING_PUNCH_OUT = "missing_punch_out"
    ABSENT = "absent"
    OVERTIME = "overtime"
    OVERTIME_EXCEED = "overtime_exceed"


class AnomalyStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    APPEALED = "appealed"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_CORRECTED = "auto_corrected"


class ApprovalType(enum.Enum):
    SUPPLEMENTARY_PUNCH = "supplementary_punch"
    LEAVE = "leave"
    SICK_LEAVE = "sick_leave"
    BUSINESS_TRIP = "business_trip"
    SHIFT_SWAP = "shift_swap"
    OVERTIME_APPLY = "overtime_apply"
    ANOMALY_EXPLAIN = "anomaly_explain"


class ApprovalStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ShiftType(enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"
    FULL_DAY = "full_day"
    FLEXIBLE = "flexible"


class ScheduleStatus(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ADJUSTED = "adjusted"
    CANCELLED = "cancelled"


class HolidayType(enum.Enum):
    NATIONAL = "national"
    COMPANY = "company"
    MAKEUP = "makeup"


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    code = Column(String(50), nullable=False, unique=True)
    parent_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    parent = relationship("Department", remote_side=[id], backref="children")
    employees = relationship("Employee", back_populates="department", foreign_keys="Employee.department_id")
    schedules = relationship("Schedule", back_populates="department")

    __table_args__ = (
        Index("idx_department_code", "code"),
    )


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_no = Column(String(50), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    position = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)
    wechat_work_id = Column(String(100), nullable=True)
    hire_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    shift_type = Column(Enum(ShiftType), default=ShiftType.FULL_DAY, nullable=False)
    hourly_rate = Column(Numeric(10, 2), default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    department = relationship("Department", back_populates="employees", foreign_keys=[department_id])
    punch_records = relationship("PunchRecord", back_populates="employee", cascade="all, delete-orphan")
    anomalies = relationship("AnomalyRecord", back_populates="employee", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="employee")

    __table_args__ = (
        Index("idx_employee_no", "employee_no"),
        Index("idx_employee_dept", "department_id"),
    )


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    shift_type = Column(Enum(ShiftType), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    rest_minutes = Column(Integer, default=60, nullable=False)
    grace_period_minutes = Column(Integer, default=5, nullable=False)
    is_cross_day = Column(Boolean, default=False, nullable=False)
    color_code = Column(String(7), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    schedules = relationship("Schedule", back_populates="shift")

    __table_args__ = (
        Index("idx_shift_type", "shift_type"),
    )


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    schedule_date = Column(Date, nullable=False)
    status = Column(Enum(ScheduleStatus), default=ScheduleStatus.PUBLISHED, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="schedules")
    department = relationship("Department", back_populates="schedules")
    shift = relationship("Shift", back_populates="schedules")

    __table_args__ = (
        UniqueConstraint("employee_id", "schedule_date", "version", name="uq_schedule_emp_date_ver"),
        Index("idx_schedule_date", "schedule_date"),
        Index("idx_schedule_dept_date", "department_id", "schedule_date"),
    )


class PunchRecord(Base):
    __tablename__ = "punch_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    punch_time = Column(DateTime, nullable=False)
    punch_date = Column(Date, nullable=False)
    punch_type = Column(Enum(PunchType), nullable=False)
    source = Column(Enum(PunchSource), nullable=False)
    device_id = Column(String(100), nullable=True)
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    location_address = Column(String(500), nullable=True)
    wifi_ssid = Column(String(200), nullable=True)
    is_valid = Column(Boolean, default=True, nullable=False)
    is_supplementary = Column(Boolean, default=False, nullable=False)
    raw_data = Column(JSON, nullable=True)
    batch_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="punch_records")

    __table_args__ = (
        Index("idx_punch_emp_date", "employee_id", "punch_date"),
        Index("idx_punch_date", "punch_date"),
        Index("idx_punch_batch", "batch_id"),
    )


class AnomalyRecord(Base):
    __tablename__ = "anomaly_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    anomaly_date = Column(Date, nullable=False)
    anomaly_type = Column(Enum(AnomalyType), nullable=False)
    status = Column(Enum(AnomalyStatus), default=AnomalyStatus.PENDING, nullable=False)
    scheduled_time = Column(DateTime, nullable=True)
    actual_time = Column(DateTime, nullable=True)
    deviation_minutes = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    auto_detected = Column(Boolean, default=True, nullable=False)
    notification_sent = Column(Boolean, default=False, nullable=False)
    notification_sent_at = Column(DateTime, nullable=True)
    corrected_by_approval_id = Column(Integer, ForeignKey("approval_records.id"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="anomalies")
    approval = relationship("ApprovalRecord", foreign_keys=[corrected_by_approval_id])

    __table_args__ = (
        Index("idx_anomaly_emp_date", "employee_id", "anomaly_date"),
        Index("idx_anomaly_type_status", "anomaly_type", "status"),
        Index("idx_anomaly_date", "anomaly_date"),
    )


class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    approval_type = Column(Enum(ApprovalType), nullable=False)
    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    related_date = Column(Date, nullable=False)
    related_date_end = Column(Date, nullable=True)
    reason = Column(Text, nullable=True)
    attachment_urls = Column(JSON, nullable=True)
    approver_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approver_comment = Column(Text, nullable=True)
    swap_target_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    swap_target_schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    swap_source_schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    supplementary_punch_time = Column(DateTime, nullable=True)
    supplementary_punch_type = Column(Enum(PunchType), nullable=True)
    auto_verified = Column(Boolean, default=False, nullable=False)
    verification_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee", foreign_keys=[employee_id])
    approver = relationship("Employee", foreign_keys=[approver_id])
    swap_target = relationship("Employee", foreign_keys=[swap_target_employee_id])

    __table_args__ = (
        Index("idx_approval_emp", "employee_id"),
        Index("idx_approval_type_status", "approval_type", "status"),
        Index("idx_approval_date", "related_date"),
    )


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    holiday_date = Column(Date, nullable=False)
    holiday_type = Column(Enum(HolidayType), nullable=False)
    is_day_off = Column(Boolean, default=True, nullable=False)
    makeup_work_date = Column(Date, nullable=True)
    batch_import_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("holiday_date", name="uq_holiday_date"),
        Index("idx_holiday_date", "holiday_date"),
        Index("idx_holiday_batch", "batch_import_id"),
    )


class MonthlyAttendanceSummary(Base):
    __tablename__ = "monthly_attendance_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    year_month = Column(String(7), nullable=False)
    total_work_days = Column(Integer, default=0, nullable=False)
    actual_work_days = Column(Integer, default=0, nullable=False)
    late_count = Column(Integer, default=0, nullable=False)
    early_leave_count = Column(Integer, default=0, nullable=False)
    absent_count = Column(Integer, default=0, nullable=False)
    missing_punch_count = Column(Integer, default=0, nullable=False)
    total_work_hours = Column(Numeric(10, 2), default=0, nullable=False)
    overtime_hours_weekday = Column(Numeric(10, 2), default=0, nullable=False)
    overtime_hours_weekend = Column(Numeric(10, 2), default=0, nullable=False)
    overtime_hours_holiday = Column(Numeric(10, 2), default=0, nullable=False)
    leave_days_annual = Column(Numeric(5, 1), default=0, nullable=False)
    leave_days_sick = Column(Numeric(5, 1), default=0, nullable=False)
    leave_days_personal = Column(Numeric(5, 1), default=0, nullable=False)
    salary_deduction = Column(Numeric(10, 2), default=0, nullable=False)
    overtime_allowance = Column(Numeric(10, 2), default=0, nullable=False)
    net_adjustment = Column(Numeric(10, 2), default=0, nullable=False)
    compliance_rate = Column(Numeric(5, 4), default=1.0, nullable=False)
    generated_at = Column(DateTime, default=func.now(), nullable=False)

    employee = relationship("Employee")
    department = relationship("Department")

    __table_args__ = (
        UniqueConstraint("employee_id", "year_month", name="uq_summary_emp_month"),
        Index("idx_summary_month", "year_month"),
        Index("idx_summary_dept_month", "department_id", "year_month"),
    )


class SchedulingPlan(Base):
    __tablename__ = "scheduling_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    plan_name = Column(String(200), nullable=False)
    trigger_reason = Column(Text, nullable=True)
    plan_data = Column(JSON, nullable=False)
    score_business = Column(Float, nullable=True)
    score_cost = Column(Float, nullable=True)
    score_preference = Column(Float, nullable=True)
    score_total = Column(Float, nullable=True)
    is_recommended = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="draft", nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    department = relationship("Department")

    __table_args__ = (
        Index("idx_plan_dept", "department_id"),
        Index("idx_plan_status", "status"),
    )


class OvertimeAlert(Base):
    __tablename__ = "overtime_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    alert_date = Column(Date, nullable=False)
    consecutive_overtime_days = Column(Integer, nullable=False)
    max_daily_hours = Column(Float, nullable=False)
    alert_type = Column(String(50), nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    employee = relationship("Employee")

    __table_args__ = (
        Index("idx_overtime_emp", "employee_id"),
        Index("idx_overtime_date", "alert_date"),
    )


class DashboardMetric(Base):
    __tablename__ = "dashboard_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_date = Column(Date, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    total_employees = Column(Integer, default=0, nullable=False)
    present_employees = Column(Integer, default=0, nullable=False)
    attendance_rate = Column(Numeric(5, 4), default=0, nullable=False)
    no_punch_count = Column(Integer, default=0, nullable=False)
    anomaly_count = Column(Integer, default=0, nullable=False)
    late_count = Column(Integer, default=0, nullable=False)
    early_leave_count = Column(Integer, default=0, nullable=False)
    overtime_employees = Column(Integer, default=0, nullable=False)
    overtime_total_hours = Column(Numeric(10, 2), default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    department = relationship("Department")

    __table_args__ = (
        UniqueConstraint("metric_date", "department_id", name="uq_dashboard_date_dept"),
        Index("idx_dashboard_date", "metric_date"),
    )


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    operator_name = Column(String(100), nullable=True)
    operation_type = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)
    detail = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_oplog_operator", "operator_id"),
        Index("idx_oplog_type", "operation_type"),
        Index("idx_oplog_time", "created_at"),
    )


class BusinessVolume(Base):
    __tablename__ = "business_volumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    record_date = Column(Date, nullable=False)
    hour = Column(Integer, nullable=False)
    customer_count = Column(Integer, default=0, nullable=False)
    transaction_count = Column(Integer, default=0, nullable=False)
    revenue = Column(Numeric(12, 2), default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    department = relationship("Department")

    __table_args__ = (
        UniqueConstraint("department_id", "record_date", "hour", name="uq_bv_dept_date_hour"),
        Index("idx_bv_dept_date", "department_id", "record_date"),
    )


async def init_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
