import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'credentials.json'

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
    Returns the current date and time in ISO format (UTC).
    Use this to calculate relative dates like 'tomorrow' or 'next Tuesday'.
    """
    return datetime.datetime.utcnow().isoformat() + "Z"

def list_upcoming_events(max_results=5):
    """
    Lists the upcoming events on the calendar.
    Useful for checking what the user already has scheduled.
    """
    try:
        service = get_calendar_service()
        calendar_id = os.getenv("CALENDAR_ID", "primary")
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId=calendar_id, timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime').execute()
        
        events = events_result.get('items', [])
        if not events:
            return "No upcoming events found."

        result_strings = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            result_strings.append(f"Event: {event['summary']} at {start}")
        
        return "\n".join(result_strings)
    except Exception as e:
        return f"Error: {str(e)}"

def check_availability(start_time_iso, end_time_iso):
    """
    Checks if the user is free between start_time_iso and end_time_iso.
    args:
        start_time_iso: Start time in ISO format (e.g., 2025-11-30T14:00:00Z)
        end_time_iso: End time in ISO format (e.g., 2025-11-30T15:00:00Z)
    returns:
        String indicating if the slot is free or lists conflicting events.
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
            return f"Conflict detected. User is busy with: {', '.join(conflicts)}"
            
    except Exception as e:
        return f"Error checking availability: {str(e)}"

def create_calendar_event(summary, start_time_iso, end_time_iso):
    """
    Books a meeting on the calendar.
    args:
        summary: Title of the meeting (e.g., "Meeting with Client")
        start_time_iso: Start time in ISO format
        end_time_iso: End time in ISO format
    """
    try:
        service = get_calendar_service()
        calendar_id = os.getenv("CALENDAR_ID", "primary")
        
        event = {
            'summary': summary,
            'start': {'dateTime': start_time_iso, 'timeZone': 'UTC'},
            'end': {'dateTime': end_time_iso, 'timeZone': 'UTC'},
        }
        
        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        return f"Success! Meeting scheduled: {event.get('htmlLink')}"
        
    except Exception as e:
        return f"Error creating event: {str(e)}"