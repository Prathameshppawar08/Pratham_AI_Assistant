import os
import json
import pickle
import datetime
import sqlite3
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from langchain_google_genai import ChatGoogleGenerativeAI

from flask_cors import CORS

app = Flask(__name__)
CORS(app) 
# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Initialize LLM
model = ChatGoogleGenerativeAI(model='gemini-1.5-pro', google_api_key=GOOGLE_API_KEY)

# Flask app
app = Flask(__name__)

# Calendar SCOPES
SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_SECRET_FILE = 'backend/credentials.json'
CREDENTIALS_PICKLE = 'token.pickle'

# ---------- Notes Functions ----------
def create_connection():
    return sqlite3.connect('notes.db')

def create_table():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS notes (topic TEXT PRIMARY KEY, points TEXT)''')
    conn.commit()
    conn.close()

def insert_or_update_notes(topic, points):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO notes (topic, points) VALUES (?, ?)''', (topic, json.dumps(points)))
    conn.commit()
    conn.close()

def get_notes(topic):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT points FROM notes WHERE topic = ?''', (topic,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return json.loads(result[0])
    return None

create_table()

# ---------- Google Calendar Functions ----------
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

def create_event(summary, start_time, end_time):
    credentials = get_credentials()
    service = build('calendar', 'v3', credentials=credentials)
    event = {
        'summary': summary,
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 10}]}
    }
    event_result = service.events().insert(calendarId='primary', body=event).execute()
    return event_result

# ---------- LLM Classification ----------
def analyze_user_prompt(prompt):
    analysis_prompt = f"""
You are a helpful assistant. Analyze the user's message and return the intent.

If it's about notes, output:
{{
  "action": "note",
  "note_action": "add" or "retrieve",
  "topic": "topic name"
}}

If it's about scheduling a calendar event, output:
{{
  "action": "calendar",
  "title": "Event title",
  "start": "2025-04-29 17:00",
  "end": "2025-04-29 18:00"
}}

User message: "{prompt}"

Respond ONLY in JSON.
"""
    response = model.invoke(analysis_prompt)
    try:
        json_start = response.content.index('{')
        json_end = response.content.rindex('}') + 1
        return json.loads(response.content[json_start:json_end])
    except Exception as e:
        return {"error": f"LLM parsing error: {str(e)}"}

# ---------- Unified Route ----------
@app.route('/assistant', methods=['POST'])
def assistant():
    user_input = request.json.get("message")
    if not user_input:
        return jsonify({"response": "Please provide a message."})

    decision = analyze_user_prompt(user_input)
    if "error" in decision:
        return jsonify({"response": decision["error"]})

    if decision.get("action") == "note":
        topic = decision.get("topic")
        note_action = decision.get("note_action")
        if note_action == "add":
            points = request.json.get("points")
            if not points:
                return jsonify({"response": "Please include points to add."})
            insert_or_update_notes(topic, points)
            return jsonify({"response": f"Note added for topic '{topic}'."})
        elif note_action == "retrieve":
            note = get_notes(topic)
            return jsonify({"response": note if note else f"No note found for '{topic}'."})
        else:
            return jsonify({"response": "Invalid note action."})

    elif decision.get("action") == "calendar":
        try:
            start_time = datetime.datetime.strptime(decision["start"], "%Y-%m-%d %H:%M")
            end_time = datetime.datetime.strptime(decision["end"], "%Y-%m-%d %H:%M")
            title = decision["title"]
            event = create_event(title, start_time, end_time)
            return jsonify({"response": "Event created.", "event_link": event.get("htmlLink")})
        except Exception as e:
            return jsonify({"response": f"Error creating event: {str(e)}"})

    return jsonify({"response": model.invoke(f"User message: {user_input}").content.strip()})



if __name__ == '__main__':
    app.run(debug=True)