import streamlit as st
import requests
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase
import speech_recognition as sr
import av

API_URL = "http://localhost:5000/assistant"  # Change when deployed

st.set_page_config(page_title="Pratham AI Assistant", page_icon="🤖")

st.markdown("<h1 style='text-align: center; color: #4CAF50;'>🤖 Pratham AI Assistant</h1>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# Session state for chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# 🎤 Audio processor for converting mic input to text
class AudioToTextProcessor(AudioProcessorBase):
    def __init__(self) -> None:
        self.recognizer = sr.Recognizer()
        self.audio = sr.AudioData(b'', 16000, 2)
        self.transcript = ""

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        audio = frame.to_ndarray()
        audio_bytes = audio.tobytes()
        audio_data = sr.AudioData(audio_bytes, frame.sample_rate, 2)

        try:
            text = self.recognizer.recognize_google(audio_data)
            self.transcript = text
            st.session_state.voice_input = text
        except sr.UnknownValueError:
            self.transcript = ""
        except sr.RequestError as e:
            self.transcript = f"[Error: {e}]"

        return frame

# Voice input section
st.markdown("### 🎙️ Or try voice input:")
webrtc_streamer(
    key="speech",
    audio_processor_factory=AudioToTextProcessor,
    media_stream_constraints={"video": False, "audio": True},
    async_processing=True
)

# Use transcript if available
default_input = st.session_state.get("voice_input", "")

# Form
with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("💬 Type or speak your request:", value=default_input, placeholder="E.g., Schedule a meeting...")
    note_points = st.text_area("📝 Optional note points:", "")
    submitted = st.form_submit_button("Send")

# Show chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle request
if submitted and user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("assistant"):
        response_area = st.empty()
        response_area.markdown("🧠 Thinking...")

    try:
        data = {"message": user_input, "points": note_points}
        res = requests.post(API_URL, json=data)

        if res.status_code == 200:
            result = res.json().get("response", "🤖 No response from assistant.")
        else:
            result = "❌ Failed to get a valid response."
    except Exception as e:
        result = f"⚠️ Error: {e}"

    response_area.markdown(result)
    st.session_state.messages.append({"role": "assistant", "content": result})
