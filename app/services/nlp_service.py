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
            print("spaCy model not found. Run: python -m spacy download en_core_web_sm")
            self.nlp = None

        # Hebrew date translations
        self.hebrew_days = {
            'היום': 'today',
            'מחר': 'tomorrow',
            'מחרתיים': 'day after tomorrow',
            'ראשון': 'sunday',
            'שני': 'monday',
            'שלישי': 'tuesday',
            'רביעי': 'wednesday',
            'חמישי': 'thursday',
            'שישי': 'friday',
            'שבת': 'saturday',
            'יום ראשון': 'sunday',
            'יום שני': 'monday',
            'יום שלישי': 'tuesday',
            'יום רביעי': 'wednesday',
            'יום חמישי': 'thursday',
            'יום שישי': 'friday',
            'יום שבת': 'saturday'
        }

        # Event keywords for better detection
        self.event_keywords = {
            'meeting': ['meeting', 'meet', 'call', 'conference', 'discussion', 'פגישה', 'פגש'],
            'appointment': ['appointment', 'visit', 'checkup', 'session', 'תור'],
            'social': ['lunch', 'dinner', 'coffee', 'drink', 'party', 'event', 'ארוחה', 'קפה'],
            'work': ['standup', 'review', 'interview', 'presentation', 'demo', 'עבודה'],
            'personal': ['workout', 'gym', 'doctor', 'dentist', 'haircut', 'רופא', 'רופאה', 'אימון']
        }

    def parse_event(self, text: str, user_timezone: str = 'UTC') -> Optional[Dict]:
        """Main parsing function - converts natural language to event data"""
        if not self.nlp:
            return None

        print("Parsing: " + text)

        # Clean and normalize text
        text = self.preprocess_text(text)
        doc = self.nlp(text)

        # Extract components
        title = self.extract_title(text, doc)
        datetime_info = self.extract_datetime_enhanced(text, user_timezone)
        location = self.extract_location(text, doc)
        duration = self.extract_duration(text)

        print("Title: " + str(title))
        print("DateTime: " + str(datetime_info))
        print("Location: " + str(location))
        print("Duration: " + str(duration))

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

        print("Confidence: " + str(confidence) + "%")
        return result

    def extract_datetime_enhanced(self, text: str, user_timezone: str) -> Optional[Dict]:
        """Enhanced datetime extraction with Hebrew support"""

        print("Enhanced datetime extraction from: " + text)

        # Try Hebrew date/time extraction first
        hebrew_result = self.extract_hebrew_datetime(text, user_timezone)
        if hebrew_result:
            print("Hebrew datetime found")
            return hebrew_result

        # Fallback to original method
        return self.extract_datetime(text, user_timezone)

    def extract_hebrew_datetime(self, text: str, user_timezone: str) -> Optional[Dict]:
        """Extract Hebrew date and time patterns"""

        print("Extracting Hebrew datetime from: " + text)

        # Find Hebrew date
        hebrew_date = None
        for hebrew_day, english_day in self.hebrew_days.items():
            if hebrew_day in text:
                print("Found Hebrew date: " + hebrew_day + " -> " + english_day)
                parsed_date = dateparser.parse(
                    english_day,
                    settings={
                        'PREFER_DATES_FROM': 'future',
                        'TIMEZONE': user_timezone,
                        'RETURN_AS_TIMEZONE_AWARE': True
                    }
                )
                if parsed_date:
                    hebrew_date = parsed_date
                    break

        # Find Hebrew time
        hebrew_time = None

        # Hebrew time patterns
        hebrew_time_patterns = [
            r'בשעה\s+(\d{1,2}):(\d{2})',  # בשעה 14:00
            r'בשעה\s+(\d{1,2})',  # בשעה 14
            r'ב(\d{1,2}):(\d{2})',  # ב14:00
            r'(\d{1,2}):(\d{2})',  # 14:00
        ]

        for pattern in hebrew_time_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if len(match.groups()) >= 2 and match.group(2) else 0

                    print("Found Hebrew time: " + str(hour) + ":" + str(minute).zfill(2))

                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        hebrew_time = {'hour': hour, 'minute': minute}
                        break
                except (ValueError, IndexError):
                    continue

        # Combine date and time
        if hebrew_date and hebrew_time:
            combined_datetime = hebrew_date.replace(
                hour=hebrew_time['hour'],
                minute=hebrew_time['minute'],
                second=0,
                microsecond=0
            )

            print("Combined Hebrew datetime: " + str(combined_datetime))
            return {'start': combined_datetime}

        # If we have date but no time, set default time
        elif hebrew_date:
            default_time = hebrew_date.replace(hour=9, minute=0, second=0, microsecond=0)
            print("Hebrew date with default time: " + str(default_time))
            return {'start': default_time}

        # If we have time but no date, assume today
        elif hebrew_time:
            now = datetime.now(pytz.timezone(user_timezone))
            time_today = now.replace(
                hour=hebrew_time['hour'],
                minute=hebrew_time['minute'],
                second=0,
                microsecond=0
            )
            print("Hebrew time today: " + str(time_today))
            return {'start': time_today}

        return None

    def preprocess_text(self, text: str) -> str:
        """Clean and normalize input text"""
        # Convert common abbreviations
        replacements = {
            'tmrw': 'tomorrow',
            'tom': 'tomorrow',
            'tomorow': 'tomorrow',
            'tomoroworrow': 'tomorrow',
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

        print("Title extraction from: " + text)

        # Strategy 1: Hebrew-aware pattern extraction
        hebrew_title_patterns = [
            # Hebrew patterns first
            r'(פגישה\s+עם\s+.+?)(?:\s+(?:מחר|היום|בשעה|\d{1,2}:\d{2}))',
            r'(תור\s+.+?)(?:\s+(?:מחר|היום|בשעה|\d{1,2}:\d{2}))',
            r'(.+?)\s+(?:מחר|היום)(?:\s+בשעה)',
            # English patterns
            r'(?:meeting|call|appointment|session)\s+(?:with\s+)?(.+?)(?:\s+(?:on|at|for|tomorrow|today|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:am|pm)))',
            r'(.+?)\s+(?:meeting|appointment|call|session)(?:\s+(?:on|at|for|tomorrow|today|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:am|pm)))',
            # Fallback pattern - capture everything before time/date indicators
            r'(.+?)(?:\s+(?:on|at|for|tomorrow|today|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday|מחר|היום|בשעה|\d{1,2}(?::|am|pm)))',
        ]

        for pattern in hebrew_title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                print("Pattern matched: " + title)
                if len(title) > 1 and not self.is_time_expression(title) and not self.is_date_word(title):
                    cleaned_title = self.clean_title(title)
                    print("Cleaned title: " + cleaned_title)
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

        print("Entities - Persons: " + str(persons) + ", Orgs: " + str(orgs) + ", Events: " + str(events))

        # Build title from entities
        if events:
            return events[0]
        elif persons:
            return "Meeting with " + ', '.join(persons)
        elif orgs:
            return "Meeting with " + orgs[0]

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
                                    word_clean not in ['on', 'at', 'for', 'with', 'a', 'an', 'the', 'and', 'עם', 'ב', 'ו']):
                                    context_words.append(words[j])

                            if len(context_words) >= 2:
                                title = ' '.join(context_words[:4])  # Take first 4 meaningful words
                                print("Keyword-based title: " + title)
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
            print("Fallback title: " + title)
            return self.clean_title(title)

        print("No title found")
        return None

    def extract_datetime(self, text: str, user_timezone: str) -> Optional[Dict]:
        """Extract date and time information"""

        print("Extracting datetime from: " + text + " in timezone: " + user_timezone)

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

            print("Combined datetime: " + str(result))
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
            print("Dateparser result: " + str(result))
            return result

        print("No datetime found")
        return None

    def extract_time_from_text_improved(self, text: str) -> Optional[Dict]:
        """Improved time extraction with better pattern matching"""

        print("Extracting time from: " + text)

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
                print("Time pattern matched: " + str(groups))

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

                        print("Converted " + str(hour) + ampm + " to " + str(hour_24) + ":00")

                        return {
                            'hour': hour_24,
                            'minute': minute
                        }

                    elif len(groups) >= 2:  # 24-hour format
                        hour = int(groups[0])
                        minute = int(groups[1])

                        if 0 <= hour <= 23 and 0 <= minute <= 59:
                            print("24-hour time: " + str(hour) + ":" + str(minute).zfill(2))
                            return {
                                'hour': hour,
                                'minute': minute
                            }

                except (ValueError, IndexError) as e:
                    print("Error parsing time: " + str(e))
                    continue

        print("No time pattern found")
        return None

    def extract_date_from_text(self, text: str, user_timezone: str) -> Optional[datetime]:
        """Extract date from text with Hebrew support"""

        # Check Hebrew dates first
        for hebrew_day, english_day in self.hebrew_days.items():
            if hebrew_day in text:
                print("Found Hebrew date: " + hebrew_day + " -> " + english_day)
                parsed_date = dateparser.parse(
                    english_day,
                    settings={
                        'PREFER_DATES_FROM': 'future',
                        'TIMEZONE': user_timezone,
                        'RETURN_AS_TIMEZONE_AWARE': True
                    }
                )
                if parsed_date:
                    print("Parsed Hebrew date: " + str(parsed_date))
                    return parsed_date

        # English date patterns
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
                print("Found date pattern: " + pattern)
                parsed_date = dateparser.parse(
                    pattern,
                    settings={
                        'PREFER_DATES_FROM': 'future',
                        'TIMEZONE': user_timezone,
                        'RETURN_AS_TIMEZONE_AWARE': True
                    }
                )
                if parsed_date:
                    print("Parsed date: " + str(parsed_date))
                    return parsed_date

        print("No date found")
        return None

    def extract_calendar_name(self, text: str) -> Optional[str]:
        """Extract calendar name from text"""

        print("Extracting calendar from: " + text)

        # Enhanced patterns to capture full names including Hebrew
        calendar_patterns = [
            r'calendar\s+(.+?)$',
            r'in\s+calendar\s+(.+?)$',
            r'to\s+calendar\s+(.+?)$',
            r'(?:in|to|on)\s+calendar\s+(.+)',
            r'calendar\s+([^\s].+?)(?:\s*$)',
        ]

        for pattern in calendar_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
            if match:
                calendar_name = match.group(1).strip()

                # Don't extract if it's too short
                if len(calendar_name) >= 2:
                    print("Found calendar name: " + calendar_name)
                    return calendar_name

        print("No calendar name found")
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
        elif any(word in title_lower for word in ['lunch', 'dinner', 'coffee', 'drink', 'ארוחה', 'קפה']):
            return timedelta(hours=1)
        elif any(word in title_lower for word in ['doctor', 'dentist', 'appointment', 'רופא', 'רופאה', 'תור']):
            return timedelta(minutes=30)
        elif any(word in title_lower for word in ['interview', 'presentation', 'demo']):
            return timedelta(hours=1)
        elif any(word in title_lower for word in ['workout', 'gym', 'exercise', 'אימון']):
            return timedelta(hours=1)
        elif any(word in title_lower for word in ['פגישה', 'meeting']):
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
        if any(word in original_text.lower() for word in ['schedule', 'add', 'create', 'meeting', 'appointment', 'פגישה', 'תור']):
            score += 5

        return min(score, 100)

    def is_time_expression(self, text: str) -> bool:
        """Check if text is a time expression"""
        time_words = ['am', 'pm', 'morning', 'afternoon', 'evening', 'tonight', 'hour', 'minute', 'o\'clock', 'בשעה', 'שעה']
        return any(word in text.lower() for word in time_words) or bool(re.search(r'\d+:\d+|\d+\s*(am|pm)', text, re.IGNORECASE))

    def is_date_word(self, text: str) -> bool:
        """Check if text is a date-related word"""
        date_words = ['today', 'tomorrow', 'yesterday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'next', 'this', 'last', 'היום', 'מחר', 'ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']
        return text.lower() in date_words

    def convert_to_24h(self, hour: int, ampm: str) -> int:
        """Convert 12-hour to 24-hour format"""
        ampm_lower = ampm.lower()

        if ampm_lower == 'am':
            # 12 AM = 0 (midnight), 1-11 AM stay the same
            return 0 if hour == 12 else hour
        else:  # pm
            # 12 PM = 12 (noon), 1-11 PM add 12
            return 12 if hour == 12 else hour + 12

    def clean_title(self, title: str) -> str:
        """Clean and format the extracted title"""
        # Remove common prefixes but be more careful
        prefixes_to_remove = ['a ', 'an ', 'the ']
        title_lower = title.lower()

        for prefix in prefixes_to_remove:
            if title_lower.startswith(prefix):
                title = title[len(prefix):]
                break

        # Don't remove "meeting with" or "call with" - these are meaningful
        # Don't remove Hebrew prepositions like "עם" (with)
        # Just capitalize appropriately
        return title.strip().title()