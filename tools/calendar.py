import os
import datetime
from typing import Optional
import pytz # New import
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'credentials.json'

# --- CONFIGURATION ---
USER_TIMEZONE = 'Asia/Kolkata' 

def get_calendar_service():
    """Authenticates using the Service Account file."""
    creds = None
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    else:
        raise FileNotFoundError("credentials.json not found!")
    return build('calendar', 'v3', credentials=creds)

def get_current_time():
    """
    Returns the current date and time in the USER_TIMEZONE.
    Crucial for the LLM to understand relative dates like "tomorrow".
    """
    tz = pytz.timezone(USER_TIMEZONE)
    now = datetime.datetime.now(tz)
    # returning Weekday helps the LLM calculate "Next Tuesday"
    return now.strftime("%A, %Y-%m-%d %H:%M:%S %Z")

def list_upcoming_events(max_results=5):
    """Lists the upcoming events on the calendar."""
    try:
        service = get_calendar_service()
        calendar_id = os.getenv("CALENDAR_ID", "primary")
        
        # Get 'now' in UTC for the API query
        now_utc = datetime.datetime.utcnow().isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId=calendar_id, timeMin=now_utc,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime').execute()
        
        events = events_result.get('items', [])
        if not events:
            return "No upcoming events found."

        result_strings = []
        for event in events:
            # Google returns date-time in ISO format
            start = event['start'].get('dateTime', event['start'].get('date'))
            result_strings.append(f"Event: {event['summary']} at {start}")
        
        return "\n".join(result_strings)
    except Exception as e:
        return f"Error: {str(e)}"

def check_availability(start_time_iso, end_time_iso):
    """
    Checks availability. 
    NOTE: The LLM must provide start_time_iso in the correct Offset or UTC.
    """
    try:
        service = get_calendar_service()
        calendar_id = os.getenv("CALENDAR_ID", "primary")
        
        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=start_time_iso,
            timeMax=end_time_iso,
            singleEvents=True,
            orderBy='startTime').execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return "Slot is available."
        else:
            conflicts = [f"{e['summary']} ({e['start'].get('dateTime')})" for e in events]
            return f"Conflict detected: {', '.join(conflicts)}"
            
    except Exception as e:
        return f"Error checking availability: {str(e)}"

def create_calendar_event(summary, start_time_iso, end_time_iso):
    """
    Books a meeting.
    The LLM should provide ISO times. We enforce the USER_TIMEZONE to be safe.
    """
    try:
        service = get_calendar_service()
        calendar_id = os.getenv("CALENDAR_ID", "primary")
        
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time_iso, 
                'timeZone': USER_TIMEZONE # Explicitly set timezone
            },
            'end': {
                'dateTime': end_time_iso, 
                'timeZone': USER_TIMEZONE
            },
        }
        
        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        return f"Success! Meeting scheduled: {event.get('htmlLink')}"
        
    except Exception as e:
        return f"Error creating event: {str(e)}"

def find_free_slots(date_iso, duration_minutes=30):
    """Finds free slots starting from date_iso."""
    try:
        service = get_calendar_service()
        calendar_id = os.getenv("CALENDAR_ID", "primary")
        
        # Ensure we work with offsets
        start_dt = datetime.datetime.fromisoformat(date_iso)
        if start_dt.tzinfo is None:
             tz = pytz.timezone(USER_TIMEZONE)
             start_dt = tz.localize(start_dt)
             
        end_search_dt = start_dt + datetime.timedelta(hours=4)
        
        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=start_dt.isoformat(),
            timeMax=end_search_dt.isoformat(),
            singleEvents=True,
            orderBy='startTime').execute()
        
        events = events_result.get('items', [])
        
        # Simple Availability Logic
        free_slots = []
        current_slot = start_dt
        
        while current_slot < end_search_dt and len(free_slots) < 3:
            # Check collision
            is_busy = False
            slot_end = current_slot + datetime.timedelta(minutes=duration_minutes)
            
            for e in events:
                e_start_str = e['start'].get('dateTime')
                if not e_start_str: continue # Skip all-day events for simplicity
                
                # Compare ISO strings (lexicographical comparison works for ISO)
                e_end_str = e['end'].get('dateTime')
                
                if e_start_str <= slot_end.isoformat() and e_end_str >= current_slot.isoformat():
                    is_busy = True
                    break
            
            if not is_busy:
                # Format nicely for the LLM
                free_slots.append(current_slot.strftime("%I:%M %p"))
            
            current_slot += datetime.timedelta(minutes=30)
            
        if not free_slots:
            return "No free slots found in the next 4 hours."
        return f"Found these free slots: {', '.join(free_slots)}"

    except Exception as e:
        return f"Error finding slots: {str(e)}"

def send_calendar_invite(email: Optional):
    pass