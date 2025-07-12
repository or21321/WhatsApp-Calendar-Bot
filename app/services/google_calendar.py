from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
import os
from app.config import Config

class GoogleCalendarService:
    def __init__(self):
        # Updated scopes to include event creation
        self.SCOPES = [
            'https://www.googleapis.com/auth/calendar.readonly',
            'https://www.googleapis.com/auth/calendar.events'  # Add this for event creation
        ]
        self.client_id = Config.GOOGLE_CLIENT_ID
        self.client_secret = Config.GOOGLE_CLIENT_SECRET
        self.redirect_uri = Config.GOOGLE_REDIRECT_URI

    def get_authorization_url(self, state=None):
        """Generate Google OAuth authorization URL"""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.SCOPES
        )
        flow.redirect_uri = self.redirect_uri

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state
        )

        return authorization_url, state

    def exchange_code_for_tokens(self, code, state=None):
        """Exchange authorization code for access tokens"""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.SCOPES,
            state=state
        )
        flow.redirect_uri = self.redirect_uri

        flow.fetch_token(code=code)
        credentials = flow.credentials

        return {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_expiry': credentials.expiry
        }

    def build_service(self, credentials_dict):
        """Build Google Calendar service from credentials"""
        credentials = Credentials(
            token=credentials_dict['access_token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.SCOPES  # Add this line
        )

        # Refresh token if needed
        if credentials.expired:
            credentials.refresh(Request())

        service = build('calendar', 'v3', credentials=credentials)
        return service, credentials

    def get_user_calendars(self, credentials_dict):
        """Get list of user's calendars with write access"""
        try:
            service, updated_credentials = self.build_service(credentials_dict)

            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            # Filter calendars with write access
            writable_calendars = []
            for calendar in calendars:
                access_role = calendar.get('accessRole', 'reader')
                if access_role in ['owner', 'writer'] and calendar.get('selected', True):
                    writable_calendars.append({
                        'id': calendar['id'],
                        'name': calendar.get('summary', calendar['id']),
                        'primary': calendar.get('primary', False),
                        'access_role': access_role,
                        'color': calendar.get('backgroundColor', '#4285f4')
                    })

            return writable_calendars, updated_credentials

        except Exception as e:
            print(f"Error fetching calendars: {e}")
            return [], None

    def get_all_calendars(self, credentials_dict):
        """Get list of all user's calendars"""
        try:
            service, updated_credentials = self.build_service(credentials_dict)

            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            return calendars, updated_credentials
        except Exception as e:
            print(f"Error fetching calendars: {e}")
            return [], None

    def get_today_events(self, credentials_dict, timezone='UTC'):
        """Get today's events from ALL Google Calendars"""
        try:
            service, updated_credentials = self.build_service(credentials_dict)

            # Get all calendars
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            # Get today's date range in user's timezone
            user_timezone = pytz.timezone(timezone)
            now = datetime.now(user_timezone)
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Convert to UTC for API call
            start_time = start_of_day.astimezone(pytz.UTC).isoformat()
            end_time = end_of_day.astimezone(pytz.UTC).isoformat()

            print(f"DEBUG: User timezone: {timezone}")
            print(f"DEBUG: Local time range: {start_of_day} to {end_of_day}")
            print(f"DEBUG: UTC time range: {start_time} to {end_time}")

            all_events = []

            # Get events from each calendar
            for calendar in calendars:
                calendar_id = calendar['id']
                calendar_name = calendar.get('summary', calendar_id)

                # Skip calendars that are hidden or not selected
                if not calendar.get('selected', True):
                    continue

                try:
                    events_result = service.events().list(
                        calendarId=calendar_id,
                        timeMin=start_time,
                        timeMax=end_time,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()

                    events = events_result.get('items', [])

                    # Add calendar name to each event
                    for event in events:
                        event['calendar_name'] = calendar_name
                        all_events.append(event)

                except Exception as e:
                    print(f"Error fetching events from calendar {calendar_name}: {e}")
                    continue

            # Sort all events by start time
            all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))

            # Format events for WhatsApp
            formatted_events = []
            for event in all_events:
                start = event.get('start', {})
                end = event.get('end', {})

                # Handle different event types (all-day vs timed)
                if 'dateTime' in start:
                    # Timed event - handle timezone properly
                    start_dt_str = start['dateTime']
                    end_dt_str = end['dateTime']

                    # Parse datetime with timezone info
                    if start_dt_str.endswith('Z'):
                        # UTC time
                        start_dt = datetime.fromisoformat(start_dt_str.replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(end_dt_str.replace('Z', '+00:00'))
                        start_local = start_dt.astimezone(user_timezone)
                        end_local = end_dt.astimezone(user_timezone)
                    else:
                        # Already has timezone info - use as is
                        start_dt = datetime.fromisoformat(start_dt_str)
                        end_dt = datetime.fromisoformat(end_dt_str)
                        start_local = start_dt
                        end_local = end_dt

                    print(f"DEBUG: Event '{event.get('summary')}' - Original: {start_dt_str} -> Final: {start_local}")

                    time_str = f"{start_local.strftime('%I:%M %p')} - {end_local.strftime('%I:%M %p')}"
                else:
                    # All-day event
                    time_str = "All day"

                formatted_events.append({
                    'title': event.get('summary', 'No title'),
                    'time': time_str,
                    'location': event.get('location', ''),
                    'description': event.get('description', ''),
                    'calendar': event.get('calendar_name', 'Unknown')
                })

            return formatted_events, updated_credentials

        except Exception as e:
            print(f"Error fetching calendar events: {e}")
            return [], None

    def get_upcoming_events(self, credentials_dict, days=7, timezone='UTC'):
        """Get upcoming events for the next N days from ALL calendars"""
        try:
            service, updated_credentials = self.build_service(credentials_dict)

            # Get all calendars
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            # Get date range
            user_timezone = pytz.timezone(timezone)
            now = datetime.now(user_timezone)
            end_date = now + timedelta(days=days)

            # Convert to UTC for API call
            start_time = now.astimezone(pytz.UTC).isoformat()
            end_time = end_date.astimezone(pytz.UTC).isoformat()

            all_events = []

            # Get events from each calendar
            for calendar in calendars:
                calendar_id = calendar['id']
                calendar_name = calendar.get('summary', calendar_id)

                # Skip calendars that are hidden or not selected
                if not calendar.get('selected', True):
                    continue

                try:
                    events_result = service.events().list(
                        calendarId=calendar_id,
                        timeMin=start_time,
                        timeMax=end_time,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()

                    events = events_result.get('items', [])

                    # Add calendar name to each event
                    for event in events:
                        event['calendar_name'] = calendar_name
                        all_events.append(event)

                except Exception as e:
                    print(f"Error fetching events from calendar {calendar_name}: {e}")
                    continue

            # Sort all events by start time
            all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))

            # Group events by date
            events_by_date = {}
            for event in all_events:
                start = event.get('start', {})

                if 'dateTime' in start:
                    event_date = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                    event_date_local = event_date.astimezone(user_timezone)
                    date_key = event_date_local.strftime('%Y-%m-%d')

                    time_str = event_date_local.strftime('%I:%M %p')
                else:
                    # All-day event
                    date_key = start['date']
                    time_str = "All day"

                if date_key not in events_by_date:
                    events_by_date[date_key] = []

                events_by_date[date_key].append({
                    'title': event.get('summary', 'No title'),
                    'time': time_str,
                    'location': event.get('location', ''),
                    'description': event.get('description', ''),
                    'calendar': event.get('calendar_name', 'Unknown')
                })

            return events_by_date, updated_credentials

        except Exception as e:
            print(f"Error fetching upcoming events: {e}")
            return {}, None

    def create_event_in_calendar(self, credentials_dict, event_data, calendar_id='primary', timezone='UTC'):
        """Create an event in a specific calendar"""
        try:
            service, updated_credentials = self.build_service(credentials_dict)

            # Prepare event data for Google Calendar API
            event = {
                'summary': event_data['title'],
                'start': {
                    'dateTime': event_data['start_time'].isoformat(),
                    'timeZone': timezone,
                },
                'end': {
                    'dateTime': event_data['end_time'].isoformat(),
                    'timeZone': timezone,
                },
            }

            # Add optional fields
            if event_data.get('location'):
                event['location'] = event_data['location']

            if event_data.get('description'):
                event['description'] = event_data['description']

            # Create the event
            created_event = service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()

            print(f"✅ Event created in calendar {calendar_id}: {created_event.get('id')}")
            return created_event.get('id'), updated_credentials

        except Exception as e:
            print(f"❌ Error creating event: {e}")
            return None, None

    def format_events_for_whatsapp(self, events):
        """Format events list for WhatsApp message"""
        if not events:
            return "No events scheduled for today! 📅"

        message = "📅 *Today's Events*\n\n"

        for i, event in enumerate(events, 1):
            message += f"{i}. *{event['title']}*\n"
            message += f"   🕐 {event['time']}\n"
            message += f"   📂 {event['calendar']}\n"

            if event['location']:
                message += f"   📍 {event['location']}\n"

            if event['description']:
                # Truncate long descriptions
                desc = event['description'][:100] + "..." if len(event['description']) > 100 else event['description']
                message += f"   📝 {desc}\n"

            message += "\n"

        return message.strip()

    def format_upcoming_events_for_whatsapp(self, events_by_date):
        """Format upcoming events for WhatsApp message"""
        if not events_by_date:
            return "No upcoming events! 📅"

        message = "📅 *Upcoming Events*\n\n"

        for date_str, events in events_by_date.items():
            # Format date nicely
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%A, %B %d')

            message += f"*{formatted_date}*\n"

            for event in events:
                message += f"  • {event['title']} - {event['time']}\n"
                message += f"    📂 {event['calendar']}\n"
                if event['location']:
                    message += f"    📍 {event['location']}\n"

            message += "\n"

        return message.strip()