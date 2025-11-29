import os
import chainlit as cl
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
    """Generates audio stream from text using ElevenLabs."""
    return elevenlabs_client.generate(
        text=text,
        voice="Rachel",
        model="eleven_turbo_v2_5", # Optimized for latency
        stream=True
    )

async def run_agent_logic(user_text, chat_session):
    """
    Core Agent Logic: Sends text to Gemini, handles Tool calls, returns final text.
    """
    # UI Feedback: Show "Thinking" animation
    async with cl.Step(name="Gemini", type="llm") as step:
        step.input = user_text
        
        # 1. Send user text to Gemini
        response = chat_session.send_message(user_text)
        part = response.candidates[0].content.parts[0]
        
        # 2. Check for Tool Calls (Function Calling)
        if part.function_call:
            function_name = part.function_call.name
            function_args = part.function_call.args
            
            # Create a sub-step for the tool
            async with cl.Step(name=function_name, type="tool") as tool_step:
                tool_step.input = f"Args: {function_args}"
                
                if function_name in tools_map:
                    tool_func = tools_map[function_name]
                    try:
                        args_dict = dict(function_args)
                        tool_result = tool_func(**args_dict)
                    except Exception as e:
                        tool_result = f"Error executing tool: {str(e)}"
                else:
                    tool_result = "Error: Tool not found."
                
                tool_step.output = str(tool_result)

            # 3. Send Tool Result back to Gemini
            final_response = chat_session.send_message(
                genai.protos.Content(
                    parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=function_name,
                            response={'result': tool_result}
                        )
                    )]
                )
            )
            final_text = final_response.text
        else:
            final_text = response.text
        
        step.output = final_text
        return final_text

# --- CHAINLIT HANDLERS ---

@cl.on_chat_start
async def start():
    """Setup the session and interactions."""
    
    # 1. Initialize Session Variables
    cl.user_session.set("voice_mode", True)
    
    # 2. Initialize Gemini Chat
    current_time_str = get_current_time()
    system_instruction = f"""
    You are a smart scheduling assistant.
    CONTEXT: Current Time: {current_time_str} | Timezone: Asia/Kolkata (IST)
    RULES:
    1. Check 'get_current_time' for relative dates (tomorrow, next week).
    2. ALWAYS call 'check_availability' or 'find_free_slots' before confirming.
    3. Keep responses CONCISE (max 1-2 sentences) for voice interaction.
    """
    
    chat = model.start_chat(history=[{"role": "user", "parts": system_instruction}])
    cl.user_session.set("chat", chat)
    
    # 3. Create the Toggle Button (Action) with FIXED payload
    actions = [
        cl.Action(name="toggle_voice", payload={"value": "on"}, label="🔊 Voice Mode: ON")
    ]
    
    await cl.Message(content="🎙️ **Smart Scheduler Ready.**", actions=actions).send()

@cl.action_callback("toggle_voice")
async def on_action(action: cl.Action):
    """Handler for the Voice Toggle Button."""
    voice_mode = cl.user_session.get("voice_mode")
    
    if voice_mode:
        # Turn OFF
        cl.user_session.set("voice_mode", False)
        action.label = "🔇 Voice Mode: OFF"
        action.payload["value"] = "off"
        await cl.Message(content="ℹ️ Voice response disabled.").send()
    else:
        # Turn ON
        cl.user_session.set("voice_mode", True)
        action.label = "🔊 Voice Mode: ON"
        action.payload["value"] = "on"
        await cl.Message(content="ℹ️ Voice response enabled.").send()
    
    await action.update()

@cl.on_message
async def on_text_message(message: cl.Message):
    """Handles text input (Typing)."""
    user_text = message.content
    chat = cl.user_session.get("chat")
    
    # Run Agent Logic
    final_text = await run_agent_logic(user_text, chat)
    
    # Check Voice Mode
    voice_mode = cl.user_session.get("voice_mode")
    
    elements = []
    if voice_mode:
        # Generate Audio
        audio_stream = await text_to_speech(final_text)
        audio_bytes = b"".join(audio_stream)
        elements = [cl.Audio(content=audio_bytes, name="reply.mp3", auto_play=True)]
    
    await cl.Message(content=final_text, elements=elements).send()

@cl.on_audio_end
async def on_audio_message(elements: list[cl.Audio]):
    """Handles voice input (Microphone)."""
    try:
        # 1. Transcribe
        audio_path = elements[0].path
        user_text = await speech_to_text(audio_path)
        
        if not user_text:
            await cl.Message(content="😕 I couldn't hear anything.").send()
            return

        # Show transcription to user
        await cl.Message(content=f"🗣️ *You said:* {user_text}", author="User").send()
        
        # 2. Run Agent Logic
        chat = cl.user_session.get("chat")
        final_text = await run_agent_logic(user_text, chat)
        
        # 3. Respond
        voice_mode = cl.user_session.get("voice_mode")
        response_elements = []
        
        if voice_mode:
            audio_stream = await text_to_speech(final_text)
            audio_bytes = b"".join(audio_stream)
            response_elements = [cl.Audio(content=audio_bytes, name="reply.mp3", auto_play=True)]
        
        await cl.Message(content=final_text, elements=response_elements).send()

    except Exception as e:
        await cl.Message(content=f"❌ Error: {str(e)}").send()