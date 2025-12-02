# 🎙️ Smart Scheduler - Assistant for Calendar Management

An intelligent voice-enabled scheduling assistant built with Chainlit, Google Gemini, and Google Calendar API. The assistant manages your calendar through natural voice commands or text input, with timezone-aware scheduling for Asia/Kolkata (IST).

![Smart Scheduler](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Chainlit](https://img.shields.io/badge/Chainlit-2.3.0+-orange)

---

## 📋 Table of Contents
- [Features](#-features)
- [How It Works](#-how-it-works)
- [Design Choices](#-design-choices)
- [Prerequisites](#-prerequisites)
- [Setup Instructions](#-setup-instructions)
- [Running the Application](#-running-the-application)
- [Usage Examples](#-usage-examples)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Features

- 🎤 **Voice Input & Output**: Speak naturally to schedule meetings and receive voice responses
- 📅 **Smart Calendar Management**: Check availability, find free slots, and create events
- 🤖 **AI-Powered Conversations**: Google Gemini 2.5 Flash with function calling for intelligent interactions
- ⏰ **Timezone-Aware Scheduling**: Configured for IST, scope of changing accordingly
- 🔄 **Real-time Transcription**: Google Cloud Speech-to-Text for accurate voice recognition
- 🗣️ **Natural Voice Synthesis**: ElevenLabs TTS for human-like responses

---

## 🧠 How It Works

### Agent Architecture

The Smart Scheduler operates as a conversational AI agent with the following workflow:

```
User Voice/Text Input
       ↓
Audio Processing (if voice)
       ↓
Speech-to-Text (Google Cloud STT)
       ↓
Google Gemini 2.5 Flash (LLM)
       ↓
Function Calling Decision
       ↓
Calendar Tool Execution
       ↓
Response Generation
       ↓
Text-to-Speech (ElevenLabs)
       ↓
Voice/Text Output to User
```

### Core Components

1. **Chainlit Frontend**: Manages UI, audio capture, and message rendering
2. **Audio Pipeline**: 
   - Captures raw PCM audio chunks from browser
   - Converts to WAV format for Google STT
   - Synthesizes speech responses using ElevenLabs
3. **Gemini Agent**: 
   - Processes natural language queries
   - Makes intelligent function calling decisions
   - Maintains conversation context across multiple turns
4. **Calendar Tools**: Five Python functions exposed to the LLM:
   - `get_current_time()`: Provides timezone-aware current time
   - `list_upcoming_events()`: Retrieves upcoming calendar events
   - `check_availability()`: Checks if a time slot is free
   - `find_free_slots()`: Searches for available meeting times
   - `create_calendar_event()`: Books meetings on Google Calendar

### Conversation Flow

The agent follows a structured decision tree:

1. **Query Understanding**: User asks about their schedule or requests a meeting
2. **Context Gathering**: Agent calls appropriate tools (e.g., `get_current_time()` for relative date parsing)
3. **Availability Check**: Verifies time slots using `check_availability()` or `find_free_slots()`
4. **Information Collection**: Asks for missing details (meeting title, preferred time)
5. **Execution**: Creates the event using `create_calendar_event()`
6. **Confirmation**: Provides a natural language summary

**Example Multi-Turn Conversation**:
```
User: "Book a meeting tomorrow morning"
Agent: [Calls get_current_time()] "Would you prefer 9 AM, 10 AM, or 11 AM?"
User: "10 AM works"
Agent: [Calls check_availability()] "That slot is free. What's the meeting title?"
User: "Team standup"
Agent: [Calls create_calendar_event()] "Done! I've scheduled 'Team standup' for tomorrow at 10 AM."
```

---

## 🎯 Design Choices

### 1. **Gemini Function Calling over LangChain/Custom Prompting**
**Why**: Gemini's native function calling provides:
- Automatic parameter extraction from natural language
- Built-in retry logic for malformed calls
- No need for complex prompt engineering to structure tool usage

**Trade-off**: Locked into Google's ecosystem, but the simplicity and reliability justify this.

### 2. **Service Account Authentication**
**Why**: 
- No OAuth consent flow required
- Automated, non-interactive authentication
- Suitable for personal/single-user deployments

**Limitation**: Cannot send calendar invites to external attendees without Domain-Wide Delegation (Google Workspace feature). For personal use, this is acceptable.

### 3. **RAW PCM to WAV Conversion**
**Why**: Chainlit sends raw audio chunks, not a complete WEBM file. We:
- Collect chunks in session state
- Wrap in WAV container using Python's `wave` module
- Send to Google STT as LINEAR16 encoding

**Alternative Considered**: Direct WEBM processing failed due to missing container headers.

### 4. **48kHz Sample Rate**
**Why**: 
- Standard for modern web browsers (WebRTC default)
- Matches Google STT's optimal sample rate
- Provides better transcription accuracy than 16kHz

### 5. **Decision Tree System Prompt**
**Why**: 
- Explicit case-by-case instructions reduce ambiguity
- LLM knows exactly when to ask questions vs. call tools
- Prevents unnecessary API calls (e.g., checking availability before knowing the desired time)

**Alternative Considered**: Free-form instructions resulted in inconsistent tool usage.

### 6. **ElevenLabs for TTS**
**Why**:
- Superior voice quality compared to Google TTS
- `eleven_turbo_v2_5` model provides low latency (<500ms)
- Natural-sounding conversational voice (Rachel)

**Cost**: ~$0.30 per 1000 characters (acceptable for personal use).

---

## 📋 Prerequisites

- **Python**: 3.11 or higher
- **Google Cloud Platform**: Account with billing enabled
- **ElevenLabs**: API key (free tier available)
- **ffmpeg**: For audio processing
- **Browser**: Chrome or Edge (recommended for audio compatibility)

---

## 🚀 Setup Instructions

### Step 1: Clone the Repository

```
git clone https://github.com/ojasva-singh/smart-scheduler.git
cd smart-scheduler
```

### Step 2: Install ffmpeg

**macOS**:
```
brew install ffmpeg
```

**Ubuntu/Debian**:
```
sudo apt update
sudo apt install ffmpeg
```

**Windows**:
Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.

### Step 3: Create Virtual Environment

```
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Step 4: Install Python Dependencies

```
pip3 install -r requirements.txt
```

### Step 5: Setup Google Cloud Project

#### A. Create Project and Enable APIs

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Navigate to **APIs & Services** → **Library**
4. Enable these APIs:
   - **Google Calendar API**
   - **Cloud Speech-to-Text API**

#### B. Create Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Name it (e.g., "smart-scheduler-bot")
4. Grant role: **Project** → **Editor**
5. Click **Done**

#### C. Generate Service Account Key

1. Click on the created service account
2. Go to **Keys** tab
3. Click **Add Key** → **Create New Key**
4. Choose **JSON** format
5. Download and save as `credentials.json` in the project root

#### D. Share Your Calendar with Service Account

1. Open [Google Calendar](https://calendar.google.com/)
2. Click the three dots next to your calendar → **Settings and sharing**
3. Scroll to **Share with specific people**
4. Click **Add people**
5. Paste the service account email from `credentials.json` (format: `your-service@project-id.iam.gserviceaccount.com`)
6. Set permission to **Make changes to events**
7. Click **Send**

### Step 6: Get API Keys

#### ElevenLabs API Key

1. Sign up at [ElevenLabs](https://elevenlabs.io/)
2. Go to **Profile Settings** → **API Keys**
3. Click **Generate**
4. Copy the key

#### Google Gemini API Key

1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click **Get API Key**
3. Create or select a Google Cloud project
4. Copy the generated API key

### Step 7: Configure Environment Variables

Create a `.env` file in the project root:

```
GOOGLE_API_KEY=your_gemini_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
CALENDAR_ID=your_email_id
```

**Important**: Replace the placeholder values with your actual API keys.

### Step 8: Verify Setup

Ensure your project structure looks like this:

```
smart-scheduler/
├── app.py
├── tools/
│   ├── __init__.py
│   └── calendar.py
├── .chainlit/
│   └── config.toml
├── credentials.json          # Your service account key
├── .env                       # Your API keys
├── requirements.txt
└── README.md
```

---

## 🎯 Running the Application

### Start the Server

```
chainlit run app.py
```

You should see:

```
Your app is available at http://localhost:8000
```

### Access the Application

1. Open your browser to `http://localhost:8000`
2. **Grant microphone permissions** when prompted (for voice input)
3. Start chatting via text or click the 🎤 microphone icon to speak

### Voice Mode Settings

- Toggle voice responses on/off using the **Voice Mode** switch in the settings (gear icon)
- When enabled, the assistant will speak responses automatically

---

## 💬 Usage Examples

### Voice Commands

- **Check Schedule**: "What meetings do I have today?"
- **Find Availability**: "Am I free tomorrow at 3 PM?"
- **Book Meeting (Vague)**: "Schedule something tomorrow morning"
  - Agent will ask: "Would you prefer 9 AM, 10 AM, or 11 AM?"
- **Book Meeting (Specific)**: "Book a meeting tomorrow at 11 AM"
  - Agent will ask: "What should I call this meeting?"
- **Find Free Slots**: "When am I free tomorrow afternoon?"

### Text Commands

All voice commands work via text input as well.

### Sample Conversation

```
You: "What do I have tomorrow?"
Agent: [Calls list_upcoming_events()]
      "You have two meetings: 'Team Sync' at 10 AM and 'Client Call' at 4 PM."

You: "Book a slot tomorrow at 2 PM for a design review"
Agent: [Calls check_availability()]
      "That time is outside working hours. I can only book between 9 AM-12 PM or 4 PM-7 PM."

You: "How about 5 PM?"
Agent: [Calls check_availability(), then create_calendar_event()]
      "Done! 'Design Review' is scheduled for tomorrow at 5 PM."
```

---

## 🔧 Troubleshooting

### Audio Not Recording

**Symptoms**: Microphone button doesn't capture voice

**Solutions**:
- ✅ Grant microphone permissions in browser
- ✅ Use Chrome or Edge (Firefox has known compatibility issues)
- ✅ Check `config.toml` has `enabled = true` under `[features.audio]`

### Empty Transcription

**Symptoms**: "😕 I couldn't transcribe the audio"

**Solutions**:
- Speak louder or closer to the microphone
- Ensure recording is at least 1 second long
- Reduce background noise
- Verify Google Cloud Speech-to-Text API is enabled

### Google Calendar Errors

**Symptoms**: "Error: 403 Forbidden" or "Calendar not found"

**Solutions**:
- ✅ Verify `credentials.json` is in the project root
- ✅ Ensure Google Calendar API is enabled in Cloud Console
- ✅ Confirm calendar is shared with service account email
- ✅ Check service account has "Make changes to events" permission

### "No upcoming events found" (but you have events)

**Solutions**:
- Calendar might not be shared with service account
- Try using `CALENDAR_ID=your-email@gmail.com` in `.env` instead of "primary"

### ElevenLabs Voice Errors

**Symptoms**: "Error generating voice response"

**Solutions**:
- Check ElevenLabs API key is valid
- Verify you haven't exceeded free tier limits
- Ensure stable internet connection

### Tool Not Found Errors

**Symptoms**: "Error: Tool not found"

**Solutions**:
- Restart the Chainlit server (`Ctrl+C` then `chainlit run app.py`)
- Verify all functions in `tools/calendar.py` are imported in `app.py`

---

## 📊 Tech Stack

- **UI Framework**: Chainlit 2.3.0+
- **LLM**: Google Gemini 2.5 Flash (function calling)
- **Speech-to-Text**: Google Cloud Speech-to-Text API
- **Text-to-Speech**: ElevenLabs API
- **Calendar**: Google Calendar API v3
- **Audio Processing**: Python `wave` module, ffmpeg
- **Authentication**: Google Service Account

---

## 🔒 Security Notes

- **Never commit** `credentials.json` or `.env` to version control (already in `.gitignore`)
- Service account keys provide full access to the calendar—treat them like passwords
- Rotate API keys periodically
- For production use, implement OAuth 2.0 instead of service accounts

---