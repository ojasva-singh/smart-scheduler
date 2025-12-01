import os
import chainlit as cl
from chainlit.input_widget import Switch
from dotenv import load_dotenv
import google.generativeai as genai
from google.cloud import speech
from elevenlabs.client import ElevenLabs
from tools.calendar import (
    list_upcoming_events, get_current_time, 
    check_availability, create_calendar_event, find_free_slots, send_calendar_invite
)
#from groq import Groq
import wave

# --- CONFIGURATION ---
load_dotenv()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
# deepgram_client = DeepgramClient(DEEPGRAM_API_KEY)
# groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
    'find_free_slots': find_free_slots,
    'send_calendar_invite': send_calendar_invite
}
tools = [list_upcoming_events, get_current_time, check_availability, create_calendar_event, find_free_slots]
model = genai.GenerativeModel('gemini-2.5-flash', tools=tools)

# --- HELPER FUNCTIONS ---

async def speech_to_text(audio_file_path):
    """Converts audio using Google Cloud STT with WAV."""
    try:
        # Read raw audio data
        with open(audio_file_path, "rb") as f:
            raw_audio = f.read()
        
        print(f"🎵 Raw audio size: {len(raw_audio)} bytes")
        
        # Create WAV file
        wav_path = audio_file_path.replace(".webm", ".wav")
        
        with wave.open(wav_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit samples
            wav_file.setframerate(48000)  # 48kHz sample rate
            wav_file.writeframes(raw_audio)
        
        # Read the WAV file
        with open(wav_path, "rb") as wav_file:
            content = wav_file.read()
        
        print(f"🔄 Created WAV: {len(content)} bytes")
        
        # Configure for LINEAR16 (WAV format)
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=48000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            audio_channel_count=1
        )
        
        print("🔍 Calling Google STT API...")
        response = speech_client.recognize(config=config, audio=audio)
        
        # Cleanup
        os.remove(wav_path)
        
        if not response.results:
            print("⚠️ No transcription results")
            return ""
        
        transcript = response.results[0].alternatives[0].transcript
        print(f"✅ Transcript: {transcript}")
        return transcript
        
    except Exception as e:
        print(f"❌ STT Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return ""


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
    
    DECISION TREE (Follow this strictly):
    
    CASE 1: User asks "What do I have?" or "Am I busy?"
    -> ACTION: Call 'list_upcoming_events'.
    -> Summarize the events concisely.

    CASE 2: User gives DATE but NO TIME (e.g., "Book slot for tomorrow")
    -> ACTION: Ask "Would you prefer a Morning or Evening slot?"
    -> DO NOT call booking tools yet.
    
    CASE 3: User gives VAGUE TIME (e.g., "Tomorrow Morning")
    -> ACTION: Call 'find_free_slots'. 
    -> IMPORTANT: Set the tool's 'date_iso' time to 09:00:00 for Morning or 16:00:00 for Evening.
    
    CASE 4: User gives SPECIFIC TIME (e.g., "Tomorrow at 10 AM")
    -> ACTION: Call 'check_availability'.
    
    CASE 5: Slot is Free & Inside Working Hours
    -> ACTION: Ask for Meeting Title & a User Email (The user email is not mandatory).
    -> After getting the TITLE -> CALL 'create_calendar_event'.
    -> IF Email is mentioned -> CALL 'send_calendar_invite'.

    STYLE:
    - Concise (spoken style), max 2 sentences.
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

@cl.on_audio_start
async def on_audio_start():
    """Initialize audio session - REQUIRED for audio to work."""
    print("🎤 Audio recording started")
    # Use a list to collect chunks (more reliable than bytearray)
    cl.user_session.set("audio_chunks", [])
    cl.user_session.set("audio_mime_type", "audio/webm")
    return True


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    """Collect incoming audio chunks."""
    print(f"📦 Received chunk: {len(chunk.data)} bytes")
    
    # Append chunk to list
    audio_chunks = cl.user_session.get("audio_chunks")
    audio_chunks.append(chunk.data)
    cl.user_session.set("audio_chunks", audio_chunks)


@cl.on_audio_end
async def on_audio_end():
    """Process the complete audio recording - NO PARAMETERS."""
    try:
        print("🛑 Audio recording ended")
        
        # 1. Retrieve collected chunks
        audio_chunks = cl.user_session.get("audio_chunks")
        
        print(f"📊 Total chunks collected: {len(audio_chunks)}")
        
        if not audio_chunks or len(audio_chunks) == 0:
            await cl.Message(content="😕 No audio chunks received. Try speaking louder or check microphone permissions.").send()
            return
        
        # 2. Combine chunks into single bytes object
        audio_buffer = b"".join(audio_chunks)
        print(f"📏 Total audio size: {len(audio_buffer)} bytes")
        
        if len(audio_buffer) < 1000:  # Less than 1KB is likely too short
            await cl.Message(content="😕 Audio too short. Please speak for at least 1 second.").send()
            return
        
        # 3. Save to temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.webm', delete=False) as f:
            f.write(audio_buffer)
            audio_path = f.name
            print(f"💾 Saved audio to: {audio_path}")
        
        # 4. Transcribe
        print("🔄 Starting transcription...")
        user_text = await speech_to_text(audio_path)
        print(f"📝 Transcription result: '{user_text}'")
        
        # Clean up temp file
        os.remove(audio_path)
        
        if not user_text or user_text.strip() == "":
            await cl.Message(content="😕 I couldn't transcribe the audio. Please try again and speak clearly.").send()
            return
        
        await cl.Message(content=f"🗣️ *You said:* {user_text}", author="User").send()
        
        # 5. Run agent logic
        chat = cl.user_session.get("chat")
        final_text = await run_agent_logic(user_text, chat)
        
        # 6. Respond with voice
        voice_mode = cl.user_session.get("voice_mode")
        response_elements = []
        
        if voice_mode:
            audio_generator = await text_to_speech(final_text)
            audio_bytes = b"".join(audio_generator)
            response_elements = [cl.Audio(content=audio_bytes, name="reply.mp3", auto_play=True)]
        
        await cl.Message(content=final_text, elements=response_elements).send()
        
    except Exception as e:
        print(f"❌ Error in on_audio_end: {str(e)}")
        import traceback
        traceback.print_exc()
        await cl.Message(content=f"❌ Error: {str(e)}").send()
