"""
Celery Application Configuration
Production-grade task queue setup with Redis backend
"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def make_celery(app_name=None):
    """Create and configure Celery application"""

    # Celery configuration
    broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

    # Create Celery instance
    celery = Celery(
        app_name or 'calendar_bot',
        broker=broker_url,
        backend=result_backend,
        include=[
            'app.tasks.reminder_tasks',
            # 'app.tasks.calendar_tasks',     # TODO: Create later
            # 'app.tasks.maintenance_tasks'   # TODO: Create later
        ]
    )

    # Celery configuration
    celery.conf.update(
        # Task settings
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,

        # Task routing
        task_routes={
            'app.tasks.reminder_tasks.*': {'queue': 'reminders'},
            # 'app.tasks.calendar_tasks.*': {'queue': 'calendar'},       # TODO: Add later
            # 'app.tasks.maintenance_tasks.*': {'queue': 'maintenance'}, # TODO: Add later
        },

        # Worker settings
        worker_prefetch_multiplier=4,
        task_acks_late=True,
        worker_disable_rate_limits=False,

        # Task retry settings
        task_default_retry_delay=60,  # 1 minute
        task_max_retries=3,

        # Result settings
        result_expires=3600,  # 1 hour
        result_backend_transport_options={
            'master_name': 'mymaster',
        },

        # Monitoring
        worker_send_task_events=True,
        task_send_sent_event=True,

        # Beat schedule for periodic tasks
        beat_schedule={
            # Check for upcoming events every minute
            'check-upcoming-reminders': {
                'task': 'app.tasks.reminder_tasks.check_upcoming_reminders',
                'schedule': crontab(minute='*'),  # Every minute
                'options': {'queue': 'reminders'}
            },
            'auto-sync-user-calendars': {
                'task': 'app.tasks.reminder_tasks.auto_sync_all_users',
                'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
                'options': {'queue': 'reminders'}
            }
            # TODO: Add these tasks later when files exist
            # # Sync calendar events every 15 minutes
            # 'sync-calendar-events': {
            #     'task': 'app.tasks.calendar_tasks.sync_user_calendars',
            #     'schedule': crontab(minute='*/15'),  # Every 15 minutes
            #     'options': {'queue': 'calendar'}
            # },
            #
            # # Cleanup old reminders daily
            # 'cleanup-old-reminders': {
            #     'task': 'app.tasks.maintenance_tasks.cleanup_old_reminders',
            #     'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
            #     'options': {'queue': 'maintenance'}
            # },
            #
            # # Health check every 5 minutes
            # 'system-health-check': {
            #     'task': 'app.tasks.maintenance_tasks.system_health_check',
            #     'schedule': crontab(minute='*/5'),  # Every 5 minutes
            #     'options': {'queue': 'maintenance'}
            # },
        },
    )

    # Configure logging
    import logging

    log_level = os.getenv('CELERY_LOG_LEVEL', 'INFO')
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    return celery

# Create Celery instance
celery = make_celery()

# Task discovery
celery.autodiscover_tasks([
    'app.tasks.reminder_tasks',
    # 'app.tasks.calendar_tasks',     # TODO: Create later
    # 'app.tasks.maintenance_tasks'   # TODO: Create later
])

# Debug task for testing
@celery.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup"""
    print(f'Request: {self.request!r}')
    return 'Debug task completed successfully!'

if __name__ == '__main__':
    celery.start()