from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    whatsapp_number = db.Column(db.String(20), unique=True, nullable=False)
    google_access_token = db.Column(db.Text)
    google_refresh_token = db.Column(db.Text)
    token_expiry = db.Column(db.DateTime)
    timezone = db.Column(db.String(50), default='UTC')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    language = db.Column(db.String(5), default='auto')  # 'en', 'he', 'auto'

    # Conversation state for multi-turn interactions
    conversation_state = db.Column(db.Text)  # JSON string for conversation data
    conversation_step = db.Column(db.String(50))  # Current conversation step
    conversation_updated = db.Column(db.DateTime)  # When conversation was last updated

    # Notification preferences
    reminder_times = db.Column(db.Text, default='[15]')  # JSON array of minutes before event
    quiet_hours_enabled = db.Column(db.Boolean, default=True)
    quiet_hours_start = db.Column(db.String(5), default='22:00')
    quiet_hours_end = db.Column(db.String(5), default='07:00')
    weekend_reminders = db.Column(db.Boolean, default=True)

    def get_credentials(self):
        return {
            'access_token': self.google_access_token,
            'refresh_token': self.google_refresh_token,
            'token_expiry': self.token_expiry
        }

    def set_conversation_state(self, step, data=None):
        """Set conversation state"""
        self.conversation_step = step
        self.conversation_state = json.dumps(data) if data else None
        self.conversation_updated = datetime.utcnow()
        db.session.commit()

    def get_conversation_state(self):
        """Get conversation state data"""
        if self.conversation_state:
            try:
                return json.loads(self.conversation_state)
            except:
                return None
        return None

    def clear_conversation_state(self):
        """Clear conversation state"""
        self.conversation_step = None
        self.conversation_state = None
        self.conversation_updated = None
        db.session.commit()

    def is_conversation_expired(self, timeout_minutes=30):
        """Check if conversation has expired"""
        if not self.conversation_updated:
            return True

        time_diff = datetime.utcnow() - self.conversation_updated
        return time_diff.total_seconds() > (timeout_minutes * 60)

    def get_notification_preferences(self):
        """Get notification preferences object"""
        return NotificationPreferences(self)


class NotificationPreferences:
    """Helper class for managing user notification preferences"""

    def __init__(self, user):
        self.user = user

    def get_reminder_times(self):
        """Get list of reminder times in minutes before event"""
        try:
            if self.user.reminder_times:
                return json.loads(self.user.reminder_times)
            else:
                return [15]  # Default 15 minutes
        except (json.JSONDecodeError, TypeError):
            return [15]

    def set_reminder_times(self, times_list):
        """Set reminder times"""
        self.user.reminder_times = json.dumps(times_list)
        db.session.commit()

    @property
    def quiet_hours_enabled(self):
        return self.user.quiet_hours_enabled

    @property
    def quiet_hours_start(self):
        return self.user.quiet_hours_start

    @property
    def quiet_hours_end(self):
        return self.user.quiet_hours_end

    @property
    def weekend_reminders(self):
        return self.user.weekend_reminders

    def set_quiet_hours(self, enabled, start_time=None, end_time=None):
        """Set quiet hours settings"""
        self.user.quiet_hours_enabled = enabled
        if start_time:
            self.user.quiet_hours_start = start_time
        if end_time:
            self.user.quiet_hours_end = end_time
        db.session.commit()

    def set_weekend_reminders(self, enabled):
        """Enable/disable weekend reminders"""
        self.user.weekend_reminders = enabled
        db.session.commit()


class ScheduledReminder(db.Model):
    """Track scheduled reminders for events"""
    __tablename__ = 'scheduled_reminders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.String(255), nullable=False)  # Google Calendar event ID
    event_title = db.Column(db.String(500))
    event_start_time = db.Column(db.DateTime, nullable=False)
    reminder_time = db.Column(db.DateTime, nullable=False)  # When to send reminder
    minutes_before = db.Column(db.Integer, nullable=False)  # How many minutes before event
    sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to user
    user = db.relationship('User', backref=db.backref('scheduled_reminders', lazy=True))

    def __repr__(self):
        return f'<ScheduledReminder {self.event_title} at {self.reminder_time}>'


class MessageHistory(db.Model):
    __tablename__ = 'message_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20))  # 'incoming', 'outgoing', 'system'
    conversation_step = db.Column(db.String(50))  # What step was user in
    created_at = db.Column(db.DateTime, default=datetime.utcnow)