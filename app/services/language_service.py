import re
from datetime import datetime

class LanguageService:
    def __init__(self):
        self.hebrew_patterns = [
            # Hebrew characters range
            r'[\u0590-\u05FF]',
            # Common Hebrew words
            r'\b(שלום|היום|מחר|פגישה|תור|בשעה|עם|ב|של|את|אני|אתה|זה)\b'
        ]

    def detect_language(self, text):
        """Detect if text is Hebrew or English"""
        if not text:
            return 'en'

        # Count Hebrew characters
        hebrew_chars = len(re.findall(r'[\u0590-\u05FF]', text))
        # Count English alphabetic characters
        english_chars = len(re.findall(r'[a-zA-Z]', text))

        # If we have Hebrew characters, it's Hebrew
        if hebrew_chars > 0:
            return 'he'
        # If we have English characters and no Hebrew, it's English
        elif english_chars > 0:
            return 'en'
        # Default to English for numbers/symbols only
        else:
            return 'en'

    def get_user_language(self, user, message_text):
        """Get user's language preference, updating if needed"""
        detected = self.detect_language(message_text)

        # Update user's language preference if auto or changed
        if user.language == 'auto' or (user.language != detected and detected in ['en', 'he']):
            user.language = detected
            from app.models.user import db
            db.session.commit()

        return user.language if user.language in ['en', 'he'] else detected

class MessageTemplates:
    """Bilingual message templates"""

    MESSAGES = {
        'en': {
            'welcome': "Hello! I'm your smart WhatsApp Calendar Bot. Try saying things like: 'Meeting with John tomorrow at 2pm', 'Doctor appointment Friday 10am', 'today' to see today's events, 'help' for more commands",

            'connect_prompt': '''🔗 *Connect Your Google Calendar*

Click this link to authorize calendar access:
{auth_url}

*What you'll be asked to allow:*
📅 Read your calendar events
➕ Create new events
🔒 We never delete or modify existing events

*This is safe and secure - you can revoke access anytime in your Google Account settings.*''',

            'help_message': '''🤖 *Smart Calendar Bot Help*

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

*🌍 Language:*
• *עבור לעברית* - Switch to Hebrew

Try saying "Meeting with John tomorrow at 2pm" to see the magic! ✨''',

            'event_created': '''🎉 *Event Created Successfully!*

📝 *{title}*
📅 {time}
📍 {location}
📂 {calendar}

✨ _Created automatically with {confidence}% confidence_''',

            'event_confirmation': '''🤔 *Let me confirm this event:*

📝 *{title}*
📅 {time}
📍 {location}

Is this correct? Reply:
• *yes* to create
• *no* to cancel
• *edit* to make changes

_Confidence: {confidence}%_''',

            'calendar_selection': '''📂 *Choose Calendar for Your Event:*

📝 *{title}*
📅 {time}

*Available Calendars:*
{calendar_list}
Reply with the number (1, 2, 3...) to select

_🔹 = Primary Calendar_''',

            'calendar_not_found': '''❌ *Calendar "{calendar_name}" not found*

📝 *{title}*
📅 {time}

*Available Calendars:*
{calendar_list}
Reply with the number (1, 2, 3...) to select

_🔹 = Primary Calendar_''',

            'today_events': "📅 *Today's Events*",
            'upcoming_events': "📊 *Upcoming Events*",
            'no_events': "📅 No events found for today",
            'no_upcoming_events': "📅 No upcoming events found",

            'not_connected': "❌ Please connect your Google Calendar first. Send 'connect' to get started.",
            'connection_success': "✅ Connected to Google Calendar\n📍 Timezone: {timezone}\n📅 Ready to fetch events and create new ones with AI!",

            'unknown_command': "Unknown command: '{message}'\nType 'help' for available commands.",
            'nlp_failed': "🤔 I couldn't parse that as an event. Try formats like: 'Meeting with John tomorrow at 2pm', 'Doctor appointment Friday 10am', 'Lunch with Sarah next Monday 12:30pm'. Or use commands like 'today', 'upcoming', or 'help'",

            'language_switched': "✅ Language switched to English! You can now chat in English.",

            'auth_denied': '''❌ Access Denied

You need to grant calendar permissions for the bot to work.
To try again, send 'connect' to the WhatsApp bot.

*Why we need permissions:*
• 📅 Read your calendar events
• ➕ Create events you request
• 🔒 We never modify or delete existing events''',

            'auth_success': '''✅ Calendar Connected Successfully!

Your WhatsApp is now connected to Google Calendar.
Timezone set to: *{timezone}*

You can now use calendar commands and create events naturally!
Try saying: *"Meeting with John tomorrow at 2pm"*'''
        },

        'he': {
            'welcome': "שלום! אני הבוט החכם שלך לניהול יומן בוואטסאפ. נסה לומר דברים כמו: 'פגישה עם יונתן מחר בשעה 14:00', 'תור לרופא יום שישי 10:00', 'היום' כדי לראות את אירועי היום, 'עזרה' לפקודות נוספות",

            'connect_prompt': '''🔗 *חבר את יומן הגוגל שלך*

לחץ על הקישור הזה כדי לאשר גישה ליומן:
{auth_url}

*מה תתבקש לאשר:*
📅 קריאת אירועי היומן שלך
➕ יצירת אירועים חדשים
🔒 אנחנו לעולם לא מוחקים או משנים אירועים קיימים

*זה בטוח ומאובטח - אתה יכול לבטל את הגישה בכל עת בהגדרות חשבון הגוגל שלך.*''',

            'help_message': '''🤖 *עזרה לבוט יומן חכם*

*📝 יצירת אירועים באופן טבעי:*
פשוט תגיד לי מה אתה רוצה לתזמן:
• "פגישה עם יונתן מחר בשעה 14:00"
• "תור לרופא יום שישי בשעה 10:00 במרפאה"
• "ארוחת צהריים עם שרה יום שני הבא 12:30"
• "סטנדאפ צוות יומי בשעה 9:00 חדר A"

*📅 צפייה באירועים:*
• *היום* - קבל את אירועי היום
• *קרוב* - קבל את אירועי השבוע

*⚙️ הגדרות:*
• *התחבר* - חבר את יומן הגוגל
• *סטטוס* - בדוק מצב החיבור

*🌍 שפה:*
• *switch to english* - עבור לאנגלית

נסה לומר "פגישה עם יונתן מחר בשעה 14:00" כדי לראות את הקסם! ✨''',

            'event_created': '''🎉 *האירוע נוצר בהצלחה!*

📝 *{title}*
📅 {time}
📍 {location}
📂 {calendar}

✨ _נוצר אוטומטית ב{confidence}% ביטחון_''',

            'event_confirmation': '''🤔 *בואו נוודא שהבנתי נכון:*

📝 *{title}*
📅 {time}
📍 {location}

האם זה נכון? השב:
• *כן* כדי ליצור
• *לא* כדי לבטל
• *עריכה* כדי לשנות

_רמת ביטחון: {confidence}%_''',

            'calendar_selection': '''📂 *בחר יומן עבור האירוע שלך:*

📝 *{title}*
📅 {time}

*יומנים זמינים:*
{calendar_list}
השב עם המספר (1, 2, 3...) כדי לבחור

_🔹 = יומן ראשי_''',

            'calendar_not_found': '''❌ *יומן "{calendar_name}" לא נמצא*

📝 *{title}*
📅 {time}

*יומנים זמינים:*
{calendar_list}
השב עם המספר (1, 2, 3...) כדי לבחור

_🔹 = יומן ראשי_''',

            'today_events': "📅 *אירועי היום*",
            'upcoming_events': "📊 *אירועים קרובים*",
            'no_events': "📅 לא נמצאו אירועים להיום",
            'no_upcoming_events': "📅 לא נמצאו אירועים קרובים",

            'not_connected': "❌ אנא חבר את יומן הגוגל שלך תחילה. שלח 'התחבר' כדי להתחיל.",
            'connection_success': "✅ מחובר ליומן הגוגל\n📍 אזור זמן: {timezone}\n📅 מוכן לאחזר אירועים וליצור חדשים עם בינה מלאכותית!",

            'unknown_command': "פקודה לא מוכרת: '{message}'\nכתוב 'עזרה' לפקודות זמינות.",
            'nlp_failed': "🤔 לא הצלחתי לפרש את זה כאירוע. נסה פורמטים כמו: 'פגישה עם יונתן מחר בשעה 14:00', 'תור לרופא יום שישי 10:00', 'ארוחת צהריים עם שרה יום שני הבא 12:30'. או השתמש בפקודות כמו 'היום', 'קרוב', או 'עזרה'",

            'language_switched': "✅ השפה הוחלפה לעברית! עכשיו אתה יכול לשוחח בעברית.",

            'auth_denied': '''❌ גישה נדחתה

אתה צריך לאשר הרשאות יומן כדי שהבוט יעבוד.
כדי לנסות שוב, שלח 'התחבר' לבוט הוואטסאפ.

*למה אנחנו צריכים הרשאות:*
• 📅 קריאת אירועי היומן שלך
• ➕ יצירת אירועים שאתה מבקש
• 🔒 אנחנו לעולם לא משנים או מוחקים אירועים קיימים''',

            'auth_success': '''✅ היומן חובר בהצלחה!

הוואטסאפ שלך מחובר עכשיו ליומן הגוגל.
אזור זמן נקבע ל: *{timezone}*

עכשיו אתה יכול להשתמש בפקודות יומן וליצור אירועים באופן טבעי!
נסה לומר: *"פגישה עם יונתן מחר בשעה 14:00"*'''
        }
    }

    @classmethod
    def get_message(cls, user, key, **kwargs):
        """Get message in user's language with formatting"""
        # Default to English if no language set
        lang = getattr(user, 'language', 'en') or 'en'

        # Get template
        template = cls.MESSAGES.get(lang, {}).get(key)
        if not template:
            # Fallback to English if key not found in user's language
            template = cls.MESSAGES['en'].get(key, f"Message key '{key}' not found")

        # Format with provided arguments
        try:
            return template.format(**kwargs) if kwargs else template
        except (KeyError, ValueError) as e:
            print(f"Error formatting message '{key}': {e}")
            return template

class HebrewDateFormatter:
    """Format dates and times in Hebrew"""

    DAYS_HE = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']
    MONTHS_HE = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
                 'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']

    @classmethod
    def format_event_time(cls, parsed_event, language='en'):
        """Format event time based on language"""
        start_time = parsed_event['start_time']
        end_time = parsed_event['end_time']

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)

        if language == 'he':
            # Hebrew formatting
            day_name = cls.DAYS_HE[start_time.weekday()]
            month_name = cls.MONTHS_HE[start_time.month - 1]

            return f"יום {day_name}, {start_time.day} ב{month_name} {start_time.year} בשעה {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
        else:
            # English formatting
            return f"{start_time.strftime('%A, %B %d, %Y')} at {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"