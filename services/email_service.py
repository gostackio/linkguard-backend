from typing import List
import os
from dotenv import load_dotenv
from fastapi import HTTPException
from datetime import datetime
import smtplib
from email.message import EmailMessage

# Optional SendGrid import (only used when not testing)
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
except Exception:
    SendGridAPIClient = None

# Load environment variables
load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", 25))

class EmailService:
    def __init__(self):
        # In test mode use a local SMTP relay (configured in .env.test)
        self.testing = os.getenv("TESTING", "0") == "1"
        self.email_enabled = os.getenv("EMAIL_ENABLED", "0") == "1"
        
        if self.testing:
            self.use_smtp = True
            self.smtp_host = SMTP_HOST
            self.smtp_port = SMTP_PORT
            self.from_email = FROM_EMAIL or "test@example.com"
            return

        # Production mode: SendGrid is optional
        if not self.email_enabled:
            print("⚠️  Email service is DISABLED. Set EMAIL_ENABLED=1 to enable.")
            self.email_enabled = False
            self.use_smtp = False
            return

        if not SENDGRID_API_KEY or not SendGridAPIClient:
            raise ValueError("SENDGRID_API_KEY environment variable is not set or sendgrid is unavailable")
        if not FROM_EMAIL:
            raise ValueError("SENDGRID_FROM_EMAIL environment variable is not set")

        self.client = SendGridAPIClient(SENDGRID_API_KEY)
        self.from_email = Email(FROM_EMAIL)
        self.use_smtp = False

    async def send_email(self, to_email: str, subject: str, content: str):
        # If email is disabled, just log and return success
        if not getattr(self, "email_enabled", False) and not getattr(self, "use_smtp", False):
            print(f"📧 Email service disabled - would send to {to_email}: {subject}")
            return 200  # Return success code to not break the flow

        if getattr(self, "use_smtp", False):
            try:
                msg = EmailMessage()
                msg["From"] = self.from_email
                msg["To"] = to_email
                msg["Subject"] = subject
                msg.set_content(content, subtype="html")

                with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
                    s.send_message(msg)
                return 250
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to send email via SMTP: {str(e)}")

        try:
            message = Mail(
                from_email=self.from_email,
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", content)
            )
            response = self.client.send(message)
            return response.status_code
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    async def send_broken_link_alert(self, user_email: str, link_name: str, link_url: str, status_code: int):
        subject = f"🚨 Broken Link Alert: {link_name}"
        content = f"""
        <h2>Broken Link Detected</h2>
        <p>We detected that one of your monitored links is not working properly:</p>
        <ul>
            <li><strong>Link Name:</strong> {link_name}</li>
            <li><strong>URL:</strong> {link_url}</li>
            <li><strong>Status Code:</strong> {status_code}</li>
            <li><strong>Detected At:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
        </ul>
        <p>Please check your link and take necessary action.</p>
        """
        return await self.send_email(user_email, subject, content)

    async def send_weekly_report(self, user_email: str, stats: dict):
        subject = "📊 Your Weekly Link Health Report"
        content = f"""
        <h2>Weekly Link Health Report</h2>
        <p>Here's a summary of your links for the past week:</p>
        <ul>
            <li><strong>Total Links:</strong> {stats['total_links']}</li>
            <li><strong>Healthy Links:</strong> {stats['healthy_links']} ({stats['healthy_percentage']}%)</li>
            <li><strong>Broken Links:</strong> {stats['broken_links']}</li>
            <li><strong>New Issues:</strong> {stats['new_issues']}</li>
        </ul>
        <h3>Links Requiring Attention</h3>
        <table border="1" cellpadding="5">
            <tr>
                <th>Link Name</th>
                <th>URL</th>
                <th>Status</th>
                <th>Last Checked</th>
            </tr>
            {stats['broken_links_table']}
        </table>
        """
        return await self.send_email(user_email, subject, content)

    async def send_password_reset(self, user_email: str, reset_token: str, frontend_url: str):
        subject = "🔑 Reset Your LinkGuard Password"
        reset_url = f"{frontend_url}/reset-password?token={reset_token}"
        content = f"""
        <h2>Password Reset Request</h2>
        <p>You recently requested to reset your password for your LinkGuard account. Click the button below to reset it:</p>
        <p style="text-align: center;">
            <a href="{reset_url}" style="background-color: #4CAF50; color: white; padding: 14px 20px; margin: 8px 0; border: none; cursor: pointer; text-decoration: none;">
                Reset Password
            </a>
        </p>
        <p>If you did not request a password reset, please ignore this email or contact support if you have concerns.</p>
        <p><small>This password reset link will expire in 1 hour.</small></p>
        """
        return await self.send_email(user_email, subject, content)

# Create a global instance
email_service = EmailService()