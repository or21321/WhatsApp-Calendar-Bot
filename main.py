from flask import Flask, request, jsonify, redirect, url_for, session
from flask_migrate import Migrate
from app.models.user import db, User, MessageHistory
from app.config import Config
from app.services.google_calendar import GoogleCalendarService
from datetime import datetime
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

            if data and 'messages' in data:
                for message in data['messages']:
                    phone_number = message.get('from')
                    message_text = message.get('text', {}).get('body', '').strip().lower()

                    print(f"Message from {phone_number}: {message_text}")

                    # Handle calendar commands
                    if message_text == 'today':
                        response = handle_today_command(phone_number)
                    elif message_text == 'upcoming':
                        response = handle_upcoming_command(phone_number)
                    elif message_text == 'connect':
                        response = handle_connect_command(phone_number)
                    elif message_text == 'hello':
                        response = "Hello! I'm your WhatsApp Calendar Bot. Type 'help' for commands."
                    elif message_text == 'help':
                        response = """📅 *Calendar Bot Commands*

• *connect* - Link your Google Calendar
• *today* - Get today's events
• *upcoming* - Get this week's events
• *status* - Check connection status
• *help* - Show this message

First, send *connect* to link your calendar!"""
                    elif message_text == 'status':
                        response = check_user_status(phone_number)
                    else:
                        response = f"Unknown command: {message_text}\nType 'help' for available commands."

                    print(f"Sending response: {response}")

            return jsonify({'status': 'success'})

        except Exception as e:
            print(f"Webhook error: {e}")
            return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/auth/login/<phone_number>')
    def auth_login(phone_number):
        """Initiate Google OAuth flow for a WhatsApp user"""
        calendar_service = GoogleCalendarService()
        auth_url, state = calendar_service.get_authorization_url(state=phone_number)

        # Store the state in session or database
        session['oauth_state'] = state
        session['phone_number'] = phone_number

        return redirect(auth_url)

    @app.route('/auth/callback')
    def auth_callback():
        """Handle Google OAuth callback"""
        try:
            code = request.args.get('code')
            state = request.args.get('state')

            if not code:
                return "Authorization failed - no code received", 400

            # Get phone number from state
            phone_number = state  # We passed phone_number as state

            # Exchange code for tokens
            calendar_service = GoogleCalendarService()
            tokens = calendar_service.exchange_code_for_tokens(code, state)

            # Save or update user in database
            user = User.query.filter_by(whatsapp_number=phone_number).first()
            if not user:
                user = User(whatsapp_number=phone_number)
                db.session.add(user)

            user.google_access_token = tokens['access_token']
            user.google_refresh_token = tokens['refresh_token']
            user.token_expiry = tokens['token_expiry']
            db.session.commit()

            return f"""
            <html>
            <body>
                <h1>✅ Calendar Connected Successfully!</h1>
                <p>Your WhatsApp number <strong>{phone_number}</strong> is now connected to Google Calendar.</p>
                <p>You can now use calendar commands in WhatsApp!</p>
                <p>Try sending: <strong>today</strong> or <strong>upcoming</strong></p>
            </body>
            </html>
            """

        except Exception as e:
            print(f"OAuth callback error: {e}")
            return f"Authorization failed: {str(e)}", 400

    @app.route('/test/calendar/<phone_number>')
    def test_calendar(phone_number):
        """Test calendar integration for a user"""
        user = User.query.filter_by(whatsapp_number=phone_number).first()

        if not user or not user.google_access_token:
            return f"User {phone_number} not found or not connected to Google Calendar"

        calendar_service = GoogleCalendarService()
        events, updated_credentials = calendar_service.get_today_events(user.get_credentials())

        if updated_credentials:
            # Update tokens if they were refreshed
            user.google_access_token = updated_credentials.token
            if updated_credentials.expiry:
                user.token_expiry = updated_credentials.expiry
            db.session.commit()

        formatted_message = calendar_service.format_events_for_whatsapp(events)

        return f"<pre>{formatted_message}</pre>"

    return app

def handle_connect_command(phone_number):
    """Handle connect command"""
    auth_url = f"http://localhost:5000/auth/login/{phone_number}"
    return f"""🔗 *Connect Your Google Calendar*

Click this link to authorize calendar access:
{auth_url}

After clicking, you'll be redirected to Google to sign in and grant permissions."""

def handle_today_command(phone_number):
    """Handle today command"""
    user = User.query.filter_by(whatsapp_number=phone_number).first()

    if not user or not user.google_access_token:
        return "❌ Please connect your Google Calendar first. Send 'connect' to get started."

    calendar_service = GoogleCalendarService()
    events, updated_credentials = calendar_service.get_today_events(
        user.get_credentials(),
        user.timezone
    )

    if updated_credentials:
        user.google_access_token = updated_credentials.token
        if updated_credentials.expiry:
            user.token_expiry = updated_credentials.expiry
        db.session.commit()

    return calendar_service.format_events_for_whatsapp(events)

def handle_upcoming_command(phone_number):
    """Handle upcoming command"""
    user = User.query.filter_by(whatsapp_number=phone_number).first()

    if not user or not user.google_access_token:
        return "❌ Please connect your Google Calendar first. Send 'connect' to get started."

    calendar_service = GoogleCalendarService()
    events_by_date, updated_credentials = calendar_service.get_upcoming_events(
        user.get_credentials(),
        days=7,
        timezone=user.timezone
    )

    if updated_credentials:
        user.google_access_token = updated_credentials.token
        if updated_credentials.expiry:
            user.token_expiry = updated_credentials.expiry
        db.session.commit()

    return calendar_service.format_upcoming_events_for_whatsapp(events_by_date)

def check_user_status(phone_number):
    """Check user's connection status"""
    user = User.query.filter_by(whatsapp_number=phone_number).first()

    if not user:
        return "❌ Not registered. Send 'connect' to get started."

    if not user.google_access_token:
        return "❌ Google Calendar not connected. Send 'connect' to link your calendar."

    return f"✅ Connected to Google Calendar\n📍 Timezone: {user.timezone}\n📅 Ready to fetch events!"

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)