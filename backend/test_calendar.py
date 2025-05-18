import os
import json
import pickle
import datetime
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from langchain_google_genai import ChatGoogleGenerativeAI

# Load .env file for Gemini key
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ------------------- Gemini Setup -------------------
model = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=GOOGLE_API_KEY)

def extract_event_details(user_input):
    prompt = f"""
You are an assistant that extracts calendar event details from user input.

Given this input: "{user_input}"

Return a valid JSON object in the following format:
{{
  "title": "Title of the meeting or event",
  "start_time": "Start time in ISO 8601 format (e.g. 2025-04-30T15:00:00)",
  "duration_hours": number of hours (e.g. 1)
}}

If information is missing, use defaults:
- start_time = now + 1 day at 9:00 AM
- duration_hours = 1
- title = entire user input
"""
    response = model.invoke(prompt)
    try:
        content = response.content.strip()
        json_part = content[content.index('{'): content.rindex('}') + 1]
        return json.loads(json_part)
    except Exception as e:
        print("Failed to parse LLM response:", e)
        print("Raw response:", response.content)
        return None

# ------------------- Google Calendar Setup -------------------
SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRET_FILE = 'credentials.json'
CREDENTIALS_PICKLE = 'token.pickle'

def get_credentials():
    credentials = None
    if os.path.exists(CREDENTIALS_PICKLE):
        with open(CREDENTIALS_PICKLE, 'rb') as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open(CREDENTIALS_PICKLE, 'wb') as token:
            pickle.dump(credentials, token)

    return credentials

def create_event(credentials, event_details):
    service = build('calendar', 'v3', credentials=credentials)

    event = {
        'summary': event_details['summary'],
        'location': event_details['location'],
        'description': event_details['description'],
        'start': {
            'dateTime': event_details['start_time'].isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
        'end': {
            'dateTime': event_details['end_time'].isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    event_result = service.events().insert(calendarId='primary', body=event).execute()
    return event_result

# ------------------- MAIN -------------------
if __name__ == '__main__':
    user_input = input("What would you like to schedule? ")

    extracted = extract_event_details(user_input)

    if not extracted:
        print("❌ Could not extract event details.")
        exit()

    # Handle defaults and conversion
    title = extracted.get("title", user_input)
    duration_hours = extracted.get("duration_hours", 1)

    try:
        start_time = datetime.datetime.fromisoformat(extracted["start_time"])
    except:
        start_time = datetime.datetime.now() + datetime.timedelta(days=1)
        start_time = start_time.replace(hour=9, minute=0, second=0, microsecond=0)

    end_time = start_time + datetime.timedelta(hours=duration_hours)

    event_details = {
        'summary': title,
        'location': 'Virtual/Online',
        'description': f'Scheduled from AI input: "{user_input}"',
        'start_time': start_time,
        'end_time': end_time,
    }
