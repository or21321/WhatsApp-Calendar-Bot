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
        self.SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
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
            client_secret=self.client_secret
        )

        # Refresh token if needed
        if credentials.expired:
            credentials.refresh(Request())

        service = build('calendar', 'v3', credentials=credentials)
        return service, credentials

    def get_today_events(self, credentials_dict, timezone='UTC'):
        """Get today's events from Google Calendar"""
        try:
            service, updated_credentials = self.build_service(credentials_dict)

            # Get today's date range
            user_timezone = pytz.timezone(timezone)
            now = datetime.now(user_timezone)
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Convert to UTC for API call
            start_time = start_of_day.astimezone(pytz.UTC).isoformat()
            end_time = end_of_day.astimezone(pytz.UTC).isoformat()

            # Call Google Calendar API
            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Format events for WhatsApp
            formatted_events = []
            for event in events:
                start = event.get('start', {})
                end = event.get('end', {})

                # Handle different event types (all-day vs timed)
                if 'dateTime' in start:
                    # Timed event
                    start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))

                    # Convert to user timezone
                    start_local = start_dt.astimezone(user_timezone)
                    end_local = end_dt.astimezone(user_timezone)

                    time_str = f"{start_local.strftime('%I:%M %p')} - {end_local.strftime('%I:%M %p')}"
                else:
                    # All-day event
                    time_str = "All day"

                formatted_events.append({
                    'title': event.get('summary', 'No title'),
                    'time': time_str,
                    'location': event.get('location', ''),
                    'description': event.get('description', '')
                })

            return formatted_events, updated_credentials

        except Exception as e:
            print(f"Error fetching calendar events: {e}")
            return [], None

    def get_upcoming_events(self, credentials_dict, days=7, timezone='UTC'):
        """Get upcoming events for the next N days"""
        try:
            service, updated_credentials = self.build_service(credentials_dict)

            # Get date range
            user_timezone = pytz.timezone(timezone)
            now = datetime.now(user_timezone)
            end_date = now + timedelta(days=days)

            # Convert to UTC for API call
            start_time = now.astimezone(pytz.UTC).isoformat()
            end_time = end_date.astimezone(pytz.UTC).isoformat()

            # Call Google Calendar API
            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Group events by date
            events_by_date = {}
            for event in events:
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
                    'description': event.get('description', '')
                })

            return events_by_date, updated_credentials

        except Exception as e:
            print(f"Error fetching upcoming events: {e}")
            return {}, None

    def format_events_for_whatsapp(self, events):
        """Format events list for WhatsApp message"""
        if not events:
            return "No events scheduled for today! 📅"

        message = "📅 *Today's Events*\n\n"

        for i, event in enumerate(events, 1):
            message += f"{i}. *{event['title']}*\n"
            message += f"   🕐 {event['time']}\n"

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
                if event['location']:
                    message += f"    📍 {event['location']}\n"

            message += "\n"

        return message.strip()