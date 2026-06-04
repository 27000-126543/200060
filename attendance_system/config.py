import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


_CONFIG_INSTANCE = None


@dataclass
class DatabaseConfig:
    url: str = "sqlite+aiosqlite:///./attendance.db"
    pool_size: int = 20
    max_overflow: int = 30


@dataclass
class DataSourceConfig:
    enabled: bool = True
    api_url: str = ""
    timeout: int = 30
    batch_size: int = 5000
    geofence_radius_meters: int = 200


@dataclass
class AnomalyConfig:
    late_threshold_minutes: int = 5
    early_leave_threshold_minutes: int = 5
    missing_punch_window_hours: int = 2
    overtime_daily_limit_hours: int = 12
    overtime_consecutive_alert: bool = True


@dataclass
class SalaryConfig:
    late_deduction_per_minute: float = 5.0
    early_leave_deduction_per_minute: float = 5.0
    absent_deduction_per_day: float = 200.0
    missing_punch_deduction: float = 50.0
    overtime_rate_weekday: float = 1.5
    overtime_rate_weekend: float = 2.0
    overtime_rate_holiday: float = 3.0


@dataclass
class SchedulingConfig:
    optimization_trigger_threshold: float = 0.9
    min_staff_ratio: float = 0.8
    max_daily_hours: int = 12
    max_weekly_hours: int = 60
    min_rest_hours_between_shifts: int = 11
    business_volume_weight: float = 0.6
    labor_cost_weight: float = 0.3
    employee_preference_weight: float = 0.1


@dataclass
class SystemConfig:
    name: str = "企业考勤智能管理系统"
    version: str = "1.0.0"
    timezone: str = "Asia/Shanghai"
    language: str = "zh_CN"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    data_sources: dict = field(default_factory=dict)
    anomaly: AnomalyConfig = field(default_factory=AnomalyConfig)
    salary: SalaryConfig = field(default_factory=SalaryConfig)
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    reports_output_dir: str = "./reports"
    log_level: str = "INFO"
    log_file: str = "./logs/attendance.log"


def load_config(config_path: Optional[str] = None) -> SystemConfig:
    global _CONFIG_INSTANCE
    if _CONFIG_INSTANCE is not None:
        return _CONFIG_INSTANCE

    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

    cfg = SystemConfig()
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        if "database" in raw:
            for k, v in raw["database"].items():
                if hasattr(cfg.database, k):
                    setattr(cfg.database, k, v)

        if "data_sources" in raw:
            for name, ds_cfg in raw["data_sources"].items():
                cfg.data_sources[name] = DataSourceConfig(**ds_cfg)

        if "anomaly_detection" in raw:
            for k, v in raw["anomaly_detection"].items():
                key = k if k in AnomalyConfig.__dataclass_fields__ else k.replace("-", "_")
                if hasattr(cfg.anomaly, key):
                    setattr(cfg.anomaly, key, v)

        if "salary" in raw:
            for k, v in raw["salary"].items():
                key = k if k in SalaryConfig.__dataclass_fields__ else k.replace("-", "_")
                if hasattr(cfg.salary, key):
                    setattr(cfg.salary, key, v)

        if "scheduling" in raw:
            for k, v in raw["scheduling"].items():
                key = k if k in SchedulingConfig.__dataclass_fields__ else k.replace("-", "_")
                if hasattr(cfg.scheduling, key):
                    setattr(cfg.scheduling, key, v)

        if "reports" in raw:
            cfg.reports_output_dir = raw["reports"].get("output_dir", cfg.reports_output_dir)

        if "logging" in raw:
            cfg.log_level = raw["logging"].get("level", cfg.log_level)
            cfg.log_file = raw["logging"].get("file", cfg.log_file)

    _CONFIG_INSTANCE = cfg
    return cfg


def get_config() -> SystemConfig:
    if _CONFIG_INSTANCE is None:
        return load_config()
    return _CONFIG_INSTANCE
