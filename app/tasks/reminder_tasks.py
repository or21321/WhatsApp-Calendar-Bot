"""
Celery Tasks for Event Reminders
Production-grade reminder system with retry logic and error handling
"""

import os
from datetime import datetime, timedelta
from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

# Import your app components
from app.celery_app import celery

# Set up logging
logger = get_task_logger(__name__)

class CallbackTask(Task):
    """Base task class with error handling and retry logic"""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails"""
        logger.error(f'Task {task_id} failed: {exc}')
        logger.error(f'Exception info: {einfo}')

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task retries"""
        logger.warning(f'Task {task_id} retrying: {exc}')

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds"""
        logger.info(f'Task {task_id} completed successfully')


def get_flask_app():
    """Get Flask app instance with proper context"""
    try:
        # Import here to avoid circular imports
        import sys
        import os
        sys.path.append('/app')

        from main import create_app
        app = create_app()
        return app
    except Exception as e:
        logger.error(f"Failed to get Flask app: {e}")
        return None


@celery.task(bind=True, base=CallbackTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def check_upcoming_reminders(self):
    """
    Check for upcoming reminders and send WhatsApp notifications
    Runs every minute via Celery Beat
    """
    app = get_flask_app()
    if not app:
        logger.error("Failed to get Flask app")
        return "Failed to get Flask app"

    with app.app_context():
        try:
            logger.info("🔍 Checking for upcoming reminders...")
            # Import here to avoid circular imports
            from app.models.user import db, User, ScheduledReminder
            from app.services.google_calendar import GoogleCalendarService

            # Get current time
            now = datetime.utcnow()

            # Find reminders that should be sent now (within the last minute)
            upcoming_reminders = ScheduledReminder.query.filter(
                ScheduledReminder.reminder_time <= now,
                ScheduledReminder.reminder_time > now - timedelta(minutes=1),
                ScheduledReminder.sent == False
            ).all()

            logger.info(f"Found {len(upcoming_reminders)} reminders to send")

            for reminder in upcoming_reminders:
                try:
                    # Send the reminder
                    send_event_reminder.delay(
                        reminder.user_id,
                        {
                            'id': reminder.event_id,
                            'title': reminder.event_title,
                            'start_time': reminder.event_start_time.isoformat(),
                            'minutes_before': reminder.minutes_before
                        }
                    )

                    # Mark as sent
                    reminder.sent = True
                    db.session.commit()

                    logger.info(f"✅ Queued reminder for user {reminder.user_id}: {reminder.event_title}")

                except Exception as e:
                    logger.error(f"❌ Failed to send reminder {reminder.id}: {e}")
                    db.session.rollback()

            return f"Processed {len(upcoming_reminders)} reminders"

        except Exception as e:
            logger.error(f"Error in check_upcoming_reminders: {e}")
            raise


@celery.task(bind=True, base=CallbackTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def send_event_reminder(self, user_id, event_data):
    """
    Send a WhatsApp reminder for a specific event
    """
    app = get_flask_app()
    if not app:
        logger.error("Failed to get Flask app")
        return "Failed to get Flask app"

    with app.app_context():
        try:
            logger.info(f"📤 Sending reminder to user {user_id} for event {event_data.get('id')}")
            # Import here to avoid circular imports
            from app.models.user import db, User
            from app.services.whatsapp_service import WhatsAppService

            # Get user from database
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return f"User {user_id} not found"

            # Format reminder message
            event_title = event_data.get('title', 'Event')
            minutes_before = event_data.get('minutes_before', 15)

            if user.language == 'he':
                message = f"🔔 *תזכורת לאירוע*\n\n"
                message += f"📅 {event_title}\n"
                message += f"⏰ האירוע מתחיל בעוד {minutes_before} דקות!\n\n"
                message += "שלח 'היום' לצפייה באירועי היום"
            else:
                message = f"🔔 *Event Reminder*\n\n"
                message += f"📅 {event_title}\n"
                message += f"⏰ Starting in {minutes_before} minutes!\n\n"
                message += "Send 'today' to view today's events"

            # Send WhatsApp message
            whatsapp_service = WhatsAppService()
            success = whatsapp_service.send_message(user.whatsapp_number, message)

            if success:
                logger.info(f"✅ Reminder sent to {user.whatsapp_number}")
                return f"Reminder sent successfully to {user.whatsapp_number}"
            else:
                logger.error(f"❌ Failed to send reminder to {user.whatsapp_number}")
                raise Exception("Failed to send WhatsApp message")

        except Exception as e:
            logger.error(f"Error sending reminder: {e}")
            raise


@celery.task(bind=True, base=CallbackTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def auto_sync_all_users(self):
    """
    Auto-sync calendar events for all active users
    Runs every 6 hours via Celery Beat
    """
    app = get_flask_app()
    if not app:
        logger.error("Failed to get Flask app")
        return "Failed to get Flask app"

    with app.app_context():
        try:
            logger.info("🔄 Starting auto-sync for all users...")
            # Import here to avoid circular imports
            from app.models.user import db, User

            # Get all active users with Google tokens
            active_users = User.query.filter(
                User.is_active == True,
                User.google_access_token.isnot(None)
            ).all()

            logger.info(f"Found {len(active_users)} active users to sync")

            synced_count = 0
            for user in active_users:
                try:
                    # Queue individual sync task
                    sync_user_calendar_events.delay(user.id)
                    synced_count += 1
                    logger.info(f"✅ Queued sync for user {user.whatsapp_number}")

                except Exception as e:
                    logger.error(f"❌ Failed to queue sync for user {user.id}: {e}")

            logger.info(f"🔄 Auto-sync completed: {synced_count}/{len(active_users)} users queued")
            return f"Auto-sync completed: {synced_count}/{len(active_users)} users queued"

        except Exception as e:
            logger.error(f"Error in auto_sync_all_users: {e}")
            raise


@celery.task(bind=True, base=CallbackTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 180})
def sync_user_calendar_events(self, user_id, silent=False):
    """
    Sync calendar events for a specific user and create reminders
    """
    app = get_flask_app()
    if not app:
        logger.error("Failed to get Flask app")
        return "Failed to get Flask app"

    with app.app_context():
        try:
            logger.info(f"📅 Syncing calendar events for user {user_id}")
            # Import here to avoid circular imports
            from app.models.user import db, User, ScheduledReminder
            from app.services.google_calendar import GoogleCalendarService

            # Get user from database
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return f"User {user_id} not found"

            if not user.google_access_token:
                logger.error(f"User {user_id} has no Google token")
                return f"User {user_id} has no Google token"

            # Get calendar service
            calendar_service = GoogleCalendarService()

            # Get upcoming events (next 30 days)
            end_time = datetime.utcnow() + timedelta(days=30)
            credentials = user.get_credentials()
            events, _ = calendar_service.get_upcoming_events(credentials, days=30)

            if not events:
                logger.info(f"No events found for user {user_id}")
                return f"No events found for user {user_id}"

            # Get user's reminder preferences
            prefs = user.get_notification_preferences()
            reminder_times = prefs.get_reminder_times()

            new_reminders = 0
            for event in events:
                try:
                    event_id = event.get('id')
                    event_title = event.get('summary', 'Untitled Event')

                    # Parse event start time
                    start_info = event.get('start', {})
                    if 'dateTime' in start_info:
                        event_start_time = datetime.fromisoformat(
                            start_info['dateTime'].replace('Z', '+00:00')
                        ).replace(tzinfo=None)
                    else:
                        # All-day event, skip
                        continue

                    # Skip past events
                    if event_start_time <= datetime.utcnow():
                        continue

                    # Create reminders for each time preference
                    for minutes_before in reminder_times:
                        reminder_time = event_start_time - timedelta(minutes=minutes_before)

                        # Skip if reminder time is in the past
                        if reminder_time <= datetime.utcnow():
                            continue

                        # Check if reminder already exists
                        existing_reminder = ScheduledReminder.query.filter_by(
                            user_id=user_id,
                            event_id=event_id,
                            minutes_before=minutes_before
                        ).first()

                        if not existing_reminder:
                            # Create new reminder
                            reminder = ScheduledReminder(
                                user_id=user_id,
                                event_id=event_id,
                                event_title=event_title,
                                event_start_time=event_start_time,
                                reminder_time=reminder_time,
                                minutes_before=minutes_before
                            )
                            db.session.add(reminder)
                            new_reminders += 1

                except Exception as e:
                    logger.error(f"Error processing event {event.get('id', 'unknown')}: {e}")
                    continue

            # Commit all new reminders
            try:
                db.session.commit()
                logger.info(f"✅ Created {new_reminders} new reminders for user {user_id}")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to save reminders for user {user_id}: {e}")
                raise

            return f"Sync completed: {new_reminders} new reminders created"

        except Exception as e:
            logger.error(f"Error syncing user {user_id}: {e}")
            raise


@celery.task(bind=True, base=CallbackTask, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 180})
def schedule_event_reminders(self, user_id, event_id, event_start_time_iso, minutes_before):
    """
    Schedule reminders for a specific event
    Called when events are created to set up future reminders
    """
    app = get_flask_app()
    if not app:
        logger.error("Failed to get Flask app")
        return "Failed to get Flask app"

    with app.app_context():
        try:
            from datetime import datetime, timedelta
            from app.models.user import User, ScheduledReminder, db

            logger.info(f"📅 Scheduling {minutes_before}min reminder for event {event_id}")

            # Parse event start time
            event_start_time = datetime.fromisoformat(event_start_time_iso)

            # Calculate reminder time
            reminder_time = event_start_time - timedelta(minutes=minutes_before)

            # Skip if reminder time is in the past
            if reminder_time <= datetime.utcnow():
                logger.info(f"Skipping past reminder time for event {event_id}")
                return "Reminder time is in the past"

            # Get user
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return f"User {user_id} not found"

            # Check if reminder already exists
            existing_reminder = ScheduledReminder.query.filter_by(
                user_id=user_id,
                event_id=event_id,
                minutes_before=minutes_before
            ).first()

            if existing_reminder:
                logger.info(f"Reminder already exists for event {event_id}")
                return "Reminder already exists"

            # Create new reminder
            reminder = ScheduledReminder(
                user_id=user_id,
                event_id=event_id,
                event_title=f"Event {event_id}",  # Will be updated by sync
                event_start_time=event_start_time,
                reminder_time=reminder_time,
                minutes_before=minutes_before
            )

            db.session.add(reminder)
            db.session.commit()

            logger.info(f"✅ Scheduled reminder for {reminder_time}")
            return f"Reminder scheduled for {reminder_time}"

        except Exception as e:
            logger.error(f"Error scheduling reminder: {e}")
            raise


@celery.task(bind=True, base=CallbackTask)
def send_test_reminder(self, phone_number, message="🔔 Test reminder from Calendar Bot!"):
    """
    Send a test reminder - useful for debugging
    """
    app = get_flask_app()
    if not app:
        logger.error("Failed to get Flask app")
        return "Failed to get Flask app"

    with app.app_context():
        try:
            from app.services.whatsapp_service import WhatsAppService

            whatsapp_service = WhatsAppService()
            success = whatsapp_service.send_message(phone_number, message)

            if success:
                logger.info(f"✅ Test reminder sent to {phone_number}")
                return f"Test reminder sent to {phone_number}"
            else:
                logger.error(f"❌ Failed to send test reminder to {phone_number}")
                raise Exception("Failed to send test reminder")

        except Exception as e:
            logger.error(f"Error sending test reminder: {e}")
            raise


@celery.task(bind=True, base=CallbackTask)
def debug_celery_connection(self):
    """
    Debug task to test Celery connection and basic functionality
    """
    app = get_flask_app()
    if not app:
        logger.error("Failed to get Flask app")
        return "Failed to get Flask app"

    with app.app_context():
        try:
            from app.models.user import db, User

            user_count = User.query.count()
            logger.info(f"🔧 Debug: Found {user_count} users in database")

            return f"Celery connection OK - {user_count} users found"

        except Exception as e:
            logger.error(f"Debug task failed: {e}")
            raise