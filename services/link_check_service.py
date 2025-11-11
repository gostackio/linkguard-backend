from typing import Optional, Dict, List
import asyncio
from datetime import datetime, timedelta
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging
import backoff  # For exponential backoff
from urllib.parse import urlparse
import dns.resolver
import socket
from concurrent.futures import ThreadPoolExecutor
import ssl
from database.models import Link, LinkStatus, Alert
from database.notification_models import UserNotificationSettings
from services.email_service import email_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LinkCheckResult:
    def __init__(self, success: bool, status_code: int, response_time: int,
                 content_type: str = "", final_url: str = "", redirect_count: int = 0,
                 error_type: str = "", error_message: str = ""):
        self.success = success
        self.status_code = status_code
        self.response_time = response_time
        self.content_type = content_type
        self.final_url = final_url
        self.redirect_count = redirect_count
        self.error_type = error_type
        self.error_message = error_message
        self.checked_at = datetime.utcnow()

class LinkCheckService:
    def __init__(self, db: Session):
        self.db = db
        self.max_retries = 3
        self.base_retry_delay = 5  # seconds
        self.timeout = 10.0   # seconds
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        self.dns_resolver = dns.resolver.Resolver()
        self.dns_resolver.timeout = 5
        self.dns_resolver.lifetime = 5

    async def _validate_domain(self, url: str) -> bool:
        """Validate domain exists and can be resolved"""
        try:
            domain = urlparse(url).netloc
            if not domain:
                return False

            # Try to resolve domain
            return await asyncio.get_event_loop().run_in_executor(
                self.thread_pool,
                self._resolve_domain,
                domain
            )
        except Exception as e:
            logger.error(f"Domain validation error for {url}: {str(e)}")
            return False

    def _resolve_domain(self, domain: str) -> bool:
        """Resolve domain using DNS (runs in thread pool)"""
        try:
            self.dns_resolver.resolve(domain, 'A')
            return True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return False
        except Exception:
            return False

    async def _check_ssl(self, url: str) -> Dict:
        """Check SSL certificate status"""
        try:
            if not url.startswith('https://'):
                return {"valid": False, "reason": "Not HTTPS"}

            domain = urlparse(url).netloc
            context = ssl.create_default_context()
            
            # Run SSL check in thread pool
            cert_info = await asyncio.get_event_loop().run_in_executor(
                self.thread_pool,
                self._get_ssl_info,
                domain,
                context
            )
            
            return {
                "valid": True,
                "expires": cert_info["expires"],
                "issuer": cert_info["issuer"]
            }
        except ssl.SSLError as e:
            return {"valid": False, "reason": str(e)}
        except Exception as e:
            return {"valid": False, "reason": "SSL check failed"}

    def _get_ssl_info(self, domain: str, context: ssl.SSLContext) -> Dict:
        """Get SSL certificate info (runs in thread pool)"""
        with socket.create_connection((domain, 443)) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                return {
                    "expires": datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z"),
                    "issuer": dict(x[0] for x in cert["issuer"])
                }

    @backoff.on_exception(
        backoff.expo,
        (httpx.HTTPError, httpx.ConnectTimeout),
        max_tries=3,
        max_time=30
    )
    async def _perform_check(self, url: str) -> LinkCheckResult:
        """Perform a single check with timing and advanced error handling"""
        start_time = datetime.now()
        
        # Validate domain first
        if not await self._validate_domain(url):
            return LinkCheckResult(
                success=False,
                status_code=0,
                response_time=0,
                error_type="DNS_ERROR",
                error_message="Domain could not be resolved"
            )

        try:
            # Check SSL for HTTPS URLs
            if url.startswith('https://'):
                ssl_info = await self._check_ssl(url)
                if not ssl_info["valid"]:
                    return LinkCheckResult(
                        success=False,
                        status_code=0,
                        response_time=0,
                        error_type="SSL_ERROR",
                        error_message=ssl_info["reason"]
                    )

            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                verify=True,
                http2=True
            ) as client:
                try:
                    # Try HEAD request first
                    response = await client.head(str(url))
                    method_used = "HEAD"
                except httpx.HTTPError:
                    # Fall back to GET if HEAD fails
                    response = await client.get(str(url))
                    method_used = "GET"

                end_time = datetime.now()
                response_time = int((end_time - start_time).total_seconds() * 1000)

                return LinkCheckResult(
                    success=200 <= response.status_code < 400,
                    status_code=response.status_code,
                    response_time=response_time,
                    content_type=response.headers.get("content-type", ""),
                    final_url=str(response.url),
                    redirect_count=len(response.history)
                )

        except httpx.ConnectTimeout:
            return LinkCheckResult(
                success=False,
                status_code=0,
                response_time=0,
                error_type="TIMEOUT",
                error_message="Connection timed out"
            )
        except httpx.TooManyRedirects:
            return LinkCheckResult(
                success=False,
                status_code=0,
                response_time=0,
                error_type="REDIRECT_ERROR",
                error_message="Too many redirects"
            )
        except httpx.HTTPError as e:
            return LinkCheckResult(
                success=False,
                status_code=getattr(e.response, 'status_code', 0),
                response_time=0,
                error_type="HTTP_ERROR",
                error_message=str(e)
            )
        except Exception as e:
            return LinkCheckResult(
                success=False,
                status_code=0,
                response_time=0,
                error_type="UNKNOWN_ERROR",
                error_message=str(e)
            )

    async def check_with_retry(self, link: Link) -> Optional[LinkStatus]:
        """Check a link with retry logic and comprehensive error handling"""
        logger.info(f"Starting check for link: {link.name} ({link.url})")
        
        check_result = await self._perform_check(str(link.url))
        
        # Create link status record
        link_status = LinkStatus(
            link_id=link.id,
            status_code=check_result.status_code,
            response_time=check_result.response_time,
            is_available=check_result.success,
            error_type=check_result.error_type,
            error_message=check_result.error_message,
            checked_at=check_result.checked_at
        )
        self.db.add(link_status)
        
        # Update link
        link.last_checked = datetime.utcnow()
        link.last_status = check_result.success
        link.consecutive_failures = 0 if check_result.success else (link.consecutive_failures or 0) + 1
        
        # Handle status change alerts
        await self._handle_status_change(link, check_result)
        
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error saving check results: {str(e)}")
            raise
        
        return link_status

    async def _handle_status_change(self, link: Link, check_result: LinkCheckResult):
        """Handle status changes and notifications"""
        try:
            settings = self.db.query(UserNotificationSettings).filter(
                UserNotificationSettings.user_id == link.owner_id
            ).first()
            
            if not settings or not settings.email_enabled:
                return

            # Determine if this is a status change
            is_status_change = link.last_status is not None and link.last_status != check_result.success
            
            if (not check_result.success and settings.broken_links) or \
               (is_status_change and settings.status_changes):
                
                alert_type = "status_change" if is_status_change else "broken"
                alert_message = self._generate_alert_message(link, check_result, alert_type)
                
                # Create alert
                alert = Alert(
                    type=alert_type,
                    message=alert_message,
                    link_id=link.id,
                    user_id=link.owner_id,
                    details={
                        "status_code": check_result.status_code,
                        "error_type": check_result.error_type,
                        "error_message": check_result.error_message
                    }
                )
                self.db.add(alert)
                
                # Send email notification
                if settings.email_enabled:
                    await self._send_alert_email(link, check_result, alert_type)
                
        except Exception as e:
            logger.error(f"Error handling status change for link {link.id}: {str(e)}")

    def _generate_alert_message(self, link: Link, check_result: LinkCheckResult, alert_type: str) -> str:
        """Generate appropriate alert message based on check results"""
        if alert_type == "status_change":
            return f"Link status changed: {link.name} is now {'UP' if check_result.success else 'DOWN'}"
        
        if check_result.error_type == "DNS_ERROR":
            return f"Domain not found: {link.name}"
        elif check_result.error_type == "SSL_ERROR":
            return f"SSL certificate error for {link.name}"
        elif check_result.error_type == "TIMEOUT":
            return f"Connection timeout for {link.name}"
        elif check_result.status_code >= 400:
            return f"Link is broken: {link.name} (HTTP {check_result.status_code})"
        else:
            return f"Link error: {link.name} - {check_result.error_message}"

    async def _send_alert_email(self, link: Link, check_result: LinkCheckResult, alert_type: str):
        """Send alert email with detailed information"""
        try:
            subject = "🔄 Link Status Change" if alert_type == "status_change" else "🚨 Broken Link Alert"
            await email_service.send_broken_link_alert(
                link.owner.email,
                link.name,
                str(link.url),
                check_result.status_code
            )
        except Exception as e:
            logger.error(f"Failed to send alert email for link {link.id}: {str(e)}")

    async def batch_check_links(self, links: List[Link], max_concurrent: int = 5) -> List[LinkStatus]:
        """Check multiple links concurrently with rate limiting"""
        results = []
        for i in range(0, len(links), max_concurrent):
            batch = links[i:i + max_concurrent]
            tasks = [self.check_with_retry(link) for link in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend([r for r in batch_results if not isinstance(r, Exception)])
        return results

    async def get_links_to_check(self) -> List[Link]:
        """Get links that need to be checked based on their check frequency and status"""
        return (
            self.db.query(Link)
            .filter(
                and_(
                    Link.is_active == True,
                    Link.last_checked + timedelta(minutes=Link.check_frequency) <= datetime.utcnow()
                )
            )
            .order_by(Link.consecutive_failures.desc())  # Prioritize failing links
            .all()
        )