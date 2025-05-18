import streamlit as st
import requests
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase
import speech_recognition as sr
import av
import numpy as np

API_URL = "http://localhost:5000/assistant"  # Update this if hosted elsewhere

st.set_page_config(page_title="Pratham AI Assistant", page_icon="🤖")

st.markdown("<h1 style='text-align: center; color: #4CAF50;'>🤖 Pratham AI Assistant</h1>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ---------------- Session state ----------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "voice_transcript" not in st.session_state:
    st.session_state.voice_transcript = ""

if "user_input" not in st.session_state:
    st.session_state.user_input = ""

# ---------------- Audio Processor ----------------
class AudioToTextProcessor(AudioProcessorBase):
    def __init__(self) -> None:
        self.recognizer = sr.Recognizer()

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        audio = frame.to_ndarray()
        audio_bytes = audio.tobytes()
        audio_data = sr.AudioData(audio_bytes, frame.sample_rate, 2)

        try:
            text = self.recognizer.recognize_google(audio_data)
            st.session_state.voice_transcript += " " + text  # Accumulate text
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            st.session_state.voice_transcript += f"[Error: {e}]"

        return frame

# ---------------- Voice Input Section ----------------
st.markdown("### 🎙️ Voice Input (Click Start and then Stop):")
webrtc_ctx = webrtc_streamer(
    key="speech",
    audio_processor_factory=AudioToTextProcessor,
    media_stream_constraints={"video": False, "audio": True},
    async_processing=True,
)

# ---------------- Sync transcript to the input ----------------
if not webrtc_ctx.state.playing and st.session_state.voice_transcript:
    st.session_state.user_input = st.session_state.voice_transcript.strip()
    st.session_state.voice_transcript = ""
    st.experimental_rerun()  # Force Streamlit to rerun to reflect updated input

# ---------------- Chat Form ----------------
with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("💬 Type or speak your request:", value=st.session_state.user_input, key="user_text")
    note_points = st.text_area("📝 Optional note points:", "")
    submitted = st.form_submit_button("Send")

# ---------------- Display Chat History ----------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------- Handle Form Submission ----------------
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
    st.session_state.user_input = ""  # Clear the input after sending