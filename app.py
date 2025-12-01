import os
import chainlit as cl
from chainlit.input_widget import Switch
from dotenv import load_dotenv
import google.generativeai as genai
from google.cloud import speech
from elevenlabs.client import ElevenLabs
from tools.calendar import (
    list_upcoming_events, get_current_time, 
    check_availability, create_calendar_event, find_free_slots
)

# --- CONFIGURATION ---
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Auth for Google Cloud (STT)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

# Configure Clients
genai.configure(api_key=GOOGLE_API_KEY)
speech_client = speech.SpeechClient()
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Configure Gemini Tools
tools_map = {
    'list_upcoming_events': list_upcoming_events,
    'get_current_time': get_current_time,
    'check_availability': check_availability,
    'create_calendar_event': create_calendar_event,
    'find_free_slots': find_free_slots
}
tools = [list_upcoming_events, get_current_time, check_availability, create_calendar_event, find_free_slots]
model = genai.GenerativeModel('gemini-2.5-flash', tools=tools)

# --- HELPER FUNCTIONS ---

async def speech_to_text(audio_file_path):
    """Converts audio file to text using Google Cloud STT."""
    with open(audio_file_path, "rb") as file:
        content = file.read()
    
    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        sample_rate_hertz=48000,
        language_code="en-US",
        model="default"
    )
    response = speech_client.recognize(config=config, audio=audio)
    if not response.results:
        return ""
    return response.results[0].alternatives[0].transcript

async def text_to_speech(text):
    """Generates audio stream using the ElevenLabs SDK."""
    # Using the exact method from your documentation snippet
    audio_generator = elevenlabs_client.text_to_speech.convert(
        text=text,
        voice_id="cgSgspJ2msm6clMCkdW9", # Rachel (Legacy) or similar ID
        model_id="eleven_turbo_v2_5",    # Low latency model
        output_format="mp3_44100_128",
    )
    return audio_generator

async def run_agent_logic(user_text, chat_session):
    """
    Handles the conversation loop. 
    Crucial Fix: Handles Multiple Tool Calls in a row before returning text.
    """
    
    # 1. Send initial message
    response = chat_session.send_message(user_text)
    
    # 2. LOOP: While Gemini wants to call a function, execute it and send results back.
    while True:
        part = response.candidates[0].content.parts[0]
        
        # If it's a function call
        if part.function_call:
            function_name = part.function_call.name
            function_args = part.function_call.args
            
            # UI: Show what tool is running
            async with cl.Step(name=function_name, type="tool") as step:
                step.input = f"Args: {function_args}"
                
                if function_name in tools_map:
                    tool_func = tools_map[function_name]
                    try:
                        args_dict = dict(function_args)
                        tool_result = tool_func(**args_dict)
                    except Exception as e:
                        tool_result = f"Error executing tool: {str(e)}"
                else:
                    tool_result = "Error: Tool not found."
                
                step.output = str(tool_result)

            # Send result back to Gemini and get the NEXT response
            response = chat_session.send_message(
                genai.protos.Content(
                    parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=function_name,
                            response={'result': tool_result}
                        )
                    )]
                )
            )
            # The loop continues... Gemini will either call another tool OR return text.
        else:
            # It's text! We can break the loop.
            break

    return response.text

# --- CHAINLIT HANDLERS ---

@cl.on_chat_start
async def start():
    """Setup session."""
    
    # 1. Settings
    await cl.ChatSettings(
        [Switch(id="VoiceMode", label="Voice Mode (Auto-Speak)", initial=True)]
    ).send()
    cl.user_session.set("voice_mode", True)
    
    # 2. System Prompt
    current_time_str = get_current_time()
    system_instruction = f"""
    You are a professional Executive Scheduling Assistant for Ojasva.
    
    CONTEXT:
    - Current Time: {current_time_str}
    - Timezone: Asia/Kolkata (IST)
    
    STRICT AVAILABILITY RULES:
    - Ojasva ONLY takes meetings during these slots:
      1. Morning: 09:00 AM to 12:00 PM IST
      2. Evening: 04:00 PM to 07:00 PM IST
    - If a user requests time outside these slots, only then politely decline and offer a slot within working hours. Don't tell the working hours until a conflict is there.
    
    EMERGENCY PROTOCOL:
    - If the user insists on an urgent meeting outside working hours, provide this email: ojasva963@gmail.com
    - Do NOT book the meeting yourself if it violates the hours.
    
    BOOKING FLOW:
    1. Understand the request (Day/Time).
    2. CALL 'check_availability' or 'find_free_slots'.
    3. If slot is free AND within working hours -> ASK for:
       - Meeting Title/Purpose
       - User's Email Address
    4. ONLY after getting Title and Email -> CALL 'create_calendar_event'.
    
    STYLE:
    - Concise (spoken style) Maximum 2 sentences.
    - Professional but firm on working hours.
    """
    
    chat = model.start_chat(history=[{"role": "user", "parts": system_instruction}])
    cl.user_session.set("chat", chat)
    
    await cl.Message(content="🎙️ **Smart Scheduler Online.**\n\nI handle Ojasva's calendar (9am-12pm & 4pm-7pm).").send()

@cl.on_settings_update
async def setup_agent(settings):
    cl.user_session.set("voice_mode", settings["VoiceMode"])
    status = "enabled" if settings["VoiceMode"] else "disabled"
    await cl.Message(content=f"ℹ️ Voice response {status}.").send()

@cl.on_message
async def on_text_message(message: cl.Message):
    """Handles text input."""
    user_text = message.content
    chat = cl.user_session.get("chat")
    
    # Run Agent Logic (Now loop-safe)
    final_text = await run_agent_logic(user_text, chat)
    
    voice_mode = cl.user_session.get("voice_mode")
    elements = []
    
    if voice_mode:
        audio_generator = await text_to_speech(final_text)
        # Convert generator to bytes
        audio_bytes = b"".join(audio_generator)
        elements = [cl.Audio(content=audio_bytes, name="reply.mp3", auto_play=True)]
    
    await cl.Message(content=final_text, elements=elements).send()

@cl.on_audio_end
async def on_audio_message(elements: list[cl.Audio]):
    """Handles microphone input."""
    try:
        # 1. Transcribe
        audio_path = elements[0].path
        user_text = await speech_to_text(audio_path)
        
        if not user_text:
            await cl.Message(content="😕 I couldn't hear anything.").send()
            return

        await cl.Message(content=f"🗣️ *You said:* {user_text}", author="User").send()
        
        # 2. Logic
        chat = cl.user_session.get("chat")
        final_text = await run_agent_logic(user_text, chat)
        
        # 3. Speak
        voice_mode = cl.user_session.get("voice_mode")
        response_elements = []
        
        if voice_mode:
            audio_generator = await text_to_speech(final_text)
            audio_bytes = b"".join(audio_generator)
            response_elements = [cl.Audio(content=audio_bytes, name="reply.mp3", auto_play=True)]
        
        await cl.Message(content=final_text, elements=response_elements).send()

    except Exception as e:
        await cl.Message(content=f"❌ Error: {str(e)}").send()