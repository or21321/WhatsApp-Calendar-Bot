from flask import Flask, request, jsonify, redirect, url_for, session
from flask_migrate import Migrate
from app.models.user import db, User
from app.config import Config
import os
import json

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    @app.route('/')
    def index():
        return "WhatsApp Calendar Bot is running!"

    @app.route('/webhook', methods=['POST'])
    def webhook():
        """Handle incoming WhatsApp messages"""
        try:
            data = request.json
            print(f"Received webhook data: {data}")

            # Simple echo response for testing
            if data and 'messages' in data:
                for message in data['messages']:
                    phone_number = message.get('from')
                    message_text = message.get('text', {}).get('body', '')

                    print(f"Message from {phone_number}: {message_text}")

                    # Simple response logic
                    if message_text.lower() == 'hello':
                        response = "Hello! I'm your WhatsApp Calendar Bot. Type 'help' for commands."
                    elif message_text.lower() == 'help':
                        response = """Available commands:
- hello - Say hello
- status - Check bot status
- today - Get today's events (coming soon)
- help - Show this message"""
                    elif message_text.lower() == 'status':
                        response = "Bot is running and ready!"
                    else:
                        response = f"You said: {message_text}. Type 'help' for available commands."

                    print(f"Sending response: {response}")

            return jsonify({'status': 'success'})

        except Exception as e:
            print(f"Webhook error: {e}")
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/auth/login')
    def auth_login():
        """Initiate Google OAuth flow"""
        # This will be implemented in the next part
        return "Google OAuth login coming soon!"

    @app.route('/auth/callback')
    def auth_callback():
        """Handle Google OAuth callback"""
        # This will be implemented in the next part
        return "OAuth callback handler coming soon!"

    return app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)