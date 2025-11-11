from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class LinkCheckStats(BaseModel):
    total_checks: int
    successful_checks: int
    failed_checks: int
    average_response_time: float
    checks_last_hour: int
    checks_last_day: int

class UserStats(BaseModel):
    total_users: int
    active_users: int
    premium_users: int
    users_with_notifications: int

class SystemStats(BaseModel):
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    uptime: float

class AdminDashboardStats(BaseModel):
    link_check_stats: LinkCheckStats
    user_stats: UserStats
    system_stats: SystemStats
    last_updated: datetime

class FailedCheck(BaseModel):
    link_id: int
    url: str
    owner_email: str
    status_code: int
    error_message: Optional[str]
    last_checked: datetime
    retry_count: int

class WeeklyReportStats(BaseModel):
    total_reports: int
    successful_deliveries: int
    failed_deliveries: int
    users_opted_in: int