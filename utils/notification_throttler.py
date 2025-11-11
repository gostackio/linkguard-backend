from typing import Dict, Optional
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)

class NotificationThrottler:
    def __init__(self):
        self._notification_history: Dict[str, Dict] = {}
        self._cleanup_threshold = 1000  # Number of items before cleanup

    def should_send_notification(
        self,
        user_id: int,
        link_id: int,
        notification_type: str,
        cooldown_minutes: int = 30
    ) -> bool:
        """
        Determine if a notification should be sent based on history and throttling rules
        """
        key = f"{user_id}:{link_id}:{notification_type}"
        now = datetime.utcnow()

        # Cleanup if needed
        if len(self._notification_history) > self._cleanup_threshold:
            self._cleanup_old_entries()

        # Get history for this notification
        history = self._notification_history.get(key)
        if not history:
            self._notification_history[key] = {
                'last_sent': now,
                'count': 1,
                'first_occurrence': now
            }
            return True

        # Calculate time since last notification
        time_since_last = now - history['last_sent']
        
        # Apply exponential backoff based on notification count
        required_cooldown = timedelta(minutes=cooldown_minutes * (2 ** (history['count'] - 1)))
        
        if time_since_last < required_cooldown:
            return False

        # Reset count if it's been a long time
        if time_since_last > timedelta(hours=24):
            history['count'] = 0
            history['first_occurrence'] = now
        
        # Update history
        history['last_sent'] = now
        history['count'] += 1
        
        return True

    def record_notification(
        self,
        user_id: int,
        link_id: int,
        notification_type: str,
        status_code: Optional[int] = None,
        error_type: Optional[str] = None
    ):
        """
        Record that a notification was sent
        """
        key = f"{user_id}:{link_id}:{notification_type}"
        now = datetime.utcnow()
        
        if key not in self._notification_history:
            self._notification_history[key] = {
                'last_sent': now,
                'count': 1,
                'first_occurrence': now,
                'status_codes': [status_code] if status_code else [],
                'error_types': [error_type] if error_type else []
            }
        else:
            history = self._notification_history[key]
            history['last_sent'] = now
            history['count'] += 1
            
            if status_code:
                history['status_codes'].append(status_code)
            if error_type:
                history['error_types'].append(error_type)

    def get_notification_summary(
        self,
        user_id: int,
        link_id: int,
        notification_type: str
    ) -> Optional[Dict]:
        """
        Get a summary of notifications for a specific user/link/type combination
        """
        key = f"{user_id}:{link_id}:{notification_type}"
        history = self._notification_history.get(key)
        
        if not history:
            return None
            
        return {
            'total_notifications': history['count'],
            'first_occurrence': history['first_occurrence'],
            'last_notification': history['last_sent'],
            'status_codes': history.get('status_codes', []),
            'error_types': history.get('error_types', [])
        }

    def _cleanup_old_entries(self):
        """
        Remove old entries to prevent memory growth
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=7)  # Keep up to 7 days of history
        
        self._notification_history = {
            k: v for k, v in self._notification_history.items()
            if v['last_sent'] > cutoff
        }

# Global instance
notification_throttler = NotificationThrottler()