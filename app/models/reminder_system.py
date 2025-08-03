"""
Database Schema Updates for Reminder System
"""

from app.models.user import db
from datetime import datetime
import json

class ReminderHistory(db.Model):
    """Track sent reminders to prevent duplicates"""
    __tablename__ = 'reminder_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.String(255), nullable=False)  # Google Calendar event ID
    event_title = db.Column(db.String(500), nullable=True)
    event_start_time = db.Column(db.DateTime, nullable=False)
    reminder_type = db.Column(db.String(50), nullable=False)  # '15min', '1hour', 'day_before'
    reminder_minutes = db.Column(db.Integer, nullable=False)  # Minutes before event
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    message_id = db.Column(db.String(255), nullable=True)  # WhatsApp message ID
    status = db.Column(db.String(50), nullable=False, default='sent')  # 'sent', 'failed', 'delivered'

    # Relationship
    user = db.relationship('User', backref=db.backref('reminder_history', lazy=True))

    def __repr__(self):
        return f'<ReminderHistory {self.user_id}:{self.event_id}:{self.reminder_type}>'

class NotificationPreferences(db.Model):
    """User notification preferences"""
    __tablename__ = 'notification_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Reminder timing
    reminder_times = db.Column(db.Text, nullable=False, default='[15]')  # JSON list of minutes before

    # Quiet hours
    quiet_hours_enabled = db.Column(db.Boolean, nullable=False, default=True)
    quiet_hours_start = db.Column(db.String(5), nullable=False, default='22:00')
    quiet_hours_end = db.Column(db.String(5), nullable=False, default='07:00')

    # Weekend settings
    weekend_reminders = db.Column(db.Boolean, nullable=False, default=True)

    # Event type filters
    work_events = db.Column(db.Boolean, nullable=False, default=True)
    personal_events = db.Column(db.Boolean, nullable=False, default=True)
    appointment_events = db.Column(db.Boolean, nullable=False, default=True)

    # Advanced settings
    max_reminders_per_day = db.Column(db.Integer, nullable=False, default=50)
    reminder_language = db.Column(db.String(5), nullable=True)  # Override user language for reminders

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = db.relationship('User', backref=db.backref('notification_preferences', uselist=False))

    def get_reminder_times(self):
        """Get reminder times as Python list"""
        try:
            return json.loads(self.reminder_times)
        except (json.JSONDecodeError, TypeError):
            return [15]  # Default fallback

    def set_reminder_times(self, times_list):
        """Set reminder times from Python list"""
        self.reminder_times = json.dumps(times_list)

    def __repr__(self):
        return f'<NotificationPreferences {self.user_id}>'

class EventCache(db.Model):
    """Cache calendar events for efficient reminder processing"""
    __tablename__ = 'event_cache'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.String(255), nullable=False)  # Google Calendar event ID
    calendar_id = db.Column(db.String(255), nullable=False)

    # Event details
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(500), nullable=True)

    # Timing
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    timezone = db.Column(db.String(50), nullable=False)

    # Event metadata
    event_type = db.Column(db.String(50), nullable=True)  # 'work', 'personal', 'appointment'
    attendees_count = db.Column(db.Integer, nullable=False, default=0)
    is_recurring = db.Column(db.Boolean, nullable=False, default=False)

    # Cache metadata
    last_synced = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    sync_version = db.Column(db.String(100), nullable=True)  # Google Calendar etag

    # Status
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Relationship
    user = db.relationship('User', backref=db.backref('cached_events', lazy=True))

    # Indexes for efficient queries
    __table_args__ = (
        db.Index('idx_user_start_time', 'user_id', 'start_time'),
        db.Index('idx_event_lookup', 'user_id', 'event_id'),
        db.Index('idx_reminder_lookup', 'start_time', 'is_active'),
    )

    def __repr__(self):
        return f'<EventCache {self.user_id}:{self.event_id}:{self.title}>'

# Helper functions to integrate with User model
def add_user_reminder_methods():
    """Add reminder-related methods to User model"""

    def get_notification_preferences(self):
        """Get user's notification preferences, creating default if needed"""
        if not self.notification_preferences:
            # Create default preferences
            prefs = NotificationPreferences(user_id=self.id)
            db.session.add(prefs)
            db.session.commit()
        return self.notification_preferences

    def should_send_reminder(self, event_start_time):
        """Check if reminder should be sent based on user preferences"""
        prefs = self.get_notification_preferences()

        # Check quiet hours
        if prefs.quiet_hours_enabled:
            now = datetime.now()
            current_time = now.strftime('%H:%M')

            if prefs.quiet_hours_start <= prefs.quiet_hours_end:
                # Normal case: 22:00 to 07:00
                if prefs.quiet_hours_start <= current_time <= prefs.quiet_hours_end:
                    return False
            else:
                # Overnight case: 23:00 to 06:00
                if current_time >= prefs.quiet_hours_start or current_time <= prefs.quiet_hours_end:
                    return False

        # Check weekend settings
        if not prefs.weekend_reminders and event_start_time.weekday() in [5, 6]:  # Saturday, Sunday
            return False

        return True

    def get_reminder_language(self):
        """Get language for reminders"""
        prefs = self.get_notification_preferences()
        return prefs.reminder_language or self.language or 'en'

    # Add methods to User class (you'll need to add these to your actual User model)
    return {
        'get_notification_preferences': get_notification_preferences,
        'should_send_reminder': should_send_reminder,
        'get_reminder_language': get_reminder_language
    }

def create_reminder_tables():
    """Create reminder tables - run this once to set up"""
    try:
        # Create all new tables
        db.create_all()

        # Create default notification preferences for existing users
        from app.models.user import User
        users_without_prefs = User.query.outerjoin(NotificationPreferences).filter(
            NotificationPreferences.id == None
        ).all()

        for user in users_without_prefs:
            prefs = NotificationPreferences(user_id=user.id)
            db.session.add(prefs)

        db.session.commit()
        print(f"✅ Created notification preferences for {len(users_without_prefs)} existing users")

        return True
    except Exception as e:
        print(f"❌ Error creating reminder tables: {e}")
        db.session.rollback()
        return False