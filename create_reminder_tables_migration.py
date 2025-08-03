"""
Script to create a migration for the reminder system tables
"""

from main import create_app
from flask_migrate import Migrate, migrate
from app.models.user import db, User, ScheduledReminder, MessageHistory
from app.models.reminder_system import ReminderHistory, NotificationPreferences, EventCache
import logging

# Initialize app and migrate
app = create_app()
migrate = Migrate(app, db)

if __name__ == '__main__':
    with app.app_context():
        print("Current tables in database:", db.metadata.tables.keys())
        print("""
To create a migration for these models, run:
flask db migrate -m "Add reminder system tables"
flask db upgrade

This will add the following tables to the database:
- reminder_history
- notification_preferences
- event_cache
        """)