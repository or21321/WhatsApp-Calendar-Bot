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

def detect_user_language(user, message_text):
    """Simple language detection and update user preference"""
    hebrew_chars = len([c for c in message_text if '\u0590' <= c <= '\u05FF'])

    if hebrew_chars > 0:
        user.language = 'he'
    else:
        user.language = 'en'

    db.session.commit()
    return user.language

def get_message_in_language(language, key, **kwargs):
    """Get message template in specified language"""
    messages = {
        'en': {
            'welcome': "Hello! I'm your smart WhatsApp Calendar Bot. Try saying things like: 'Meeting with John tomorrow at 2pm', 'Doctor appointment Friday 10am', 'today' to see today's events, 'help' for more commands",
            'help': "🤖 *Smart Calendar Bot Help*\n\n*📝 Create Events Naturally:*\nJust tell me what you want to schedule:\n• \"Meeting with John tomorrow at 2pm\"\n• \"Doctor appointment Friday 10am in clinic\"\n• \"Lunch with Sarah next Monday 12:30pm\"\n\n*📅 View Events:*\n• *today* - Get today's events\n• *upcoming* - Get this week's events\n\n*⚙️ Setup:*\n• *connect* - Link your Google Calendar\n• *status* - Check connection status\n\n*🌍 Language:*\n• *עבור לעברית* - Switch to Hebrew\n\nTry saying \"Meeting with John tomorrow at 2pm\" to see the magic! ✨",
            'not_connected': "❌ Please connect your Google Calendar first. Send 'connect' to get started.",
            'connection_success': "✅ Connected to Google Calendar\n📍 Timezone: {timezone}\n📅 Ready to fetch events and create new ones with AI!",
            'unknown_command': "Unknown command: '{message}'\nType 'help' for available commands.",
            'nlp_failed': "🤔 I couldn't parse that as an event. Try formats like: 'Meeting with John tomorrow at 2pm', 'Doctor appointment Friday 10am', 'Lunch with Sarah next Monday 12:30pm'. Or use commands like 'today', 'upcoming', or 'help'",
            'language_switched': "✅ Language switched to English! You can now chat in English.",
            'cancel_with_conversation': "❌ Cancelled current conversation. You can start fresh anytime!",
            'cancel_without_conversation': "Nothing to cancel. You can create events by saying something like: 'Meeting with John tomorrow at 2pm'",
            'connect_prompt': "🔗 *Connect Your Google Calendar*\n\nClick this link to authorize calendar access:\n{auth_url}\n\n*What you'll be asked to allow:*\n📅 Read your calendar events\n➕ Create new events\n🔒 We never delete or modify existing events\n\n*This is safe and secure - you can revoke access anytime in your Google Account settings.*"
        },
        'he': {
            'welcome': "שלום! אני הבוט החכם שלך לניהול יומן בוואטסאפ. נסה לומר דברים כמו: 'פגישה עם יונתן מחר בשעה 14:00', 'תור לרופא יום שישי 10:00', 'היום' כדי לראות את אירועי היום, 'עזרה' לפקודות נוספות",
            'help': "🤖 *עזרה לבוט יומן חכם*\n\n*📝 יצירת אירועים באופן טבעי:*\nפשוט תגיד לי מה אתה רוצה לתזמן:\n• \"פגישה עם יונתן מחר בשעה 14:00\"\n• \"תור לרופא יום שישי בשעה 10:00 במרפאה\"\n• \"ארוחת צהריים עם שרה יום שני הבא 12:30\"\n\n*📅 צפייה באירועים:*\n• *היום* - קבל את אירועי היום\n• *קרוב* - קבל את אירועי השבוע\n\n*⚙️ הגדרות:*\n• *התחבר* - חבר את יומן הגוגל\n• *סטטוס* - בדוק מצב החיבור\n\n*🌍 שפה:*\n• *switch to english* - עבור לאנגלית\n\nנסה לומר \"פגישה עם יונתן מחר בשעה 14:00\" כדי לראות את הקסם! ✨",
            'not_connected': "❌ אנא חבר את יומן הגוגל שלך תחילה. שלח 'התחבר' כדי להתחיל.",
            'connection_success': "✅ מחובר ליומן הגוגל\n📍 אזור זמן: {timezone}\n📅 מוכן לאחזר אירועים וליצור חדשים עם בינה מלאכותית!",
            'unknown_command': "פקודה לא מוכרת: '{message}'\nכתוב 'עזרה' לפקודות זמינות.",
            'nlp_failed': "🤔 לא הצלחתי לפרש את זה כאירוע. נסה פורמטים כמו: 'פגישה עם יונתן מחר בשעה 14:00', 'תור לרופא יום שישי 10:00', 'ארוחת צהריים עם שרה יום שני הבא 12:30'. או השתמש בפקודות כמו 'היום', 'קרוב', או 'עזרה'",
            'language_switched': "✅ השפה הוחלפה לעברית! עכשיו אתה יכול לשוחח בעברית.",
            'cancel_with_conversation': "❌ השיחה הנוכחית בוטלה. אתה יכול להתחיל מחדש בכל עת!",
            'cancel_without_conversation': "אין מה לבטל. אתה יכול ליצור אירועים על ידי אמירת משהו כמו: 'פגישה עם יונתן מחר בשעה 14:00'",
            'connect_prompt': "🔗 *חבר את יומן הגוגל שלך*\n\nלחץ על הקישור הזה כדי לאשר גישה ליומן:\n{auth_url}\n\n*מה תתבקש לאשר:*\n📅 קריאת אירועי היומן שלך\n➕ יצירת אירועים חדשים\n🔒 אנחנו לעולם לא מוחקים או משנים אירועים קיימים\n\n*זה בטוח ומאובטח - אתה יכול לבטל את הגישה בכל עת בהגדרות חשבון הגוגל שלך.*"
        }
    }

    lang_messages = messages.get(language, messages['en'])
    template = lang_messages.get(key, messages['en'].get(key, f"Message '{key}' not found"))

    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, ValueError):
        return template

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
        'standup', 'review', 'workout', 'gym', 'party', 'event',
        # Hebrew indicators
        'פגישה', 'תור', 'פגש', 'ארוחה', 'קפה', 'רופא', 'רופאה'
    ]

    if any(indicator in message_lower for indicator in strong_indicators):
        return True

    # Time/date indicators (likely an event if combined with other words)
    time_indicators = [
        'tomorrow', 'today', 'tonight', 'morning', 'afternoon', 'evening',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'next week', 'this week', 'next month', 'next monday', 'this friday',
        'am', 'pm', 'o\'clock',
        # Hebrew indicators
        'מחר', 'היום', 'בוקר', 'צהריים', 'ערב', 'לילה',
        'ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת',
        'בשעה', 'ב'
    ]

    # If has time indicator + person/organization names, likely an event
    if any(indicator in message_lower for indicator in time_indicators):
        # Check for person indicators
        person_indicators = ['with', 'and', 'john', 'sarah', 'mike', 'team', 'client', 'boss', 'עם', 'ו']
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
        r'\d{1,2}:\d{2}',  # 24-hour format
        r'בשעה\s+\d{1,2}',  # Hebrew time patterns
    ]

    for pattern in time_patterns:
        if re.search(pattern, message_lower):
            return True

    # Default: don't try NLP
    return False

def format_event_time(parsed_event, language='en'):
    """Format event time for display"""
    start_time = parsed_event['start_time']
    end_time = parsed_event['end_time']

    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    if language == 'he':
        # Hebrew formatting
        days_he = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']
        months_he = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
                     'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']

        day_name = days_he[start_time.weekday()]
        month_name = months_he[start_time.month - 1]

        return f"יום {day_name}, {start_time.day} ב{month_name} {start_time.year} בשעה {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    else:
        # English formatting
        return f"{start_time.strftime('%A, %B %d, %Y')} at {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"

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

    if message_lower in ['yes', 'y', 'confirm', 'create', 'ok', 'okay', 'כן', 'אישור']:
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

    elif message_lower in ['no', 'n', 'cancel', 'nope', 'לא', 'בטל']:
        # User cancelled
        user.clear_conversation_state()
        if user.language == 'he':
            return "❌ יצירת האירוע בוטלה. אתה יכול ליצור אירוע חדש בכל עת על ידי אמירת משהו כמו: 'פגישה עם יונתן מחר בשעה 14:00'"
        else:
            return "❌ Event creation cancelled. You can create a new event anytime by saying something like: 'Meeting with John tomorrow at 2pm'"

    elif message_lower in ['edit', 'change', 'modify', 'fix', 'עריכה', 'שנה']:
        # User wants to edit
        user.set_conversation_state('edit_event', conversation_data)
        if user.language == 'he':
            return "✏️ *מה תרצה לשנות?*\n\nאתה יכול לומר:\n• \"שנה שעה ל15:00\"\n• \"שנה תאריך ליום שני\"\n• \"שנה כותרת לפגישת צוות\"\n• \"הוסף מיקום משרד חדר A\"\n• \"בטל\" כדי להתחיל מחדש"
        else:
            return "✏️ *What would you like to change?*\n\nYou can say:\n• \"Change time to 3pm\"\n• \"Change date to Monday\"\n• \"Change title to Team Meeting\"\n• \"Add location Office Room A\"\n• \"Cancel\" to start over"

    else:
        # Invalid response - ask again
        serializable_event = conversation_data.get('parsed_event')
        if serializable_event:
            parsed_event = make_json_deserializable(serializable_event)
            if user.language == 'he':
                return f"🤔 אנא השב עם:\n• *כן* כדי ליצור את האירוע\n• *לא* כדי לבטל\n• *עריכה* כדי לשנות\n\nאירוע: *{parsed_event.get('title', 'ללא כותרת')}*\nזמן: {format_event_time(parsed_event, user.language)}"
            else:
                return f"🤔 Please reply with:\n• *yes* to create the event\n• *no* to cancel\n• *edit* to make changes\n\nEvent: *{parsed_event.get('title', 'Untitled')}*\nTime: {format_event_time(parsed_event, user.language)}"
        else:
            user.clear_conversation_state()
            return "❌ Something went wrong. Please try creating your event again."

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
            if user.language == 'he':
                return f"❌ אנא הכנס מספר בין 1 ל{len(calendars)}"
            else:
                return f"❌ Please enter a number between 1 and {len(calendars)}"

    except ValueError:
        message_lower = message_text.lower().strip()
        if message_lower in ['cancel', 'back', 'בטל', 'חזור']:
            user.clear_conversation_state()
            if user.language == 'he':
                return "❌ בחירת יומן בוטלה."
            else:
                return "❌ Calendar selection cancelled."

        calendars = conversation_data.get('calendars', [])
        calendar_list = "\n".join([f"{i+1}. {cal['name']}" for i, cal in enumerate(calendars)])

        if user.language == 'he':
            return f"❌ אנא הכנס מספר לבחירת יומן:\n\n{calendar_list}"
        else:
            return f"❌ Please enter a number to select a calendar:\n\n{calendar_list}"

def handle_event_editing(user, message_text, conversation_data):
    """Handle event editing requests"""
    # This is a simplified version - you could make this much more sophisticated
    user.clear_conversation_state()
    if user.language == 'he':
        return "✏️ עריכת אירועים בקרוב! לעת עתה, אנא צור אירוע חדש עם הפרטים הנכונים."
    else:
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
    event_time = format_event_time(parsed_event, user.language)

    if user.language == 'he':
        message = f"❌ *יומן \"{requested_name}\" לא נמצא*\n\n"
        message += f"📝 *{event_title}*\n"
        message += f"📅 {event_time}\n\n"
        message += "*יומנים זמינים:*\n"
        message += calendar_list
        message += "השב עם המספר (1, 2, 3...) כדי לבחור\n\n"
        message += "_🔹 = יומן ראשי_"
    else:
        message = f"❌ *Calendar \"{requested_name}\" not found*\n\n"
        message += f"📝 *{event_title}*\n"
        message += f"📅 {event_time}\n\n"
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

    if user.language == 'he':
        message = "📂 *בחר יומן עבור האירוע שלך:*\n\n"
        message += f"📝 *{parsed_event['title']}*\n"
        message += f"📅 {format_event_time(parsed_event, user.language)}\n\n"
        message += "*יומנים זמינים:*\n"
        message += calendar_list
        message += "השב עם המספר (1, 2, 3...) כדי לבחור\n\n"
        message += "_🔹 = יומן ראשי_"
    else:
        message = "📂 *Choose Calendar for Your Event:*\n\n"
        message += f"📝 *{parsed_event['title']}*\n"
        message += f"📅 {format_event_time(parsed_event, user.language)}\n\n"
        message += "*Available Calendars:*\n"
        message += calendar_list
        message += "Reply with the number (1, 2, 3...) to select\n\n"
        message += "_🔹 = Primary Calendar_"

    return message

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
            location_text = parsed_event['location'] if parsed_event['location'] else (
                'ללא מיקום' if user.language == 'he' else 'No location'
            )

            if user.language == 'he':
                message = "🎉 *האירוע נוצר בהצלחה!*\n\n"
                message += f"📝 *{parsed_event['title']}*\n"
                message += f"📅 {format_event_time(parsed_event, user.language)}\n"
                message += f"📍 {location_text}\n"
                message += f"📂 {calendar_name}\n\n"
                message += f"✨ _נוצר אוטומטית ב{parsed_event['confidence']}% ביטחון_"
            else:
                message = "🎉 *Event Created Successfully!*\n\n"
                message += f"📝 *{parsed_event['title']}*\n"
                message += f"📅 {format_event_time(parsed_event, user.language)}\n"
                message += f"📍 {location_text}\n"
                message += f"📂 {calendar_name}\n\n"
                message += f"✨ _Created automatically with {parsed_event['confidence']}% confidence_"

            return message
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
            location_text = parsed_event['location'] if parsed_event['location'] else (
                'ללא מיקום' if user.language == 'he' else 'No location'
            )

            if user.language == 'he':
                message = "🎉 *האירוע נוצר בהצלחה!*\n\n"
                message += f"📝 *{parsed_event['title']}*\n"
                message += f"📅 {format_event_time(parsed_event, user.language)}\n"
                message += f"📍 {location_text}\n"
                message += f"📂 {calendar_name}\n\n"
                message += f"Event ID: {event_id}"
            else:
                message = "🎉 *Event Created Successfully!*\n\n"
                message += f"📝 *{parsed_event['title']}*\n"
                message += f"📅 {format_event_time(parsed_event, user.language)}\n"
                message += f"📍 {location_text}\n"
                message += f"📂 {calendar_name}\n\n"
                message += f"Event ID: {event_id}"

            return message
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
            location_text = parsed_event['location'] if parsed_event['location'] else (
                'ללא מיקום' if user.language == 'he' else 'No location'
            )

            if user.language == 'he':
                message = f"🎉 *האירוע נוצר ב{selected_calendar['name']}!*\n\n"
                message += f"📝 *{parsed_event['title']}*\n"
                message += f"📅 {format_event_time(parsed_event, user.language)}\n"
                message += f"📍 {location_text}\n"
                message += f"📂 {selected_calendar['name']}\n\n"
                message += f"Event ID: {event_id}"
            else:
                message = f"🎉 *Event Created in {selected_calendar['name']}!*\n\n"
                message += f"📝 *{parsed_event['title']}*\n"
                message += f"📅 {format_event_time(parsed_event, user.language)}\n"
                message += f"📍 {location_text}\n"
                message += f"📂 {selected_calendar['name']}\n\n"
                message += f"Event ID: {event_id}"

            return message
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

    location_text = parsed_event['location'] if parsed_event['location'] else (
        'ללא מיקום' if user.language == 'he' else 'No location'
    )

    if user.language == 'he':
        message = "🤔 *בואו נוודא שהבנתי נכון:*\n\n"
        message += f"📝 *{parsed_event['title']}*\n"
        message += f"📅 {format_event_time(parsed_event, user.language)}\n"
        message += f"📍 {location_text}\n\n"
        message += "האם זה נכון? השב:\n"
        message += "• *כן* כדי ליצור\n"
        message += "• *לא* כדי לבטל\n"
        message += "• *עריכה* כדי לשנות\n\n"
        message += f"_רמת ביטחון: {parsed_event['confidence']}%_"
    else:
        message = "🤔 *Let me confirm this event:*\n\n"
        message += f"📝 *{parsed_event['title']}*\n"
        message += f"📅 {format_event_time(parsed_event, user.language)}\n"
        message += f"📍 {location_text}\n\n"
        message += "Is this correct? Reply:\n"
        message += "• *yes* to create\n"
        message += "• *no* to cancel\n"
        message += "• *edit* to make changes\n\n"
        message += f"_Confidence: {parsed_event['confidence']}%_"

    return message

def show_understanding_and_ask(user, parsed_event):
    """Show what we understood and ask for clarification"""
    # Convert datetime objects to strings for JSON storage
    serializable_event = make_json_serializable(parsed_event)
    user.set_conversation_state('confirm_event', {'parsed_event': serializable_event})

    location_text = parsed_event['location'] if parsed_event['location'] else (
        'ללא מיקום' if user.language == 'he' else 'No location'
    )

    if user.language == 'he':
        message = "🤔 *אני חושב שאני מבין, אבל רוצה לוודא:*\n\n"
        message += f"📝 *{parsed_event['title']}*\n"
        message += f"📅 {format_event_time(parsed_event, user.language)}\n"
        message += f"📍 {location_text}\n\n"
        message += "האם הבנתי נכון? השב:\n"
        message += "• *כן* כדי ליצור את האירוע הזה\n"
        message += "• *לא* כדי לבטל\n"
        message += "• *עריכה* כדי לשנות\n\n"
        message += f"_רמת ביטחון: {parsed_event['confidence']}%_"
    else:
        message = "🤔 *I think I understand, but want to make sure:*\n\n"
        message += f"📝 *{parsed_event['title']}*\n"
        message += f"📅 {format_event_time(parsed_event, user.language)}\n"
        message += f"📍 {location_text}\n\n"
        message += "Did I get this right? Reply:\n"
        message += "• *yes* to create this event\n"
        message += "• *no* to cancel\n"
        message += "• *edit* to make changes\n\n"
        message += f"_Confidence: {parsed_event['confidence']}%_"

    return message

def get_help_message(user):
    """Get comprehensive help message"""
    return get_message_in_language(user.language, 'help')

def handle_connect_command(phone_number):
    """Handle connect command"""
    user = User.query.filter_by(whatsapp_number=phone_number).first()
    if not user:
        user = User(whatsapp_number=phone_number)
        db.session.add(user)
        db.session.commit()

    auth_url = f"https://41bf4e1c7513.ngrok-free.app/auth/login/{phone_number}"
    return get_message_in_language(user.language, 'connect_prompt', auth_url=auth_url)

def handle_today_command(phone_number):
    """Handle today command"""
    user = User.query.filter_by(whatsapp_number=phone_number).first()

    if not user or not user.google_access_token:
        return get_message_in_language(user.language if user else 'en', 'not_connected')

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
        return get_message_in_language(user.language if user else 'en', 'not_connected')

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
        return get_message_in_language('en', 'not_connected')

    if not user.google_access_token:
        return get_message_in_language(user.language, 'not_connected')

    return get_message_in_language(user.language, 'connection_success', timezone=user.timezone)

def handle_cancel_command(user):
    """Handle cancel command to clear conversation state"""
    if user.conversation_step:
        user.clear_conversation_state()
        return get_message_in_language(user.language, 'cancel_with_conversation')
    else:
        return get_message_in_language(user.language, 'cancel_without_conversation')

def process_message(phone_number, message_text):
    """Process incoming message and return response"""
    print(f"🔥 FUNCTION CALLED: {message_text}")
    print(f"Processing: {message_text} from {phone_number}")

    # Get or create user
    user = User.query.filter_by(whatsapp_number=phone_number).first()
    if not user:
        user = User(whatsapp_number=phone_number)
        user.language = 'auto'  # Set default language
        db.session.add(user)
        db.session.commit()

    # Detect and set user language
    if message_text:
        detect_user_language(user, message_text)

    print(f"🌍 User language: {user.language}")

    # Clean message text
    message_lower = message_text.lower().strip()

    # Check if user is in a conversation flow
    if user.conversation_step and not user.is_conversation_expired():
        print(f"🔥 USER IN CONVERSATION: {user.conversation_step}")
        conversation_result = handle_conversation_flow(user, message_text)
        if conversation_result:
            return conversation_result

    # Handle language switching commands
    if message_lower in ['עבור לאנגלית', 'switch to english']:
        user.language = 'en'
        db.session.commit()
        return get_message_in_language('en', 'language_switched')

    elif message_lower in ['עבור לעברית', 'switch to hebrew']:
        user.language = 'he'
        db.session.commit()
        return get_message_in_language('he', 'language_switched')

    # Handle exact command matches (both languages)
    exact_commands = {
        # English commands
        'today': lambda: handle_today_command(phone_number),
        'upcoming': lambda: handle_upcoming_command(phone_number),
        'connect': lambda: handle_connect_command(phone_number),
        'status': lambda: check_user_status(phone_number),
        'hello': lambda: get_message_in_language(user.language, 'welcome'),
        'help': lambda: get_help_message(user),
        'add': lambda: get_message_in_language(user.language, 'nlp_failed'),
        'cancel': lambda: handle_cancel_command(user),

        # Hebrew commands
        'היום': lambda: handle_today_command(phone_number),
        'קרוב': lambda: handle_upcoming_command(phone_number),
        'התחבר': lambda: handle_connect_command(phone_number),
        'סטטוס': lambda: check_user_status(phone_number),
        'שלום': lambda: get_message_in_language(user.language, 'welcome'),
        'עזרה': lambda: get_help_message(user),
        'הוסף': lambda: get_message_in_language(user.language, 'nlp_failed'),
        'בטל': lambda: handle_cancel_command(user)
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
            return get_message_in_language(user.language, 'not_connected')
        else:
            print("🔥 SHOULD NOT TRY NLP")
            return get_message_in_language(user.language, 'unknown_command', message=message_text)

    print("🔥 USER IS CONNECTED")

    # Try NLP parsing for event creation (only if connected)
    if should_try_nlp(message_text):
        print("🔥 TRYING NLP!")
        nlp_result = try_nlp_event_creation(user, message_text)
        print(f"🔥 NLP RESULT: {nlp_result is not None}")
        if nlp_result:
            return nlp_result
        else:
            return get_message_in_language(user.language, 'nlp_failed')

    print("🔥 NOT TRYING NLP")
    # Fallback for non-event messages
    return get_message_in_language(user.language, 'unknown_command', message=message_text)

# NOW create_app() function
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    @app.route('/')
    def index():
        return "WhatsApp Calendar Bot with Bilingual Support is running!"

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
            # Check if user denied access
            error = request.args.get('error')
            if error == 'access_denied':
                phone_number = request.args.get('state')
                user = User.query.filter_by(whatsapp_number=phone_number).first()

                if user and user.language == 'he':
                    return '''
                    <html>
                    <body style="font-family: Arial; text-align: right; direction: rtl;">
                        <h1>❌ גישה נדחתה</h1>
                        <p>אתה צריך לאשר הרשאות יומן כדי שהבוט יעבוד.</p>
                        <p>כדי לנסות שוב, שלח 'התחבר' לבוט הוואטסאפ.</p>
                        <br>
                        <p><strong>למה אנחנו צריכים הרשאות:</strong></p>
                        <ul>
                            <li>📅 קריאת אירועי היומן שלך</li>
                            <li>➕ יצירת אירועים שאתה מבקש</li>
                            <li>🔒 אנחנו לעולם לא משנים או מוחקים אירועים קיימים</li>
                        </ul>
                    </body>
                    </html>
                    '''
                else:
                    return '''
                    <html>
                    <body>
                        <h1>❌ Access Denied</h1>
                        <p>You need to grant calendar permissions for the bot to work.</p>
                        <p>To try again, send 'connect' to the WhatsApp bot.</p>
                        <br>
                        <p><strong>Why we need permissions:</strong></p>
                        <ul>
                            <li>📅 Read your calendar events</li>
                            <li>➕ Create events you request</li>
                            <li>🔒 We never modify or delete existing events</li>
                        </ul>
                    </body>
                    </html>
                    '''

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
                user.language = 'auto'
                db.session.add(user)

            user.google_access_token = tokens['access_token']
            user.google_refresh_token = tokens['refresh_token']
            user.token_expiry = tokens['token_expiry']
            user.timezone = 'Asia/Jerusalem'
            db.session.commit()

            if user.language == 'he':
                return '''
                <html>
                <body style="font-family: Arial; text-align: right; direction: rtl;">
                    <h1>✅ היומן חובר בהצלחה!</h1>
                    <p>הוואטסאפ שלך מחובר עכשיו ליומן הגוגל.</p>
                    <p>אזור זמן נקבע ל: <strong>Asia/Jerusalem</strong></p>
                    <p>עכשיו אתה יכול להשתמש בפקודות יומן וליצור אירועים באופן טבעי!</p>
                    <p>נסה לומר: <strong>"פגישה עם יונתן מחר בשעה 14:00"</strong></p>
                </body>
                </html>
                '''
            else:
                return f'''
                <html>
                <body>
                    <h1>✅ Calendar Connected Successfully!</h1>
                    <p>Your WhatsApp number <strong>{phone_number}</strong> is now connected to Google Calendar.</p>
                    <p>Timezone set to: <strong>Asia/Jerusalem</strong></p>
                    <p>You can now use calendar commands and create events naturally!</p>
                    <p>Try saying: <strong>"Meeting with John tomorrow at 2pm"</strong></p>
                </body>
                </html>
                '''

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
    @app.route('/debug/conversation/<path:phone_number>')
    def debug_conversation(phone_number):
        """Debug conversation state for a user"""
        phone_number = phone_number.replace('%2B', '+')
        user = User.query.filter_by(whatsapp_number=phone_number).first()

        if not user:
            return f"User {phone_number} not found"

        return {
            'phone_number': user.whatsapp_number,
            'language': user.language,
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