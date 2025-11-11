from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import and_
from sqlalchemy.orm import Session
from database.models import User, Link, LinkStatus
from database.notification_models import WeeklyReport
from database.notification_models import UserNotificationSettings
from services.email_service import email_service

class WeeklyReportService:
    def __init__(self, db: Session):
        self.db = db

    async def _get_link_stats(self, user_id: int, start_date: datetime) -> Dict:
        """Get link statistics for a user within the specified period"""
        # Get all user's links
        links = self.db.query(Link).filter(Link.owner_id == user_id).all()
        total_links = len(links)
        
        if total_links == 0:
            return None

        # Get latest status for each link
        healthy_links = 0
        broken_links = 0
        new_issues = 0
        broken_links_details = []

        for link in links:
            latest_status = (
                self.db.query(LinkStatus)
                .filter(LinkStatus.link_id == link.id)
                .order_by(LinkStatus.checked_at.desc())
                .first()
            )
            
            if latest_status:
                if latest_status.is_available:
                    healthy_links += 1
                else:
                    broken_links += 1
                    # Check if this is a new issue
                    previous_status = (
                        self.db.query(LinkStatus)
                        .filter(
                            and_(
                                LinkStatus.link_id == link.id,
                                LinkStatus.checked_at < latest_status.checked_at,
                                LinkStatus.checked_at >= start_date
                            )
                        )
                        .order_by(LinkStatus.checked_at.desc())
                        .first()
                    )
                    
                    if not previous_status or previous_status.is_available:
                        new_issues += 1
                    
                    broken_links_details.append({
                        "name": link.name,
                        "url": str(link.url),
                        "status_code": latest_status.status_code,
                        "last_checked": latest_status.checked_at
                    })

        # Calculate percentages
        healthy_percentage = (healthy_links / total_links * 100) if total_links > 0 else 0

        # Create broken links table HTML
        broken_links_table = ""
        for link in broken_links_details:
            broken_links_table += f"""
            <tr>
                <td>{link['name']}</td>
                <td><a href="{link['url']}">{link['url']}</a></td>
                <td>HTTP {link['status_code']}</td>
                <td>{link['last_checked'].strftime('%Y-%m-%d %H:%M:%S')}</td>
            </tr>
            """

        return {
            "total_links": total_links,
            "healthy_links": healthy_links,
            "broken_links": broken_links,
            "new_issues": new_issues,
            "healthy_percentage": round(healthy_percentage, 1),
            "broken_links_table": broken_links_table
        }

    async def generate_and_send_weekly_report(self, user: User) -> Optional[WeeklyReport]:
        """Generate and send weekly report for a user"""
        # Check if user wants weekly reports
        settings = self.db.query(UserNotificationSettings).filter(
            UserNotificationSettings.user_id == user.id
        ).first()
        
        if not settings or not settings.weekly_report or not settings.email_enabled:
            return None

        # Get stats for the past week
        start_date = datetime.utcnow() - timedelta(days=7)
        stats = await self._get_link_stats(user.id, start_date)
        
        if not stats:
            return None

        # Create weekly report record
        report = WeeklyReport(
            user_id=user.id,
            total_links=stats["total_links"],
            healthy_links=stats["healthy_links"],
            broken_links=stats["broken_links"],
            new_issues=stats["new_issues"]
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        # Send email
        try:
            await email_service.send_weekly_report(user.email, stats)
        except Exception as e:
            print(f"Failed to send weekly report to {user.email}: {str(e)}")
            return None

        return report

    async def send_all_weekly_reports(self) -> Dict[str, int]:
        """Generate and send weekly reports for all eligible users"""
        users = self.db.query(User).filter(User.is_active == True).all()
        
        success_count = 0
        error_count = 0
        
        for user in users:
            try:
                report = await self.generate_and_send_weekly_report(user)
                if report:
                    success_count += 1
            except Exception as e:
                print(f"Error generating report for user {user.id}: {str(e)}")
                error_count += 1

        return {
            "success": success_count,
            "errors": error_count
        }