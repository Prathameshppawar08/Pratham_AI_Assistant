from flask import Flask, request, jsonify
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os
import json
import sqlite3
from datetime import datetime
import pytz
app = Flask(__name__)



# Get current date and time in Asia/Kolkata timezone (or any other timezone)
india_tz = pytz.timezone('Asia/Kolkata')
current_time = datetime.now(india_tz)

# Format it as a string
current_date = current_time.strftime("%Y-%m-%d %H:%M:%S")
print(f"Current Date and Time: {current_date}")

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Initialize Gemini model
model = ChatGoogleGenerativeAI(model='gemini-1.5-pro', google_api_key=GOOGLE_API_KEY)

# SQLite setup
def create_connection():
    conn = sqlite3.connect('notes.db')
    return conn

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

# Create table if not exists
create_table()

def ask_llm_to_decide(user_input):
    prompt = f"""
You are a helpful AI assistant that helps manage notes.

User's message: "{user_input}"

Your task:
- Decide if the user wants to **ADD** or **RETRIEVE** a note.
- Extract the **topic name** they are referring to.

Strictly output ONLY valid JSON like:
{{
  "action": "add" or "retrieve",
  "topic": "topic name"
}}

Do not add any explanation or text outside the JSON.
"""
    response = model.invoke(prompt)
    content = response.content.strip()

    # Extract JSON part safely
    try:
        json_start = content.index('{')
        json_end = content.rindex('}') + 1
        json_content = content[json_start:json_end]
        decision = json.loads(json_content)
        return decision
    except Exception as e:
        print("Error parsing LLM response:", e)
        return None


@app.route('/handle_note', methods=['POST'])
def handle_note():
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({"response": "No input received."})
    
    decision = ask_llm_to_decide(user_input)
    if not decision:
        return jsonify({"response": "Sorry, couldn't understand the request."})
    
    action = decision.get("action")
    topic = decision.get("topic")
    
    if action == "add":
        points = request.json.get("points")
        if not points:
            return jsonify({"response": "No points provided. Please include points for the note."})
        insert_or_update_notes(topic, points)
        return jsonify({"response": f"Note added for topic '{topic}'!"})
    
    elif action == "retrieve":
        note = get_notes(topic)
        if note:
            return jsonify({"response": f"Here are your notes for '{topic}':", "points": note})
        else:
            return jsonify({"response": f"No note found for topic: {topic}"})
    
    else:
        return jsonify({"response": "Sorry, couldn't understand your intent."})

@app.route('/view_all_notes', methods=['GET'])
def view_all_notes():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT topic, points FROM notes''')
    rows = cursor.fetchall()
    conn.close()
    
    if rows:
        notes_dict = {topic: json.loads(points) for topic, points in rows}
        return jsonify({"response": "Here are all your notes:", "notes": notes_dict})
    else:
        return jsonify({"response": "No notes found."})
    

from flask import Flask, request, jsonify
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os
import json
import sqlite3
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth import exceptions

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
CLIENT_SECRET_FILE = 'backend/credentials.json'
SCOPES = ['https://www.googleapis.com/auth/calendar']

app = Flask(__name__)
model = ChatGoogleGenerativeAI(model='gemini-1.5-pro', google_api_key=GOOGLE_API_KEY)
creds = None

# ----------------- Calendar Authentication -----------------
def get_credentials():
    global creds
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        return creds
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    return creds

def create_event(event_details):
    creds = get_credentials()
    try:
        service = build('calendar', 'v3', credentials=creds)
        event = service.events().insert(calendarId='primary', body=event_details).execute()
        return event
    except exceptions.GoogleAuthError as error:
        return {"error": f"An error occurred: {error}"}

# ----------------- LLM Prompt Logic -----------------
def extract_event_details_with_llm(user_input):
    prompt = f"""
You are a helpful assistant that extracts event information from a user message.

User input: "{user_input}"

Extract the following fields:
- title (e.g., 'Project Meeting')
- start_time (ISO 8601 format preferred, assume Asia/Kolkata timezone if not specified)
- duration_minutes (duration of the meeting in minutes)


If any information is missing, use the following defaults:
- start_time: tomorrow at 10:00 AM
- duration_minutes: 60
- title: Use user's input as the title
- if year is not specified take 2025


Return the response in strict JSON format:
{{
  "title": "...",
  "start_time": "...",
  "duration_minutes": ...
}}
"""
    response = model.invoke(prompt)
    try:
        json_start = response.content.index('{')
        json_end = response.content.rindex('}') + 1
        return json.loads(response.content[json_start:json_end])
    except Exception as e:
        print("LLM parsing error:", e)
        return None

# ----------------- Flask Endpoint -----------------
@app.route('/schedule_event', methods=['POST'])
def schedule_event():
    try:
        user_input = request.json.get('message')
        if not user_input:
            return jsonify({"response": "Please provide a message with the event details."})

        # Ask LLM to extract structured event data
        parsed = extract_event_details_with_llm(user_input)
        if not parsed:
            return jsonify({"response": "Could not understand your input. Please try again."})

        title = parsed.get("title", user_input)
        start_time_str = parsed.get("start_time")
        duration_minutes = parsed.get("duration_minutes", 60)

        if start_time_str:
            start_time = datetime.fromisoformat(start_time_str)
        else:
            start_time = datetime.now() + timedelta(days=1, hours=10)  # default 10 AM tomorrow

        end_time = start_time + timedelta(minutes=duration_minutes)

        event_details = {
            'summary': title,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
        }

        event = create_event(event_details)
        if 'error' in event:
            return jsonify({"response": event['error']})

        return jsonify({"response": "Event created!", "event_link": event.get('htmlLink')})

    except Exception as e:
        return jsonify({"response": f"An error occurred: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=True)




