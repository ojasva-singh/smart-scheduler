import os
import chainlit as cl
from dotenv import load_dotenv
import google.generativeai as genai
from google.cloud import speech # Replaces Deepgram
from elevenlabs.client import ElevenLabs
from tools.calendar import list_upcoming_events, get_current_time, check_availability, create_calendar_event, find_free_slots
import datetime

# 1. Load Config
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# AUTHENTICATION FIX: Point Google Cloud libs to your credentials file
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

# 2. Configure Clients
genai.configure(api_key=GOOGLE_API_KEY)
speech_client = speech.SpeechClient() # Google STT Client
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# 3. Configure Gemini Model with Tools
# Map the string name to the actual function
tools_map = {
    'list_upcoming_events': list_upcoming_events,
    'get_current_time': get_current_time,
    'check_availability': check_availability,
    'create_calendar_event': create_calendar_event,
    'find_free_slots': find_free_slots
}

# Pass the actual functions to Gemini
tools = [list_upcoming_events, get_current_time, check_availability, create_calendar_event, find_free_slots]

model = genai.GenerativeModel('gemini-2.5-flash', tools=tools)

@cl.on_chat_start
async def start():
    """Initializes the chat session."""
    
    # 1. Fetch the REAL current time with Timezone
    current_time_str = get_current_time()
    
    # 2. Advanced System Prompt
    system_instruction = f"""
    You are a smart scheduling assistant.
    
    CONTEXT:
    - Current Time: {current_time_str}
    - Timezone: Asia/Kolkata (IST)
    
    INSTRUCTIONS FOR TIME PARSING:
    - If user says "tomorrow", calculate the date based on Current Time.
    - If user says "next Tuesday", find the date for the upcoming Tuesday.
    - If user says "2 PM", assume 2 PM IST (14:00).
    - Convert all relative times to ISO 8601 format (YYYY-MM-DDTHH:MM:SS) for tool calls.
    
    PROTOCOL:
    1. Check 'get_current_time' first if context is missing.
    2. ALWAYS call 'check_availability' or 'find_free_slots' before confirming.
    3. Be concise. Spoken answers should be under 10 words if possible.
    """

    chat = model.start_chat(history=[
        {"role": "user", "parts": system_instruction}
    ])
    cl.user_session.set("chat", chat)
    
    await cl.Message(content="🎙️ Smart Scheduler Ready (IST Mode).").send()

@cl.on_audio_end
async def on_audio_end(elements: list[cl.Audio]):
    """
    Pipeline: Audio -> Google STT -> Gemini -> TTS -> Audio
    """
    try:
        # --- A. Speech to Text (Google Cloud) ---
        audio_file_path = elements[0].path
        
        # Read the file
        with open(audio_file_path, "rb") as file:
            content = file.read()

        audio = speech.RecognitionAudio(content=content)
        
        # Configure for the audio type Chainlit sends (usually WebM/Opus or Wav)
        # We generally treat it as WEBM_OPUS for browser audio
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=48000,
            language_code="en-US",
            model="default"
        )

        # Call Google STT
        response = speech_client.recognize(config=config, audio=audio)
        
        # Extract text
        if not response.results:
            return # No speech detected
            
        user_text = response.results[0].alternatives[0].transcript
        
        # Display what the user said
        await cl.Message(content=f"🗣️ **You:** {user_text}").send()

        # --- B. Brain Processing (Gemini + Tools) ---
        chat = cl.user_session.get("chat")
        
        # Send message to Gemini
        gemini_response = chat.send_message(user_text)
        
        # Check if Gemini wants to call a function
        final_text_response = ""
        part = gemini_response.candidates[0].content.parts[0]
        
        if part.function_call:
            function_call = part.function_call
            function_name = function_call.name
            
            await cl.Message(content=f"⚙️ *Calling Tool: {function_name}...*").send()
            
            if function_name in tools_map:
                tool_result = tools_map[function_name]()
            else:
                tool_result = "Error: Tool not found."
                
            final_response = chat.send_message(
                genai.protos.Content(
                    parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=function_name,
                            response={'result': tool_result}
                        )
                    )]
                )
            )
            final_text_response = final_response.text
        else:
            final_text_response = gemini_response.text

        # Display Gemini's text response
        await cl.Message(content=f"🤖 **Gemini:** {final_text_response}").send()

        # --- C. Text to Speech (ElevenLabs) ---
        audio_stream = elevenlabs_client.generate(
            text=final_text_response,
            voice="Rachel",
            model="eleven_turbo_v2_5", # reduces the tts generateion time
            stream=True # This will reduce time to first byte 
        )
        
        audio_bytes = b""
        for chunk in audio_stream:
            if chunk:
                audio_bytes+=chunk
        
        await cl.Message(
            content="",
            elements=[cl.Audio(content=audio_bytes, name="response.mp3", auto_play=True)]
        ).send()

    except Exception as e:
        await cl.Message(content=f"❌ Error: {str(e)}").send()

@cl.on_message
async def main(message: cl.Message):
    """Fallback for typing."""
    await cl.Message(content="ℹ️ Please use the microphone button.").send()