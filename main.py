from flask import Flask, request, jsonify, redirect, url_for, session
from flask_migrate import Migrate
from app.models.user import db, User, MessageHistory
from app.config import Config
from app.services.google_calendar import GoogleCalendarService
from app.services.whatsapp_service import WhatsAppService
from datetime import datetime
import os
import json

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    @app.route('/debug/token')
    def debug_token():
        """Debug token loading"""
        token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        return {
            'token_present': bool(token),
            'token_length': len(token) if token else 0,
            'token_starts_with': token[:10] if token else None,
            'token_ends_with': token[-10:] if token else None
        }

    @app.route('/')
    def index():
        return "WhatsApp Calendar Bot is running!"

    @app.route('/test')
    def test_route():
        return "Hello from Flask!"

    @app.route('/webhook', methods=['GET', 'POST'])
    def webhook():
        """Handle WhatsApp webhook - verification and incoming messages"""

        if request.method == 'GET':
            # Webhook verification
            verify_token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')

            print(f"Webhook verification - Token: {verify_token}, Challenge: {challenge}")

            if verify_token == 'my_secret_verify_token_123':
                print("Webhook verified successfully!")
                return challenge
            else:
                print("Invalid verify token!")
                return 'Invalid verify token', 403

        elif request.method == 'POST':
            # Handle incoming messages
            try:
                data = request.json
                print(f"Received webhook data: {json.dumps(data, indent=2)}")

                # WhatsApp Business API format
                if 'entry' in data:
                    for entry in data['entry']:
                        if 'changes' in entry:
                            for change in entry['changes']:
                                if change.get('field') == 'messages':
                                    messages = change.get('value', {}).get('messages', [])

                                    for message in messages:
                                        phone_number = message.get('from')

                                        if message.get('type') == 'text':
                                            message_text = message.get('text', {}).get('body', '').strip().lower()

                                            print(f"Processing message from {phone_number}: {message_text}")

                                            # Process the message
                                            response_text = process_message(phone_number, message_text)

                                            # Send response
                                            whatsapp_service = WhatsAppService()
                                            success = whatsapp_service.send_message(phone_number, response_text)

                                            print(f"Response sent: {success}")

                return jsonify({'status': 'success'})

            except Exception as e:
                print(f"Webhook error: {e}")
                return jsonify({'status': 'error', 'message': str(e)})

    @app.route('/auth/login/<path:phone_number>')
    def auth_login(phone_number):
        """Initiate Google OAuth flow for a WhatsApp user"""
        phone_number = phone_number.replace('%2B', '+')

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
            user.timezone = 'Asia/Jerusalem'
            db.session.commit()

            return f"""
            <html>
            <body>
                <h1>✅ Calendar Connected Successfully!</h1>
                <p>Your WhatsApp number <strong>{phone_number}</strong> is now connected to Google Calendar.</p>
                <p>Timezone set to: <strong>Asia/Jerusalem</strong></p>
                <p>You can now use calendar commands in WhatsApp!</p>
                <p>Try sending: <strong>today</strong> or <strong>upcoming</strong></p>
            </body>
            </html>
            """

        except Exception as e:
            print(f"OAuth callback error: {e}")
            return f"Authorization failed: {str(e)}", 400

    @app.route('/test/calendar/<path:phone_number>')
    def test_calendar(phone_number):
        """Test calendar integration for a user"""
        phone_number = phone_number.replace('%2B', '+')

        user = User.query.filter_by(whatsapp_number=phone_number).first()

        if not user or not user.google_access_token:
            return f"User {phone_number} not found or not connected to Google Calendar"

        calendar_service = GoogleCalendarService()
        events, updated_credentials = calendar_service.get_today_events(user.get_credentials(), user.timezone)

        if updated_credentials:
            # Update tokens if they were refreshed
            user.google_access_token = updated_credentials.token
            if updated_credentials.expiry:
                user.token_expiry = updated_credentials.expiry
            db.session.commit()

        formatted_message = calendar_service.format_events_for_whatsapp(events)

        return f"<pre>{formatted_message}</pre>"

    @app.route('/test/send-message/<path:phone_number>')
    def test_send_message(phone_number):
        """Test sending a WhatsApp message"""
        phone_number = phone_number.replace('%2B', '+')

        whatsapp_service = WhatsAppService()
        success = whatsapp_service.test_send_message(phone_number)

        if success:
            return f"✅ Test message sent to {phone_number}!"
        else:
            return f"❌ Failed to send message to {phone_number}"

    return app

def process_message(phone_number, message_text):
    """Process incoming message and return response"""
    print(f"Processing: {message_text} from {phone_number}")

    if message_text == 'today':
        return handle_today_command(phone_number)
    elif message_text == 'upcoming':
        return handle_upcoming_command(phone_number)
    elif message_text == 'connect':
        return handle_connect_command(phone_number)
    elif message_text == 'status':
        return check_user_status(phone_number)
    elif message_text == 'hello':
        return "Hello! I'm your WhatsApp Calendar Bot. Type 'help' for commands."
    elif message_text == 'help':
        return """📅 *Calendar Bot Commands*

• *connect* - Link your Google Calendar
• *today* - Get today's events
• *upcoming* - Get this week's events
• *status* - Check connection status
• *help* - Show this message

First, send *connect* to link your calendar!"""
    else:
        return f"Unknown command: '{message_text}'\nType 'help' for available commands."

def get_base_url():
    """Get the base URL (ngrok or localhost)"""
    # You can set this as an environment variable
    return os.getenv('BASE_URL', 'http://localhost:5000')

def handle_connect_command(phone_number):
    """Handle connect command"""
    base_url = get_base_url()
    auth_url = f"{base_url}/auth/login/{phone_number}"
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