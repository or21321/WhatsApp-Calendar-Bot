from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

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

    def get_credentials(self):
        return {
            'access_token': self.google_access_token,
            'refresh_token': self.google_refresh_token,
            'token_expiry': self.token_expiry
        }

class MessageHistory(db.Model):
    __tablename__ = 'message_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)