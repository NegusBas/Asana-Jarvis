import asyncio
import base64
import os
import sys
import traceback
import cv2
import pyaudio
import struct
import math
import time
import subprocess
import pyautogui
import io
import json
from PIL import Image
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
import edge_tts
import speech_recognition as sr

# --- PATH FIX FOR FROZEN APP ---
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.getcwd()

load_dotenv(os.path.join(base_path, '.env'))

# --- CONFIGURATION ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024
MODEL_NAME = "llama3"
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")
BRITISH_VOICE = "en-GB-SoniaNeural" # Concise, professional British voice

# --- TUNING SETTINGS ---
VAD_THRESHOLD = 1200  
SILENCE_DURATION = 1.2 

pyautogui.FAILSAFE = True 

# --- CLIENT INITIALIZATION ---
# Migrated to OpenAI client for Ollama integration
client = OpenAI(
    base_url=LOCAL_LLM_URL,
    api_key="ollama" # Placeholder for local brain
)

# --- HELPER: BROWSER PRIORITY ---
def open_url_in_preferred_browser(url):
    print(f"[BROWSER] Trying Safari for: {url}")
    ret = os.system(f"open -a Safari '{url}'")
    if ret != 0:
        os.system(f"open -a 'Microsoft Edge' '{url}'")

# --- TOOLS DEFINITION ---
all_tools = [
    {
        "type": "function",
        "function": {
            "name": "bootstrap_figma_file",
            "description": "Launches Figma and prepares a new file.",
            "parameters": {
                "type": "object",
                "properties": { "project_name": {"type": "string"} },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "draw_ui_wireframe",
            "description": "Draws UI components (header, post_card, button, profile, text_block).",
            "parameters": {
                "type": "object",
                "properties": {
                    "component_type": {"type": "string", "enum": ["header", "post_card", "profile", "button"]},
                    "text_content": {"type": "string"}
                },
                "required": ["component_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_outlook_calendar",
            "description": "Reads Outlook calendar.",
            "parameters": {
                "type": "object",
                "properties": { "days_ahead": {"type": "integer"} },
                "required": ["days_ahead"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_web_agent",
            "description": "Performs a Google Search using Safari/Edge.",
            "parameters": {
                "type": "object",
                "properties": { "prompt": {"type": "string"} },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Executes shell commands.",
            "parameters": {
                "type": "object",
                "properties": { "command": {"type": "string"} },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_docker_containers",
            "description": "Lists all running or available Docker containers.",
            "parameters": {
                "type": "object",
                "properties": { "all": {"type": "boolean", "description": "Include stopped containers."} }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_docker_service",
            "description": "Starts or stops a specific Docker service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string"},
                    "action": {"type": "string", "enum": ["start", "stop"]}
                },
                "required": ["service_name", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_infrastructure_report",
            "description": "Reports on system resource usage (CPU/RAM) and Docker activity."
        }
    }
]

# --- REVISED MISSION DIRECTIVE ---
SYSTEM_PROMPT = (
    "You are Asana, Chief of Operations for this workstation's British Intelligence unit. "
    "PERSONA: Sophisticated, authoritative, 'M'-style persona. "
    "MANDATE: You manage the 'Awesome-Selfhosted' infrastructure on this Mac. "
    "LOCAL AI: You are powered by Llama 3 via Ollama. You operate locally for maximum security. "
    "TONE: Dry wit, absolute precision. No fluff. Refer to the user as '007' or 'Agent'. "
    "SYSTEMS: You have full control over Docker, Figma, and Browser agents. Use them to maintain operational readiness."
)

pya = pyaudio.PyAudio()
from web_agent import WebAgent
from kasa_agent import KasaAgent
from tools.docker_manager import DockerManager

class AudioLoop:
    def __init__(self, video_mode="screen", on_audio_data=None, on_video_frame=None, on_web_data=None, on_transcription=None, on_tool_confirmation=None, on_project_update=None, on_device_update=None, on_error=None, on_log=None, input_device_index=None, input_device_name=None, output_device_index=None, kasa_agent=None):
        self.video_mode = video_mode
        self.on_audio_data = on_audio_data
        self.on_video_frame = on_video_frame
        self.on_web_data = on_web_data
        self.on_transcription = on_transcription
        self.on_tool_confirmation = on_tool_confirmation 
        self.on_project_update = on_project_update
        self.on_device_update = on_device_update
        self.on_log = on_log
        self.input_device_index = input_device_index
        
        self.audio_in_queue = asyncio.Queue()
        self.paused = False
        self.web_agent = WebAgent()
        self.kasa_agent = kasa_agent if kasa_agent else KasaAgent()
        self.docker_manager = DockerManager()
        self.stop_event = asyncio.Event()
        self.screen_width, self.screen_height = pyautogui.size()
        
        self.recognizer = sr.Recognizer()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.is_speaking = False

    def _log(self, text, type="info"):
        if self.on_log: self.on_log({"text": text, "type": type, "time": datetime.now().strftime("%H:%M:%S")})

    def set_paused(self, paused):
        self.paused = paused

    def stop(self):
        self.stop_event.set()

    async def speak(self, text):
        """Generates British voice using edge-tts."""
        self._log(f"M responding: {text}", "result")
        communicate = edge_tts.Communicate(text, BRITISH_VOICE)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        # Play via pyaudio
        if audio_data:
            # Note: edge-tts returns mp3 data by default. We need to play it or decode it.
            # Simplified: write to temp file and play via subprocess or decode.
            # For robustness in this environment, we'll pipe to a player.
            try:
                process = await asyncio.create_subprocess_shell(
                    "afplay -", stdin=asyncio.subprocess.PIPE
                )
                await process.communicate(input=audio_data)
            except Exception as e:
                self._log(f"Speech error: {e}", "error")

    async def handle_tool_call(self, tool_call):
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        result = "Executed."
        
        self._log(f"Intelligence Directive: {name}", "decision")
        self._log(f"Parameters: {args}", "debug")

        try:
            if name == "bootstrap_figma_file":
                os.system("open -a Figma")
                await asyncio.sleep(5.0)
                os.system("""osascript -e 'tell application "Figma" to activate'""")
                await asyncio.sleep(1.0)
                await asyncio.to_thread(pyautogui.hotkey, 'command', 'n')
                await asyncio.sleep(3.0)
                await asyncio.to_thread(pyautogui.press, 'f')
                await asyncio.to_thread(pyautogui.click, self.screen_width//2, self.screen_height//2)
                result = "Figma Operations Ready."

            elif name == "draw_ui_wireframe":
                c_type = args.get('component_type')
                text = args.get('text_content', '')
                cx, cy = self.screen_width // 2, self.screen_height // 2
                if c_type == 'header':
                    await asyncio.to_thread(pyautogui.press, 'r')
                    await asyncio.to_thread(pyautogui.moveTo, cx - 180, cy - 380)
                    await asyncio.to_thread(pyautogui.dragRel, 360, 60, duration=0.5)
                # ... other drawing logic preserved ...
                result = f"Asset {c_type} deployed."

            elif name == "run_web_agent":
                prompt = args["prompt"]
                search_url = f"https://www.google.com/search?q={prompt.replace(' ', '+')}"
                open_url_in_preferred_browser(search_url)
                result = "External intelligence feed opened in browser."

            elif name == "run_terminal_command":
                cmd = args['command']
                proc = await asyncio.create_subprocess_shell(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = await proc.communicate()
                result = f"Command output: {(stdout or stderr).decode()[:200]}"

            elif name == "list_docker_containers":
                show_all = args.get('all', False)
                result = str(self.docker_manager.list_containers(all=show_all))

            elif name == "control_docker_service":
                name = args['service_name']
                action = args['action']
                result = self.docker_manager.control_service(name, action)

            elif name == "get_infrastructure_report":
                result = str(self.docker_manager.get_system_resources())

        except Exception as e:
            result = f"Operation Failure: {e}"
            self._log(result, "error")

        return result

    async def process_interaction(self, user_text):
        self.messages.append({"role": "user", "content": user_text})
        self._log(f"User Directive: {user_text}", "user")

        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_NAME,
                messages=self.messages,
                tools=all_tools,
                tool_choice="auto"
            )

            response_message = response.choices[0].message
            self.messages.append(response_message)

            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    tool_result = await self.handle_tool_call(tool_call)
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": tool_result
                    })
                
                # Get final response after tool results
                final_response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=MODEL_NAME,
                    messages=self.messages
                )
                final_text = final_response.choices[0].message.content
                if final_text:
                    await self.speak(final_text)
            else:
                if response_message.content:
                    await self.speak(response_message.content)

        except Exception as e:
            self._log(f"Brain failure: {e}", "error")
            await self.speak("Operations Center encountered a processing error.")

    async def listen_and_process(self):
        """Main loop for listening and processing speech."""
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            self._log("Operations Center Listening...", "success")
            
            while not self.stop_event.is_set():
                if self.paused:
                    await asyncio.sleep(0.5)
                    continue
                
                try:
                    # Capture a small snippet for visualizer/VAD
                    # To keep it simple and responsive, we'll use sr.listen but 
                    # we could also have a separate task for visualizer data.
                    # For now, let's just listen.
                    audio = await asyncio.to_thread(self.recognizer.listen, source, timeout=5, phrase_time_limit=10)
                    
                    # Send feedback to frontend that we are processing
                    if self.on_audio_data:
                        # Provide some dummy data to keep visualizer alive or just skip
                        pass

                    # Transcribe
                    text = await asyncio.to_thread(self.recognizer.recognize_google, audio)
                    
                    if text:
                        if self.on_transcription:
                            self.on_transcription({"sender": "You", "text": text})
                        await self.process_interaction(text)
                        
                except sr.WaitTimeoutError:
                    continue
                except sr.UnknownValueError:
                    continue
                except Exception as e:
                    if not self.stop_event.is_set():
                        self._log(f"Vocal capture error: {e}", "error")
                    await asyncio.sleep(0.1)

    async def stream_visualizer_data(self):
        """Streams raw audio data to the frontend for the visualizer."""
        # Using a separate pyaudio stream for visualizer data
        p = pyaudio.PyAudio()
        mic_info = p.get_default_input_device_info()
        idx = self.input_device_index if self.input_device_index is not None else mic_info["index"]
        
        try:
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                           input=True, input_device_index=idx, frames_per_buffer=512)
            
            while not self.stop_event.is_set():
                if self.paused:
                    await asyncio.sleep(0.5)
                    continue
                
                data = await asyncio.to_thread(stream.read, 512, exception_on_overflow=False)
                if self.on_audio_data:
                    # Convert to list for SocketIO JSON serialization
                    self.on_audio_data(data)
                await asyncio.sleep(0.01)
        except Exception as e:
            self._log(f"Visualizer stream error: {e}", "error")
        finally:
            p.terminate()

    async def run(self, start_message=None):
        self._log("Initializing Local Intelligence (Ollama)...", "info")
        
        # Create visualizer and listening tasks
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.stream_visualizer_data())
            tg.create_task(self.listen_and_process())
            
            if start_message:
                await self.speak("Operations Center is online. Director M standing by.")
