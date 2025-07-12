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

class MessageHistory(db.Model):
    __tablename__ = 'message_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20))  # 'incoming', 'outgoing', 'system'
    conversation_step = db.Column(db.String(50))  # What step was user in
    created_at = db.Column(db.DateTime, default=datetime.utcnow)