from typing import List, Dict
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import BackgroundTasks
from database.database import SessionLocal
from database.models import Link, User, LinkStatus
from services.email_service import email_service
from services.link_check_service import LinkCheckService
import os
import logging
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
MAX_CONCURRENT_CHECKS = int(os.getenv("MAX_CONCURRENT_CHECKS", "10"))
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "100"))
JITTER_SECONDS = int(os.getenv("JITTER_SECONDS", "30"))
ERROR_BACKOFF_MINUTES = int(os.getenv("ERROR_BACKOFF_MINUTES", "5"))

class LinkCheckerScheduler:
    def __init__(self):
        self.running = False
        self.check_service = None
        self.health_metrics = {
            "last_run": None,
            "total_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "total_errors": 0,
            "avg_response_time": 0
        }

    async def get_links_to_check(self, db: Session) -> List[Link]:
        """Get links that need to be checked based on their check frequency and status"""
        return (
            db.query(Link)
            .filter(
                and_(
                    Link.is_active == True,
                    Link.last_checked + timedelta(minutes=Link.check_frequency) <= datetime.utcnow()
                )
            )
            .order_by(
                Link.consecutive_failures.desc(),  # Prioritize failing links
                Link.last_checked.asc()           # Then oldest checks
            )
            .limit(MAX_BATCH_SIZE)
            .all()
        )

    def update_metrics(self, results: List[LinkStatus]):
        """Update health metrics based on check results"""
        self.health_metrics["last_run"] = datetime.utcnow()
        self.health_metrics["total_checks"] += len(results)
        
        successful = sum(1 for r in results if r.is_available)
        self.health_metrics["successful_checks"] += successful
        self.health_metrics["failed_checks"] += (len(results) - successful)
        
        # Update average response time
        valid_times = [r.response_time for r in results if r.response_time > 0]
        if valid_times:
            current_avg = self.health_metrics["avg_response_time"]
            self.health_metrics["avg_response_time"] = (
                (current_avg * (self.health_metrics["total_checks"] - len(valid_times)) +
                 sum(valid_times)) / self.health_metrics["total_checks"]
            )

    async def process_batch(self, links: List[Link], db: Session) -> List[LinkStatus]:
        """Process a batch of links with error handling and metrics"""
        if not self.check_service:
            self.check_service = LinkCheckService(db)

        results = []
        for i in range(0, len(links), MAX_CONCURRENT_CHECKS):
            batch = links[i:i + MAX_CONCURRENT_CHECKS]
            try:
                batch_results = await self.check_service.batch_check_links(batch)
                results.extend(batch_results)
                
                # Add jitter between batches to prevent thundering herd
                if i + MAX_CONCURRENT_CHECKS < len(links):
                    await asyncio.sleep(random.uniform(1, JITTER_SECONDS))
                
            except Exception as e:
                logger.error(f"Error processing batch: {str(e)}")
                self.health_metrics["total_errors"] += 1
                continue
        
        return results

    async def check_all_links(self):
        """Main function to check all links that need checking"""
        db = SessionLocal()
        try:
            links = await self.get_links_to_check(db)
            if not links:
                logger.info("No links to check at this time")
                return

            logger.info(f"Starting checks for {len(links)} links")
            results = await self.process_batch(links, db)
            self.update_metrics(results)
            
            logger.info(f"Completed checks. Success: {self.health_metrics['successful_checks']}, "
                       f"Failed: {self.health_metrics['failed_checks']}")
            
        except Exception as e:
            logger.error(f"Error in check_all_links: {str(e)}")
            self.health_metrics["total_errors"] += 1
        finally:
            db.close()

    async def start(self, background_tasks: BackgroundTasks):
        """Start the link checker scheduler with error handling and recovery"""
        self.running = True
        consecutive_errors = 0
        
        while self.running:
            try:
                await self.check_all_links()
                consecutive_errors = 0  # Reset error count on success
                
                # Calculate next run time with jitter
                jitter = random.uniform(-JITTER_SECONDS, JITTER_SECONDS)
                next_run = CHECK_INTERVAL_MINUTES * 60 + jitter
                
                logger.info(f"Next check scheduled in {next_run/60:.1f} minutes")
                await asyncio.sleep(next_run)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in link checker (attempt {consecutive_errors}): {str(e)}")
                
                # Exponential backoff for repeated errors
                backoff_time = min(
                    ERROR_BACKOFF_MINUTES * (2 ** (consecutive_errors - 1)),
                    CHECK_INTERVAL_MINUTES
                )
                logger.info(f"Backing off for {backoff_time} minutes")
                await asyncio.sleep(backoff_time * 60)

    def stop(self):
        """Stop the link checker scheduler"""
        self.running = False

    @property
    def health_check(self) -> Dict:
        """Get health check information"""
        return {
            "status": "healthy" if self.running else "stopped",
            "last_run": self.health_metrics["last_run"],
            "total_checks": self.health_metrics["total_checks"],
            "success_rate": (
                self.health_metrics["successful_checks"] / self.health_metrics["total_checks"]
                if self.health_metrics["total_checks"] > 0 else 0
            ),
            "avg_response_time": self.health_metrics["avg_response_time"],
            "error_count": self.health_metrics["total_errors"]
        }

# Create global scheduler instance
scheduler = LinkCheckerScheduler()

def schedule_link_checks(background_tasks: BackgroundTasks):
    """Initialize the link checker on server startup"""
    background_tasks.add_task(scheduler.start, background_tasks)