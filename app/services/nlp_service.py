import spacy
import dateparser
from datetime import datetime, timedelta
import re
import pytz
from typing import Dict, Optional, List, Tuple

class SmartEventParser:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            print("❌ spaCy model not found. Run: python -m spacy download en_core_web_sm")
            self.nlp = None

        # Common event keywords for better detection
        self.event_keywords = {
            'meeting': ['meeting', 'meet', 'call', 'conference', 'discussion'],
            'appointment': ['appointment', 'visit', 'checkup', 'session'],
            'social': ['lunch', 'dinner', 'coffee', 'drink', 'party', 'event'],
            'work': ['standup', 'review', 'interview', 'presentation', 'demo'],
            'personal': ['workout', 'gym', 'doctor', 'dentist', 'haircut']
        }

        # Time patterns for better parsing
        self.time_patterns = [
            r'(\d{1,2}):(\d{2})\s*(am|pm)',  # 2:30pm
            r'(\d{1,2})\s*(am|pm)',          # 2pm
            r'(\d{1,2})-(\d{1,2})\s*(am|pm)', # 2-3pm
            r'(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\s*(am|pm)', # 2:30-3:30pm
        ]

    def extract_calendar_name(self, text: str) -> Optional[str]:
        """Extract calendar name from text"""

        print(f"📂 Extracting calendar from: '{text}'")

        # Enhanced patterns to capture full names including Hebrew
        calendar_patterns = [
            # Pattern to capture everything after "calendar" until end of string
            r'calendar\s+(.+?)$',
            # Pattern to capture everything after "in calendar"
            r'in\s+calendar\s+(.+?)$',
            # Pattern to capture everything after "to calendar"
            r'to\s+calendar\s+(.+?)$',
            # Pattern for Hebrew - capture everything after calendar keyword
            r'(?:in|to|on)\s+calendar\s+(.+)',
            # Broader pattern - everything after calendar
            r'calendar\s+([^\s].+?)(?:\s*$)',
        ]

        for pattern in calendar_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
            if match:
                calendar_name = match.group(1).strip()

                # Don't extract if it's too short
                if len(calendar_name) >= 2:
                    print(f"📂 Found calendar name: '{calendar_name}'")
                    return calendar_name

        print("📂 No calendar name found")
        return None

    def parse_event(self, text: str, user_timezone: str = 'UTC') -> Optional[Dict]:
        """Main parsing function - converts natural language to event data"""
        if not self.nlp:
            return None

        print(f"🔍 Parsing: '{text}'")

        # Clean and normalize text
        text = self.preprocess_text(text)
        doc = self.nlp(text)

        # Extract components
        title = self.extract_title(text, doc)
        datetime_info = self.extract_datetime(text, user_timezone)
        location = self.extract_location(text, doc)
        duration = self.extract_duration(text)

        print(f"📝 Title: {title}")
        print(f"📅 DateTime: {datetime_info}")
        print(f"📍 Location: {location}")
        print(f"⏱️ Duration: {duration}")

        if not title:
            return None

        # Calculate start and end times
        if datetime_info:
            start_time = datetime_info['start']
            end_time = datetime_info.get('end')

            if not end_time:
                if duration:
                    end_time = start_time + duration
                else:
                    # Smart default duration based on event type
                    default_duration = self.get_default_duration(title)
                    end_time = start_time + default_duration
        else:
            return None

        # Calculate confidence score
        confidence = self.calculate_confidence(title, datetime_info, location, text)

        result = {
            'title': title,
            'start_time': start_time,
            'end_time': end_time,
            'location': location,
            'confidence': confidence,
            'original_text': text
        }

        print(f"✅ Confidence: {confidence}%")
        return result

    def preprocess_text(self, text: str) -> str:
        """Clean and normalize input text"""
        # Convert common abbreviations
        replacements = {
            'tmrw': 'tomorrow',
            'tom': 'tomorrow',
            'tomorow': 'tomorrow',
            'tomoroworrow': 'tomorrow',  # Fix for your case
            'mins': 'minutes',
            'hr': 'hour',
            'hrs': 'hours',
            'w/': 'with',
            'mtg': 'meeting',
            'appt': 'appointment',
        }

        text_lower = text.lower()
        for abbrev, full in replacements.items():
            text_lower = text_lower.replace(abbrev, full)

        # Remove extra spaces and normalize
        text_lower = ' '.join(text_lower.split())

        return text_lower

    def extract_title(self, text: str, doc) -> Optional[str]:
        """Extract event title using multiple strategies"""

        print(f"🔍 Title extraction from: '{text}'")

        # Strategy 1: Pattern-based extraction (IMPROVED)
        title_patterns = [
            # More specific patterns first
            r'(?:meeting|call|appointment|session)\s+(?:with\s+)?(.+?)(?:\s+(?:on|at|for|tomorrow|today|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:am|pm)))',
            r'(.+?)\s+(?:meeting|appointment|call|session)(?:\s+(?:on|at|for|tomorrow|today|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:am|pm)))',
            r'(?:schedule|add|create|set up|book|plan)\s+(?:a\s+)?(.+?)(?:\s+(?:on|at|for|tomorrow|today|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:am|pm)))',
            # Fallback pattern - capture everything before time/date indicators
            r'(.+?)(?:\s+(?:on|at|for|tomorrow|today|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?::|am|pm)))',
        ]

        for pattern in title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                print(f"📝 Pattern matched: '{title}' with pattern: {pattern[:50]}...")
                if len(title) > 1 and not self.is_time_expression(title) and not self.is_date_word(title):
                    cleaned_title = self.clean_title(title)
                    print(f"📝 Cleaned title: '{cleaned_title}'")
                    return cleaned_title

        # Strategy 2: Entity-based extraction
        persons = []
        orgs = []
        events = []

        for ent in doc.ents:
            if ent.label_ == 'PERSON':
                persons.append(ent.text)
            elif ent.label_ == 'ORG':
                orgs.append(ent.text)
            elif ent.label_ == 'EVENT':
                events.append(ent.text)

        print(f"🏷️ Entities - Persons: {persons}, Orgs: {orgs}, Events: {events}")

        # Build title from entities
        if events:
            return events[0]
        elif persons:
            return f"Meeting with {', '.join(persons)}"
        elif orgs:
            return f"Meeting with {orgs[0]}"

        # Strategy 3: Keyword-based extraction with context
        words = text.split()

        # Look for meeting keywords and extract surrounding context
        for category, keywords in self.event_keywords.items():
            for keyword in keywords:
                if keyword in text.lower():
                    # Find the keyword position and extract context
                    for i, word in enumerate(words):
                        if keyword.lower() in word.lower():
                            # Extract context around the keyword
                            context_start = max(0, i-2)
                            context_end = min(len(words), i+4)
                            context_words = []

                            for j in range(context_start, context_end):
                                word_clean = words[j].lower()
                                # Skip time expressions, dates, and common words
                                if (not self.is_time_expression(words[j]) and
                                    not self.is_date_word(words[j]) and
                                    word_clean not in ['on', 'at', 'for', 'with', 'a', 'an', 'the', 'and']):
                                    context_words.append(words[j])

                            if len(context_words) >= 2:
                                title = ' '.join(context_words[:4])  # Take first 4 meaningful words
                                print(f"📝 Keyword-based title: '{title}'")
                                return self.clean_title(title)

        # Strategy 4: Fallback - extract meaningful words from beginning
        meaningful_words = []
        skip_words = {'schedule', 'add', 'create', 'set', 'up', 'book', 'plan', 'have', 'a', 'an', 'the'}

        for word in words:
            word_clean = word.lower()
            if (word_clean not in skip_words and
                not self.is_time_expression(word) and
                not self.is_date_word(word) and
                len(word) > 1):
                meaningful_words.append(word)
                if len(meaningful_words) >= 3:
                    break

        if meaningful_words:
            title = ' '.join(meaningful_words)
            print(f"📝 Fallback title: '{title}'")
            return self.clean_title(title)

        print("📝 No title found")
        return None

    def extract_datetime(self, text: str, user_timezone: str) -> Optional[Dict]:
        """Extract date and time information (IMPROVED)"""

        print(f"🕐 Extracting datetime from: '{text}' in timezone: {user_timezone}")

        # First, try to extract time separately for better accuracy
        time_match = self.extract_time_from_text_improved(text)
        date_match = self.extract_date_from_text(text, user_timezone)

        if time_match and date_match:
            # Combine date and time
            date_part = date_match
            time_part = time_match

            # Set the time on the date
            combined_datetime = date_part.replace(
                hour=time_part['hour'],
                minute=time_part['minute'],
                second=0,
                microsecond=0
            )

            result = {'start': combined_datetime}

            # Check for end time
            if time_part.get('end_hour'):
                end_datetime = date_part.replace(
                    hour=time_part['end_hour'],
                    minute=time_part.get('end_minute', 0),
                    second=0,
                    microsecond=0
                )
                result['end'] = end_datetime

            print(f"🕐 Combined datetime: {result}")
            return result

        # Fallback to original dateparser approach
        parsed_dt = dateparser.parse(
            text,
            settings={
                'PREFER_DATES_FROM': 'future',
                'TIMEZONE': user_timezone,
                'RETURN_AS_TIMEZONE_AWARE': True
            }
        )

        if parsed_dt:
            result = {'start': parsed_dt}

            # Look for time ranges in the original approach
            time_range = self.extract_time_range(text, parsed_dt)
            if time_range:
                result.update(time_range)

            print(f"🕐 Dateparser result: {result}")
            return result

        print("🕐 No datetime found")
        return None

    def extract_time_from_text_improved(self, text: str) -> Optional[Dict]:
        """Improved time extraction with better pattern matching"""

        print(f"🕐 Extracting time from: '{text}'")

        # Enhanced time patterns with better capturing
        time_patterns = [
            # Range patterns: 2-3pm, 9:30-10:30am
            r'(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)',
            # Single time patterns: 2pm, 9:30am
            r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)',
            # 24-hour format: 14:00, 09:30
            r'(\d{1,2}):(\d{2})(?!\s*(?:am|pm))',
        ]

        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                print(f"🕐 Time pattern matched: {groups} with pattern: {pattern}")

                try:
                    if '-' in pattern and len(groups) >= 5:  # Range pattern
                        start_hour = int(groups[0])
                        start_min = int(groups[1]) if groups[1] else 0
                        end_hour = int(groups[2])
                        end_min = int(groups[3]) if groups[3] else 0
                        ampm = groups[4].lower()

                        # Convert to 24-hour format
                        start_hour_24 = self.convert_to_24h(start_hour, ampm)
                        end_hour_24 = self.convert_to_24h(end_hour, ampm)

                        return {
                            'hour': start_hour_24,
                            'minute': start_min,
                            'end_hour': end_hour_24,
                            'end_minute': end_min
                        }

                    elif len(groups) >= 3 and groups[2]:  # Single time with am/pm
                        hour = int(groups[0])
                        minute = int(groups[1]) if groups[1] else 0
                        ampm = groups[2].lower()

                        # Convert to 24-hour format
                        hour_24 = self.convert_to_24h(hour, ampm)

                        print(f"🕐 Converted {hour}{ampm} to {hour_24}:00")

                        return {
                            'hour': hour_24,
                            'minute': minute
                        }

                    elif len(groups) >= 2:  # 24-hour format
                        hour = int(groups[0])
                        minute = int(groups[1])

                        if 0 <= hour <= 23 and 0 <= minute <= 59:
                            return {
                                'hour': hour,
                                'minute': minute
                            }

                except (ValueError, IndexError) as e:
                    print(f"🕐 Error parsing time: {e}")
                    continue

        print("🕐 No time pattern found")
        return None

    def extract_date_from_text(self, text: str, user_timezone: str) -> Optional[datetime]:
        """Extract date from text"""

        date_patterns = [
            'tomorrow', 'today', 'tonight',
            'next monday', 'next tuesday', 'next wednesday', 'next thursday',
            'next friday', 'next saturday', 'next sunday',
            'this monday', 'this tuesday', 'this wednesday', 'this thursday',
            'this friday', 'this saturday', 'this sunday',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
        ]

        text_lower = text.lower()

        # Try each date pattern
        for pattern in date_patterns:
            if pattern in text_lower:
                print(f"📅 Found date pattern: '{pattern}'")
                parsed_date = dateparser.parse(
                    pattern,
                    settings={
                        'PREFER_DATES_FROM': 'future',
                        'TIMEZONE': user_timezone,
                        'RETURN_AS_TIMEZONE_AWARE': True
                    }
                )
                if parsed_date:
                    print(f"📅 Parsed date: {parsed_date}")
                    return parsed_date

        # Fallback: try to parse the whole text for date
        parsed_date = dateparser.parse(
            text,
            settings={
                'PREFER_DATES_FROM': 'future',
                'TIMEZONE': user_timezone,
                'RETURN_AS_TIMEZONE_AWARE': True
            }
        )

        if parsed_date:
            print(f"📅 Fallback parsed date: {parsed_date}")
            return parsed_date

        print("📅 No date found")
        return None

    def extract_time_range(self, text: str, base_date: datetime) -> Optional[Dict]:
        """Extract time ranges like '2-3pm', '9:30-10:30am'"""

        range_patterns = [
            r'(\d{1,2}):?(\d{2})?\s*-\s*(\d{1,2}):?(\d{2})?\s*(am|pm)',
            r'(\d{1,2})\s*-\s*(\d{1,2})\s*(am|pm)',
            r'from\s+(\d{1,2}):?(\d{2})?\s*(am|pm)\s+to\s+(\d{1,2}):?(\d{2})?\s*(am|pm)',
        ]

        for pattern in range_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()

                    if 'from' in pattern:
                        # "from X to Y" format
                        start_hour = int(groups[0])
                        start_min = int(groups[1]) if groups[1] else 0
                        start_ampm = groups[2]
                        end_hour = int(groups[3])
                        end_min = int(groups[4]) if groups[4] else 0
                        end_ampm = groups[5]
                    else:
                        # "X-Y" format
                        start_hour = int(groups[0])
                        start_min = int(groups[1]) if groups[1] else 0
                        end_hour = int(groups[2])
                        end_min = int(groups[3]) if groups[3] else 0
                        ampm = groups[-1]
                        start_ampm = end_ampm = ampm

                    # Convert to 24-hour format
                    start_hour_24 = self.convert_to_24h(start_hour, start_ampm)
                    end_hour_24 = self.convert_to_24h(end_hour, end_ampm)

                    start_time = base_date.replace(hour=start_hour_24, minute=start_min, second=0, microsecond=0)
                    end_time = base_date.replace(hour=end_hour_24, minute=end_min, second=0, microsecond=0)

                    return {'start': start_time, 'end': end_time}

                except (ValueError, IndexError):
                    continue

        return None

    def extract_time_from_text(self, text: str, base_date: datetime) -> Optional[Dict]:
        """Extract single time from text"""

        for pattern in self.time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    hour = int(groups[0])
                    minute = int(groups[1]) if len(groups) > 1 and groups[1] else 0
                    ampm = groups[-1] if groups[-1] in ['am', 'pm'] else None

                    if ampm:
                        hour_24 = self.convert_to_24h(hour, ampm)
                    else:
                        hour_24 = hour

                    start_time = base_date.replace(hour=hour_24, minute=minute, second=0, microsecond=0)
                    return {'start': start_time}

                except (ValueError, IndexError):
                    continue

        return None

    def extract_location(self, text: str, doc) -> str:
        """Extract location from text"""
        locations = []

        # Entity-based location extraction
        for ent in doc.ents:
            if ent.label_ in ['GPE', 'LOC', 'FAC', 'ORG']:
                locations.append(ent.text)

        # Pattern-based location extraction
        location_patterns = [
            r'(?:at|in|@)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s+(?:on|at|for|tomorrow|today|next|this|\d)|$)',
            r'room\s+([A-Za-z0-9]+)',
            r'office\s+([A-Za-z0-9\s]+?)(?:\s+(?:on|at|for|tomorrow|today|next|this|\d)|$)',
            r'conference\s+room\s+([A-Za-z0-9]+)',
        ]

        for pattern in location_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match and len(match.strip()) > 0:
                    locations.append(match.strip())

        # Return the first reasonable location
        for loc in locations:
            if len(loc) > 1 and not self.is_time_expression(loc):
                return loc

        return ""

    def extract_duration(self, text: str) -> Optional[timedelta]:
        """Extract duration from text"""
        duration_patterns = [
            r'for\s+(\d+)\s+(hours?|hrs?)',
            r'for\s+(\d+)\s+(minutes?|mins?)',
            r'(\d+)\s+(hours?|hrs?)\s+(?:long|meeting|session)',
            r'(\d+)\s+(minutes?|mins?)\s+(?:long|meeting|session)',
            r'(\d+)\s*h\s*(\d+)?m?',  # 1h30m or 2h
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    if 'h' in pattern:  # Special case for "1h30m"
                        hours = int(match.group(1))
                        minutes = int(match.group(2)) if match.group(2) else 0
                        return timedelta(hours=hours, minutes=minutes)
                    else:
                        num = int(match.group(1))
                        unit = match.group(2).lower()

                        if 'hour' in unit or 'hr' in unit:
                            return timedelta(hours=num)
                        elif 'minute' in unit or 'min' in unit:
                            return timedelta(minutes=num)
                except ValueError:
                    continue

        return None

    def get_default_duration(self, title: str) -> timedelta:
        """Get smart default duration based on event type"""
        title_lower = title.lower()

        if any(word in title_lower for word in ['standup', 'daily', 'brief']):
            return timedelta(minutes=15)
        elif any(word in title_lower for word in ['lunch', 'dinner', 'coffee', 'drink']):
            return timedelta(hours=1)
        elif any(word in title_lower for word in ['doctor', 'dentist', 'appointment']):
            return timedelta(minutes=30)
        elif any(word in title_lower for word in ['interview', 'presentation', 'demo']):
            return timedelta(hours=1)
        elif any(word in title_lower for word in ['workout', 'gym', 'exercise']):
            return timedelta(hours=1)
        else:
            return timedelta(hours=1)  # Default 1 hour

    def calculate_confidence(self, title: str, datetime_info: Dict, location: str, original_text: str) -> int:
        """Calculate confidence score for the parsing"""
        score = 0

        # Title quality (40 points max)
        if title:
            if len(title) > 2:
                score += 20
            if any(keyword in title.lower() for keywords in self.event_keywords.values() for keyword in keywords):
                score += 10
            if len(title.split()) >= 2:
                score += 10

        # DateTime quality (40 points max)
        if datetime_info:
            score += 30
            if datetime_info.get('end'):
                score += 10

        # Location (10 points max)
        if location and len(location) > 1:
            score += 10

        # Original text quality (10 points max)
        if len(original_text.split()) >= 4:
            score += 5
        if any(word in original_text.lower() for word in ['schedule', 'add', 'create', 'meeting', 'appointment']):
            score += 5

        return min(score, 100)

    def is_time_expression(self, text: str) -> bool:
        """Check if text is a time expression"""
        time_words = ['am', 'pm', 'morning', 'afternoon', 'evening', 'tonight', 'hour', 'minute', 'o\'clock']
        return any(word in text.lower() for word in time_words) or bool(re.search(r'\d+:\d+|\d+\s*(am|pm)', text, re.IGNORECASE))

    def is_date_word(self, text: str) -> bool:
        """Check if text is a date-related word"""
        date_words = ['today', 'tomorrow', 'yesterday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'next', 'this', 'last']
        return text.lower() in date_words

    def convert_to_24h(self, hour: int, ampm: str) -> int:
        """Convert 12-hour to 24-hour format (FIXED)"""
        ampm_lower = ampm.lower()

        if ampm_lower == 'am':
            # 12 AM = 0 (midnight), 1-11 AM stay the same
            return 0 if hour == 12 else hour
        else:  # pm
            # 12 PM = 12 (noon), 1-11 PM add 12
            return 12 if hour == 12 else hour + 12

    def set_smart_default_time(self, date: datetime) -> datetime:
        """Set smart default time based on current time and date"""
        now = datetime.now(date.tzinfo)

        if date.date() == now.date():  # Today
            # If it's before 9 AM, default to 9 AM
            if now.hour < 9:
                return date.replace(hour=9, minute=0, second=0, microsecond=0)
            # Otherwise, round to next hour
            else:
                return date.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
        else:  # Future date
            return date.replace(hour=9, minute=0, second=0, microsecond=0)  # Default to 9 AM

    def clean_title(self, title: str) -> str:
        """Clean and format the extracted title (IMPROVED)"""
        # Remove common prefixes but be more careful
        prefixes_to_remove = ['a ', 'an ', 'the ']
        title_lower = title.lower()

        for prefix in prefixes_to_remove:
            if title_lower.startswith(prefix):
                title = title[len(prefix):]
                break

        # Don't remove "meeting with" or "call with" - these are meaningful
        # Just capitalize appropriately
        return title.strip().title()