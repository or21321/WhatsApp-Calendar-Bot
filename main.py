from flask import Flask, request, jsonify, redirect, url_for, session
from flask_migrate import Migrate
from app.models.user import db, User, MessageHistory
from app.config import Config
from app.services.google_calendar import GoogleCalendarService
from app.services.whatsapp_service import WhatsAppService
from app.services.nlp_service import SmartEventParser
from datetime import datetime, timedelta
import os
import json
import re

# Helper functions BEFORE create_app()

def make_json_serializable(parsed_event):
    """Convert datetime objects to strings for JSON serialization"""
    if not parsed_event:
        return None

    # Create a copy to avoid modifying original
    serializable_event = parsed_event.copy()

    # Convert datetime objects to ISO strings
    if 'start_time' in serializable_event and hasattr(serializable_event['start_time'], 'isoformat'):
        serializable_event['start_time'] = serializable_event['start_time'].isoformat()

    if 'end_time' in serializable_event and hasattr(serializable_event['end_time'], 'isoformat'):
        serializable_event['end_time'] = serializable_event['end_time'].isoformat()

    return serializable_event

def make_json_deserializable(parsed_event):
    """Convert ISO strings back to datetime objects"""
    if not parsed_event:
        return None

    # Create a copy to avoid modifying original
    event = parsed_event.copy()

    # Convert ISO strings back to datetime objects
    if 'start_time' in event and isinstance(event['start_time'], str):
        event['start_time'] = datetime.fromisoformat(event['start_time'])

    if 'end_time' in event and isinstance(event['end_time'], str):
        event['end_time'] = datetime.fromisoformat(event['end_time'])

    return event

def should_try_nlp(message_text):
    """Determine if message should be processed with NLP for event creation"""

    # Don't try NLP for very short messages
    if len(message_text.split()) < 3:
        return False

    # Don't try NLP for messages that are clearly not events
    non_event_patterns = [
        r'^(what|when|where|how|why|who)',  # Questions
        r'^(yes|no|ok|okay|thanks|thank you)',  # Simple responses
        r'^\d+$',  # Just numbers
        r'^[a-z]$',  # Single letters
    ]

    message_lower = message_text.lower()
    for pattern in non_event_patterns:
        if re.match(pattern, message_lower):
            return False

    # Strong event indicators (definitely try NLP)
    strong_indicators = [
        'meeting', 'appointment', 'call', 'lunch', 'dinner', 'coffee',
        'schedule', 'book', 'plan', 'create', 'add', 'set up',
        'doctor', 'dentist', 'interview', 'presentation', 'demo',
        'standup', 'review', 'workout', 'gym', 'party', 'event'
    ]

    if any(indicator in message_lower for indicator in strong_indicators):
        return True

    # Time/date indicators (likely an event if combined with other words)
    time_indicators = [
        'tomorrow', 'today', 'tonight', 'morning', 'afternoon', 'evening',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'next week', 'this week', 'next month', 'next monday', 'this friday',
        'am', 'pm', 'o\'clock'
    ]

    # If has time indicator + person/organization names, likely an event
    if any(indicator in message_lower for indicator in time_indicators):
        # Check for person indicators
        person_indicators = ['with', 'and', 'john', 'sarah', 'mike', 'team', 'client', 'boss']
        if any(person in message_lower for person in person_indicators):
            return True

        # Check for action words
        action_words = ['meet', 'see', 'visit', 'go to', 'attend']
        if any(action in message_lower for action in action_words):
            return True

    # If message has time patterns (2pm, 9:30am, etc.)
    time_patterns = [
        r'\d{1,2}:\d{2}\s*(am|pm)',
        r'\d{1,2}\s*(am|pm)',
        r'\d{1,2}-\d{1,2}\s*(am|pm)',
    ]

    for pattern in time_patterns:
        if re.search(pattern, message_lower):
            return True

    # Default: don't try NLP
    return False

def handle_conversation_flow(user, message_text):
    """Handle multi-turn conversations (confirmations, clarifications)"""

    # Check if conversation has expired
    if user.is_conversation_expired():
        user.clear_conversation_state()
        return None

    step = user.conversation_step
    conversation_data = user.get_conversation_state()

    print(f"🔥 CONVERSATION STEP: {step}")
    print(f"🔥 CONVERSATION DATA: {conversation_data}")

    if step == 'confirm_event':
        return handle_event_confirmation(user, message_text, conversation_data)
    elif step == 'choose_calendar':
        return handle_calendar_selection(user, message_text, conversation_data)
    elif step == 'edit_event':
        return handle_event_editing(user, message_text, conversation_data)

    return None

def handle_event_confirmation(user, message_text, conversation_data):
    """Handle yes/no confirmation for event creation"""
    message_lower = message_text.lower().strip()

    if message_lower in ['yes', 'y', 'confirm', 'create', 'ok', 'okay']:
        # User confirmed - create the event
        serializable_event = conversation_data.get('parsed_event')
        selected_calendar = conversation_data.get('selected_calendar')

        if serializable_event:
            # Convert back from JSON-serializable format
            parsed_event = make_json_deserializable(serializable_event)

            if selected_calendar:
                # Create in pre-selected calendar
                result = create_event_in_specific_calendar(user, parsed_event, selected_calendar)
            else:
                # Create in default calendar
                result = create_event_from_confirmation(user, parsed_event)

            user.clear_conversation_state()
            return result
        else:
            user.clear_conversation_state()
            return "❌ Error: Event data was lost. Please try creating the event again."

    # ... rest of the function stays the same

def handle_calendar_selection(user, message_text, conversation_data):
    """Handle calendar selection when user has multiple calendars"""

    # Check if user is trying to create a new event instead of selecting calendar
    if should_try_nlp(message_text):
        print("🔥 User sent new event request while in calendar selection - processing as new event")
        # Clear conversation state and process as new event
        user.clear_conversation_state()
        return try_nlp_event_creation(user, message_text)

    try:
        # Try to parse as number
        selection = int(message_text.strip())
        calendars = conversation_data.get('calendars', [])

        if 1 <= selection <= len(calendars):
            selected_calendar = calendars[selection - 1]
            serializable_event = conversation_data.get('parsed_event')
            parsed_event = make_json_deserializable(serializable_event)

            # Create event in selected calendar
            result = create_event_in_specific_calendar(user, parsed_event, selected_calendar)
            user.clear_conversation_state()
            return result
        else:
            return f"❌ Please enter a number between 1 and {len(calendars)}"

    except ValueError:
        message_lower = message_text.lower().strip()
        if message_lower in ['cancel', 'back']:
            user.clear_conversation_state()
            return "❌ Calendar selection cancelled."

        calendars = conversation_data.get('calendars', [])
        calendar_list = "\n".join([f"{i+1}. {cal['name']}" for i, cal in enumerate(calendars)])
        return f"❌ Please enter a number to select a calendar:\n\n{calendar_list}"

def handle_event_editing(user, message_text, conversation_data):
    """Handle event editing requests"""
    # This is a simplified version - you could make this much more sophisticated
    user.clear_conversation_state()
    return "✏️ Event editing is coming soon! For now, please create a new event with the correct details."

def find_matching_calendar(requested_name, calendars):
    """Find calendar that matches the requested name"""
    requested_lower = requested_name.lower().strip()

    print(f"🔍 Looking for calendar: '{requested_name}' (lowered: '{requested_lower}') in {len(calendars)} calendars")

    # Try exact match first
    for calendar in calendars:
        calendar_lower = calendar['name'].lower().strip()
        print(f"🔍 Checking exact: '{calendar['name']}' (lowered: '{calendar_lower}')")
        print(f"🔍 Comparison: '{requested_lower}' == '{calendar_lower}' ? {requested_lower == calendar_lower}")

        if calendar_lower == requested_lower:
            print(f"✅ Exact match found: {calendar['name']}")
            return calendar

    # Try exact match without extra spaces and normalization
    for calendar in calendars:
        # Normalize both strings - remove extra spaces, normalize unicode
        cal_normalized = ' '.join(calendar['name'].lower().split())
        req_normalized = ' '.join(requested_lower.split())

        print(f"🔍 Normalized check: '{req_normalized}' == '{cal_normalized}' ? {req_normalized == cal_normalized}")

        if cal_normalized == req_normalized:
            print(f"✅ Normalized exact match found: {calendar['name']}")
            return calendar

    # Try partial matching only as last resort
    for calendar in calendars:
        calendar_lower = calendar['name'].lower()
        if (len(requested_lower) >= 3 and
            requested_lower in calendar_lower and
            len(requested_lower) >= len(calendar_lower) * 0.7):  # Must be at least 70% of calendar name
            print(f"✅ Significant partial match found: {calendar['name']}")
            return calendar

    print(f"❌ No match found for: '{requested_name}'")
    return None

def show_calendar_not_found(user, parsed_event, requested_name, calendars):
    """Show message when requested calendar is not found"""

    calendar_list = ""
    for i, calendar in enumerate(calendars, 1):
        primary_indicator = " 🔹" if calendar.get('primary') else ""
        calendar_list += f"{i}. {calendar['name']}{primary_indicator}\n"

    serializable_event = make_json_serializable(parsed_event)
    user.set_conversation_state('choose_calendar', {
        'parsed_event': serializable_event,
        'calendars': calendars
    })

    event_title = parsed_event['title']
    event_time = format_event_time(parsed_event)

    message = "❌ *Calendar \"" + requested_name + "\" not found*\n\n"
    message += "📝 *" + event_title + "*\n"
    message += "📅 " + event_time + "\n\n"
    message += "*Available Calendars:*\n"
    message += calendar_list
    message += "Reply with the number (1, 2, 3...) to select\n\n"
    message += "_🔹 = Primary Calendar_"

    return message

def try_nlp_event_creation(user, message_text):
    """Try to create event using NLP parsing"""

    try:
        # Parse with NLP
        parser = SmartEventParser()
        parsed_event = parser.parse_event(message_text, user.timezone)

        if not parsed_event:
            return None

        confidence = parsed_event['confidence']

        # Get user's calendars
        calendar_service = GoogleCalendarService()
        calendars, _ = calendar_service.get_user_calendars(user.get_credentials())
        writable_calendars = [cal for cal in calendars if cal['access_role'] in ['owner', 'writer']]

        print(f"🔥 Found {len(writable_calendars)} writable calendars")

        # Check if user specified a calendar in the message
        requested_calendar_name = parser.extract_calendar_name(message_text)
        selected_calendar = None

        if requested_calendar_name:
            print(f"🔥 User requested calendar: '{requested_calendar_name}'")
            selected_calendar = find_matching_calendar(requested_calendar_name, writable_calendars)

            if selected_calendar:
                print(f"🔥 Found matching calendar: {selected_calendar['name']}")
                # Create event directly in specified calendar
                return create_event_in_specific_calendar(user, parsed_event, selected_calendar)
            else:
                print(f"🔥 Calendar '{requested_calendar_name}' not found")
                # Calendar not found - show available calendars
                return show_calendar_not_found(user, parsed_event, requested_calendar_name, writable_calendars)

        # No specific calendar requested - check for multiple calendars
        if len(writable_calendars) > 1:
            print("🔥 Multiple calendars detected - asking for selection")
            return ask_calendar_selection(user, parsed_event, writable_calendars)

        # Single calendar - use confidence-based flow
        print("🔥 Single calendar - using confidence-based flow")
        if confidence >= 80:
            return create_event_automatically(user, parsed_event, writable_calendars)
        elif confidence >= 50:
            return ask_for_confirmation(user, parsed_event)
        elif confidence >= 30:
            return show_understanding_and_ask(user, parsed_event)
        else:
            return None

    except Exception as e:
        print(f"NLP parsing error: {e}")
        return None

def handle_high_confidence_event(user, parsed_event):
    """Handle high confidence events - check for multiple calendars"""
    try:
        calendar_service = GoogleCalendarService()
        calendars, _ = calendar_service.get_user_calendars(user.get_credentials())
        writable_calendars = [cal for cal in calendars if cal['access_role'] in ['owner', 'writer']]

        if len(writable_calendars) <= 1:
            # Single calendar - create directly
            return create_event_automatically(user, parsed_event, writable_calendars)
        else:
            # Multiple calendars - ask user to choose
            return ask_calendar_selection(user, parsed_event, writable_calendars)

    except Exception as e:
        print(f"Error handling high confidence event: {e}")
        return "❌ Error accessing your calendars. Please try again."

def ask_calendar_selection(user, parsed_event, calendars):
    """Ask user to select calendar for high-confidence event"""
    serializable_event = make_json_serializable(parsed_event)
    serializable_calendars = calendars  # Calendars are already JSON-serializable

    user.set_conversation_state('choose_calendar', {
        'parsed_event': serializable_event,
        'calendars': serializable_calendars
    })

    calendar_list = ""
    for i, calendar in enumerate(calendars, 1):
        primary_indicator = " 🔹" if calendar.get('primary') else ""
        calendar_list += f"{i}. {calendar['name']}{primary_indicator}\n"

    return f'''📂 *Choose Calendar for Your Event:*

📝 *{parsed_event['title']}*
📅 {format_event_time(parsed_event)}

*Available Calendars:*
{calendar_list}
Reply with the number (1, 2, 3...) to select

_🔹 = Primary Calendar_'''

def create_event_automatically(user, parsed_event, calendars):
    """Create event automatically with high confidence"""
    try:
        calendar_service = GoogleCalendarService()

        # Use primary calendar or first available
        calendar_id = 'primary'
        calendar_name = 'Primary Calendar'

        if calendars:
            for cal in calendars:
                if cal.get('primary'):
                    calendar_id = cal['id']
                    calendar_name = cal['name']
                    break
            else:
                calendar_id = calendars[0]['id']
                calendar_name = calendars[0]['name']

        # Create the event
        event_id, updated_credentials = calendar_service.create_event_in_calendar(
            user.get_credentials(),
            parsed_event,
            calendar_id,
            user.timezone
        )

        # Update user credentials if refreshed
        if updated_credentials:
            user.google_access_token = updated_credentials.token
            if updated_credentials.expiry:
                user.token_expiry = updated_credentials.expiry
            db.session.commit()

        if event_id:
            return f'''🎉 *Event Created Successfully!*

📝 *{parsed_event['title']}*
📅 {format_event_time(parsed_event)}
📍 {parsed_event['location'] if parsed_event['location'] else 'No location'}
📂 {calendar_name}

✨ _Created automatically with {parsed_event['confidence']}% confidence_'''
        else:
            return "❌ Failed to create event. Please try again or check your permissions."

    except Exception as e:
        print(f"Error creating event automatically: {e}")
        return "❌ Error creating event. Please try again."

def create_event_from_confirmation(user, parsed_event):
    """Create event after user confirmation"""
    try:
        calendar_service = GoogleCalendarService()
        calendars, _ = calendar_service.get_user_calendars(user.get_credentials())

        # Use primary calendar or first available
        calendar_id = 'primary'
        calendar_name = 'Primary Calendar'

        if calendars:
            for cal in calendars:
                if cal.get('primary'):
                    calendar_id = cal['id']
                    calendar_name = cal['name']
                    break
            else:
                calendar_id = calendars[0]['id']
                calendar_name = calendars[0]['name']

        # Create the event
        event_id, updated_credentials = calendar_service.create_event_in_calendar(
            user.get_credentials(),
            parsed_event,
            calendar_id,
            user.timezone
        )

        # Update user credentials if refreshed
        if updated_credentials:
            user.google_access_token = updated_credentials.token
            if updated_credentials.expiry:
                user.token_expiry = updated_credentials.expiry
            db.session.commit()

        if event_id:
            return f'''🎉 *Event Created Successfully!*

📝 *{parsed_event['title']}*
📅 {format_event_time(parsed_event)}
📍 {parsed_event['location'] if parsed_event['location'] else 'No location'}
📂 {calendar_name}

Event ID: {event_id}'''
        else:
            return "❌ Failed to create event. Please try again or check your permissions."

    except Exception as e:
        print(f"Error creating confirmed event: {e}")
        return "❌ Error creating event. Please try again."

def create_event_in_specific_calendar(user, parsed_event, selected_calendar):
    """Create event in user-selected calendar"""
    try:
        calendar_service = GoogleCalendarService()

        # Create the event
        event_id, updated_credentials = calendar_service.create_event_in_calendar(
            user.get_credentials(),
            parsed_event,
            selected_calendar['id'],
            user.timezone
        )

        # Update user credentials if refreshed
        if updated_credentials:
            user.google_access_token = updated_credentials.token
            if updated_credentials.expiry:
                user.token_expiry = updated_credentials.expiry
            db.session.commit()

        if event_id:
            return f'''🎉 *Event Created Successfully!*

📝 *{parsed_event['title']}*
📅 {format_event_time(parsed_event)}
📍 {parsed_event['location'] if parsed_event['location'] else 'No location'}
📂 {selected_calendar['name']}

Event ID: {event_id}'''
        else:
            return "❌ Failed to create event. Please try again or check your permissions."

    except Exception as e:
        print(f"Error creating event in specific calendar: {e}")
        return "❌ Error creating event. Please try again."

def ask_for_confirmation(user, parsed_event):
    """Ask user to confirm event creation"""
    # Convert datetime objects to strings for JSON storage
    serializable_event = make_json_serializable(parsed_event)
    user.set_conversation_state('confirm_event', {'parsed_event': serializable_event})

    location_text = parsed_event['location'] if parsed_event['location'] else 'No location'

    return f'''🤔 *Let me confirm this event:*

📝 *{parsed_event['title']}*
📅 {format_event_time(parsed_event)}
📍 {location_text}

Is this correct? Reply:
• *yes* to create
• *no* to cancel
• *edit* to make changes

_Confidence: {parsed_event['confidence']}%_'''

def show_understanding_and_ask(user, parsed_event):
    """Show what we understood and ask for clarification"""
    # Convert datetime objects to strings for JSON storage
    serializable_event = make_json_serializable(parsed_event)
    user.set_conversation_state('confirm_event', {'parsed_event': serializable_event})

    location_text = parsed_event['location'] if parsed_event['location'] else 'No location'

    return f'''🤔 *I think I understand, but want to make sure:*

📝 *{parsed_event['title']}*
📅 {format_event_time(parsed_event)}
📍 {location_text}

Did I get this right? Reply:
• *yes* to create this event
• *no* to cancel
• *edit* to make changes

_Confidence: {parsed_event['confidence']}%_'''

def format_event_time(parsed_event):
    """Format event time for display"""
    start_time = parsed_event['start_time']
    end_time = parsed_event['end_time']

    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    return f"{start_time.strftime('%A, %B %d, %Y')} at {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"

def get_help_message():
    """Get comprehensive help message"""
    return '''🤖 *Smart Calendar Bot Help*

*📝 Create Events Naturally:*
Just tell me what you want to schedule:
• "Meeting with John tomorrow at 2pm"
• "Doctor appointment Friday 10am in clinic"
• "Lunch with Sarah next Monday 12:30pm"
• "Team standup daily at 9am room A"

*📅 View Events:*
• *today* - Get today's events
• *upcoming* - Get this week's events

*⚙️ Setup:*
• *connect* - Link your Google Calendar
• *status* - Check connection status

*💡 Tips:*
• I understand natural language!
• Include time, date, and who you're meeting
• Add location for better organization
• I'll ask for confirmation if unsure

Try saying "Meeting with John tomorrow at 2pm" to see the magic! ✨'''

def handle_connect_command(phone_number):
    """Handle connect command"""
    auth_url = f"https://41bf4e1c7513.ngrok-free.app/auth/login/{phone_number}"
    return f'''🔗 *Connect Your Google Calendar*

Click this link to authorize calendar access:
{auth_url}

After clicking, you'll be redirected to Google to sign in and grant permissions.'''

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

    return f"✅ Connected to Google Calendar\n📍 Timezone: {user.timezone}\n📅 Ready to fetch events and create new ones with AI!"

def process_message(phone_number, message_text):
    """Process incoming message and return response"""
    print(f"🔥 FUNCTION CALLED: {message_text}")
    print(f"Processing: {message_text} from {phone_number}")

    # Get or create user
    user = User.query.filter_by(whatsapp_number=phone_number).first()
    if not user:
        user = User(whatsapp_number=phone_number)
        db.session.add(user)
        db.session.commit()

    # Clean message text
    message_lower = message_text.lower().strip()

    # Check if user is in a conversation flow
    if user.conversation_step and not user.is_conversation_expired():
        print(f"🔥 USER IN CONVERSATION: {user.conversation_step}")
        conversation_result = handle_conversation_flow(user, message_text)
        if conversation_result:
            return conversation_result

    # Handle exact command matches
    exact_commands = {
        'today': lambda: handle_today_command(phone_number),
        'upcoming': lambda: handle_upcoming_command(phone_number),
        'connect': lambda: handle_connect_command(phone_number),
        'status': lambda: check_user_status(phone_number),
        'hello': lambda: "Hello! I'm your smart WhatsApp Calendar Bot. Try saying things like: 'Meeting with John tomorrow at 2pm', 'Doctor appointment Friday 10am', 'today' to see today's events, 'help' for more commands",
        'help': lambda: get_help_message(),
        'add': lambda: "📝 Just tell me about your event naturally! Try saying: 'Meeting with John tomorrow at 2pm', 'Doctor appointment Friday 10am', 'Lunch with Sarah next Monday 12:30pm'",
        'cancel': lambda: handle_cancel_command(user)
    }

    if message_lower in exact_commands:
        print(f"🔥 EXACT COMMAND FOUND: {message_lower}")
        return exact_commands[message_lower]()

    # Check if user is connected for event creation
    if not user.google_access_token:
        print("🔥 USER NOT CONNECTED")
        # Only suggest NLP for event-like messages
        if should_try_nlp(message_text):
            print("🔥 SHOULD TRY NLP - NOT CONNECTED")
            return "❌ Please connect your Google Calendar first to create events. Send 'connect' to get started, then you can say things like: 'Meeting with John tomorrow at 2pm'"
        else:
            print("🔥 SHOULD NOT TRY NLP")
            return f"Unknown command: '{message_text}'\nType 'help' for available commands."

    print("🔥 USER IS CONNECTED")

    # Try NLP parsing for event creation (only if connected)
    if should_try_nlp(message_text):
        print("🔥 TRYING NLP!")
        nlp_result = try_nlp_event_creation(user, message_text)
        print(f"🔥 NLP RESULT: {nlp_result is not None}")
        if nlp_result:
            return nlp_result
        else:
            return "🤔 I couldn't parse that as an event. Try formats like: 'Meeting with John tomorrow at 2pm', 'Doctor appointment Friday 10am', 'Lunch with Sarah next Monday 12:30pm'. Or use commands like 'today', 'upcoming', or 'help'"

    print("🔥 NOT TRYING NLP")
    # Fallback for non-event messages
    return f"Unknown command: '{message_text}'\nType 'help' for available commands."

def handle_cancel_command(user):
    """Handle cancel command to clear conversation state"""
    if user.conversation_step:
        user.clear_conversation_state()
        return "❌ Cancelled current conversation. You can start fresh anytime!"
    else:
        return "Nothing to cancel. You can create events by saying something like: 'Meeting with John tomorrow at 2pm'"

# NOW create_app() function
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    @app.route('/')
    def index():
        return "WhatsApp Calendar Bot with Conversation State is running!"

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
                                            message_text = message.get('text', {}).get('body', '').strip()

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
                <p>You can now use calendar commands and create events naturally!</p>
                <p>Try saying: <strong>"Meeting with John tomorrow at 2pm"</strong></p>
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

    # Debug routes for conversation state
    @app.route('/debug/event-creation/<path:phone_number>')
    def debug_event_creation(phone_number):
        """Debug event creation"""
        phone_number = phone_number.replace('%2B', '+')
        user = User.query.filter_by(whatsapp_number=phone_number).first()

        if not user or not user.google_access_token:
            return "User not connected to Google Calendar"

        # Test event creation
        test_event = {
            'title': 'Test Event',
            'start_time': datetime.now(),
            'end_time': datetime.now() + timedelta(hours=1),
            'location': 'Test Location'
        }

        try:
            calendar_service = GoogleCalendarService()
            event_id, updated_credentials = calendar_service.create_event_in_calendar(
                user.get_credentials(),
                test_event,
                'primary',
                user.timezone
            )

            if event_id:
                return f"✅ Test event created successfully! ID: {event_id}"
            else:
                return "❌ Event creation returned None"

        except Exception as e:
            return f"❌ Event creation error: {str(e)}"

    @app.route('/debug/calendars/<path:phone_number>')
    def debug_calendars(phone_number):
        """Debug user's calendars"""
        phone_number = phone_number.replace('%2B', '+')
        user = User.query.filter_by(whatsapp_number=phone_number).first()

        if not user or not user.google_access_token:
            return "User not connected"

        try:
            calendar_service = GoogleCalendarService()
            calendars, _ = calendar_service.get_user_calendars(user.get_credentials())

            result = f"Total calendars: {len(calendars)}\n\n"

            for i, cal in enumerate(calendars, 1):
                result += f"{i}. {cal['name']}\n"
                result += f"   ID: {cal['id']}\n"
                result += f"   Primary: {cal.get('primary', False)}\n"
                result += f"   Access: {cal['access_role']}\n"
                result += f"   Writable: {cal['access_role'] in ['owner', 'writer']}\n\n"

            writable_calendars = [cal for cal in calendars if cal['access_role'] in ['owner', 'writer']]
            result += f"Writable calendars: {len(writable_calendars)}\n"

            return f"<pre>{result}</pre>"

        except Exception as e:
            return f"Error: {str(e)}"

    @app.route('/debug/conversation/<path:phone_number>')
    def debug_conversation(phone_number):
        """Debug conversation state for a user"""
        phone_number = phone_number.replace('%2B', '+')
        user = User.query.filter_by(whatsapp_number=phone_number).first()

        if not user:
            return f"User {phone_number} not found"

        return {
            'phone_number': user.whatsapp_number,
            'conversation_step': user.conversation_step,
            'conversation_state': user.get_conversation_state(),
            'conversation_updated': user.conversation_updated.isoformat() if user.conversation_updated else None,
            'is_expired': user.is_conversation_expired()
        }

    @app.route('/debug/clear-conversation/<path:phone_number>')
    def clear_conversation(phone_number):
        """Clear conversation state for a user"""
        phone_number = phone_number.replace('%2B', '+')
        user = User.query.filter_by(whatsapp_number=phone_number).first()

        if not user:
            return f"User {phone_number} not found"

        user.clear_conversation_state()
        return f"Conversation state cleared for {phone_number}"

    return app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)