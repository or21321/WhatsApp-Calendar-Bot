"""
Script to create a migration for the reminder system tables
"""

from main import create_app
from app.models.user import db
from flask_migrate import Migrate, migrate

# Import all models to ensure they're recognized for migrations
from app.models.user import User, ScheduledReminder, MessageHistory

# Import models from reminder-system.py
# These need to be imported so the migration can detect them
from app.models.reminder_system import ReminderHistory, NotificationPreferences, EventCache

app = create_app()
migrate = Migrate(app, db)

if __name__ == '__main__':
    with app.app_context():
        print("Creating migration for reminder system tables...")
        # This would normally be run with the command: flask db migrate -m "Add reminder system tables"
        # But we're simulating it here for checking purposes
        print("Migration would include tables:", db.metadata.tables.keys())