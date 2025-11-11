import psutil
from typing import List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import User, Link, LinkStatus, Alert
from database.notification_models import UserNotificationSettings, WeeklyReport
from schemas.admin_schemas import (
    AdminDashboardStats, LinkCheckStats, UserStats,
    SystemStats, FailedCheck, WeeklyReportStats
)
from services.link_check_service import LinkCheckService
from services.weekly_report_service import WeeklyReportService

router = APIRouter(prefix="/api/admin", tags=["admin"])

def get_system_stats() -> SystemStats:
    """Get system resource usage statistics"""
    return SystemStats(
        cpu_usage=psutil.cpu_percent(),
        memory_usage=psutil.virtual_memory().percent,
        disk_usage=psutil.disk_usage('/').percent,
        uptime=psutil.boot_time()
    )

@router.get("/dashboard", response_model=AdminDashboardStats)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get comprehensive dashboard statistics"""
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    
    # Link check stats
    total_checks = db.query(func.count(LinkStatus.id)).scalar()
    successful_checks = db.query(func.count(LinkStatus.id)).filter(
        LinkStatus.is_available == True
    ).scalar()
    failed_checks = total_checks - successful_checks
    avg_response_time = db.query(func.avg(LinkStatus.response_time)).scalar() or 0
    
    checks_last_hour = db.query(func.count(LinkStatus.id)).filter(
        LinkStatus.checked_at >= hour_ago
    ).scalar()
    
    checks_last_day = db.query(func.count(LinkStatus.id)).filter(
        LinkStatus.checked_at >= day_ago
    ).scalar()
    
    link_stats = LinkCheckStats(
        total_checks=total_checks,
        successful_checks=successful_checks,
        failed_checks=failed_checks,
        average_response_time=float(avg_response_time),
        checks_last_hour=checks_last_hour,
        checks_last_day=checks_last_day
    )
    
    # User stats
    total_users = db.query(func.count(User.id)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    premium_users = db.query(func.count(User.id)).filter(User.is_premium == True).scalar()
    users_with_notifications = db.query(func.count(UserNotificationSettings.id)).filter(
        UserNotificationSettings.email_enabled == True
    ).scalar()
    
    user_stats = UserStats(
        total_users=total_users,
        active_users=active_users,
        premium_users=premium_users,
        users_with_notifications=users_with_notifications
    )
    
    return AdminDashboardStats(
        link_check_stats=link_stats,
        user_stats=user_stats,
        system_stats=get_system_stats(),
        last_updated=datetime.utcnow()
    )

@router.get("/failed-checks", response_model=List[FailedCheck])
async def get_failed_checks(
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get details of failed link checks in the last X hours"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    failed_checks = (
        db.query(
            LinkStatus,
            Link.url,
            User.email,
            func.count(LinkStatus.id).label("retry_count")
        )
        .join(Link, LinkStatus.link_id == Link.id)
        .join(User, Link.owner_id == User.id)
        .filter(
            and_(
                LinkStatus.is_available == False,
                LinkStatus.checked_at >= cutoff_time
            )
        )
        .group_by(LinkStatus.id, Link.url, User.email)
        .order_by(LinkStatus.checked_at.desc())
        .all()
    )
    
    return [
        FailedCheck(
            link_id=check[0].link_id,
            url=str(check[1]),
            owner_email=check[2],
            status_code=check[0].status_code,
            error_message=None if check[0].status_code > 0 else "Connection Error",
            last_checked=check[0].checked_at,
            retry_count=check[3]
        )
        for check in failed_checks
    ]

@router.get("/weekly-reports/stats", response_model=WeeklyReportStats)
async def get_weekly_report_stats(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get statistics about weekly report generation and delivery"""
    cutoff_time = datetime.utcnow() - timedelta(days=days)
    
    total_reports = db.query(func.count(WeeklyReport.id)).filter(
        WeeklyReport.sent_at >= cutoff_time
    ).scalar()
    
    users_opted_in = db.query(func.count(UserNotificationSettings.id)).filter(
        and_(
            UserNotificationSettings.weekly_report == True,
            UserNotificationSettings.email_enabled == True
        )
    ).scalar()
    
    # In a real implementation, you would track successful/failed deliveries
    # This is a simplified version
    successful_deliveries = total_reports
    failed_deliveries = 0
    
    return WeeklyReportStats(
        total_reports=total_reports,
        successful_deliveries=successful_deliveries,
        failed_deliveries=failed_deliveries,
        users_opted_in=users_opted_in
    )

@router.post("/weekly-reports/send-all")
async def trigger_weekly_reports(db: Session = Depends(get_db)):
    """Manually trigger weekly report generation for all users"""
    report_service = WeeklyReportService(db)
    results = await report_service.send_all_weekly_reports()
    return {
        "message": "Weekly reports job completed",
        "results": results
    }