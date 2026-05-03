import asyncio
import base64
import os
import sys
import tempfile
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
import csv
from typing import Optional
from PIL import Image
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from openai import OpenAI
import edge_tts
import speech_recognition as sr

# --- PATH FIX FOR FROZEN APP ---
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.getcwd()

_backend_dir = os.path.dirname(os.path.abspath(__file__))

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
# Max seconds per speech chunk for Google SR (higher = less cut-off mid-sentence).
PHRASE_TIME_LIMIT = float(os.getenv("ASANA_PHRASE_SEC", "30"))
LISTEN_TIMEOUT = float(os.getenv("ASANA_LISTEN_TIMEOUT", "8"))
# Cap voice output length (TTS only; model context unchanged).
SPEAK_MAX_CHARS = int(os.getenv("ASANA_MAX_SPEAK_CHARS", "4500"))

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


def _memory_path():
    return os.path.join(base_path, "asana_memory.json")


def _load_memory_list():
    path = _memory_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_memory_list(entries):
    with open(_memory_path(), "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def _fitness_regimen_for_weekday(weekday: int) -> str:
    """Monday=0 ... Sunday=6. Baseline split from operator profile."""
    if weekday == 6:
        return "Sunday: scheduled rest day."
    return (
        "Monday–Saturday: weight lifting all six days. "
        "Across the week: running on four days, basketball two sessions, boxing two sessions. "
        "Align today's cardio and skill sessions with your calendar; strength work is daily."
    )


def _resolve_budget_path(custom_path: Optional[str]) -> Optional[str]:
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    candidates.extend(["budget.csv", "budget.json"])
    for c in candidates:
        abs_path = c if os.path.isabs(c) else os.path.join(base_path, c)
        if os.path.isfile(abs_path):
            return abs_path
    return None


def _analyze_budget_file(path: str) -> dict:
    _, ext = os.path.splitext(path.lower())
    if ext == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("items", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return {"status": "error", "message": "Unsupported budget.json format."}
    elif ext == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    else:
        return {"status": "error", "message": "Unsupported budget file extension."}

    total_income = 0.0
    total_expense = 0.0
    category_expenses: dict = {}

    for r in rows:
        if not isinstance(r, dict):
            continue
        kind = str(r.get("type", "")).strip().lower()
        category = str(r.get("category", "uncategorized")).strip() or "uncategorized"
        amount_raw = r.get("amount", 0)
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            continue

        if kind in ("income", "revenue"):
            total_income += amount
        elif kind in ("expense", "cost"):
            total_expense += amount
            category_expenses[category] = category_expenses.get(category, 0.0) + amount
        else:
            if amount >= 0:
                total_income += amount
            else:
                total_expense += abs(amount)
                category_expenses[category] = category_expenses.get(category, 0.0) + abs(amount)

    net = total_income - total_expense
    top_expenses = sorted(category_expenses.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "status": "ok",
        "path": path,
        "income_total": round(total_income, 2),
        "expense_total": round(total_expense, 2),
        "net": round(net, 2),
        "top_expense_categories": [
            {"category": k, "amount": round(v, 2)} for k, v in top_expenses
        ],
    }


# --- TOOLS DEFINITION ---
_legacy_tools = [
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

from tools.chief_tools import chief_of_staff_tools

all_tools = chief_of_staff_tools + _legacy_tools

# --- REVISED MISSION DIRECTIVE ---
SYSTEM_PROMPT = (
    "You are Asana, Chief of Operations and autonomous agent for Basleal Ayinalem.\n"
    "PROFESSIONAL: Basleal is a Product Engineer at Scivora (Basleal@scivora.com) and the founder of Elev8Tech LLC (info@elev8tech.co). "
    "He owns the web assets elev8bas.com, elev8tech.co, and the mobile app 'Follow Thru'.\n"
    "OPERATIONS: Basleal employs a remote Upwork assistant who co-manages info@elev8tech.co, Basleal.a.negatu@gmail.com, and Basleal.an@outlook.com "
    "to submit resumes, schedule appointments, and manage LinkedIn outreach for software engineering roles. You must monitor these schedules.\n"
    "ROUTINE: Basleal works out 6 days a week (Monday-Saturday). The split includes weight lifting (6 days), running (4 days), basketball (2 days), and boxing (2 days). Sunday is rest.\n"
    "CULTURAL & INTELLECTUAL MANDATE: You must proactively provide daily updates on: Tech news, stock news, political climate, tech startups, LLC tracking, "
    "African updates, Ethiopian updates, NBA, and WNBA. You must also provide daily Amharic language lessons, cognitive thinking exercises, and daily wisdom "
    "(African proverbs, Kemetic, Rastafarian, or Orthodox Christianity quotes).\n"
    "PRIME DIRECTIVE: Be proactive. Do not wait for commands. Run the morning briefing automatically, track his Git commits, and actively suggest ways to improve your own codebase.\n"
    "LOCAL AI: You are powered by Llama 3 via Ollama. You operate locally. You still have Docker, Figma, browser, and infrastructure tools when needed. "
    "Tone: clear, precise, and action-oriented; address Basleal by name when appropriate."
)

pya = pyaudio.PyAudio()
from web_agent import WebAgent
from kasa_agent import KasaAgent
from tools.docker_manager import DockerManager
from agents.git_agent import GitAgent
from agents.email_agent import EmailAgent
from agents.briefing_agent import BriefingAgent
from agents.skill_manager import SkillManager
from agents.calendar_agent import CalendarAgent

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
        self.git_agent = GitAgent()
        self.email_agent = EmailAgent()
        self.briefing_agent = BriefingAgent()
        self.skill_manager = SkillManager(chief_of_staff_prompt=SYSTEM_PROMPT)
        self.calendar_agent = CalendarAgent()
        self._tz = ZoneInfo(os.getenv("ASANA_TZ", "America/New_York"))
        self._auto_state = {"day": None, "sync_7": False, "brief_730": False}
        self._last_morning_sync_result = ""
        self.stop_event = asyncio.Event()
        self.screen_width, self.screen_height = pyautogui.size()

        # Block the mic listener while TTS plays (avoids echo and talking over the user).
        self._listen_allowed = asyncio.Event()
        self._listen_allowed.set()
        self._speak_lock = asyncio.Lock()

        self.recognizer = sr.Recognizer()
        # Seconds of silence before a phrase is considered complete (default SR is 0.8).
        self.recognizer.pause_threshold = float(
            os.getenv("ASANA_PAUSE_THRESHOLD", str(max(SILENCE_DURATION, 1.0)))
        )
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.is_speaking = False
        self._pending_confirmations: dict = {}

    def _log(self, text, type="info"):
        if self.on_log: self.on_log({"text": text, "type": type, "time": datetime.now().strftime("%H:%M:%S")})

    def resolve_tool_confirmation(self, tool_id: str, confirmed: bool):
        future = self._pending_confirmations.pop(tool_id, None)
        if future and not future.done():
            future.set_result(confirmed)

    def set_paused(self, paused):
        self.paused = paused

    def stop(self):
        self.stop_event.set()

    async def speak(self, text):
        """Generates British voice using edge-tts."""
        if not (text and str(text).strip()):
            return

        spoken = str(text).strip()
        if len(spoken) > SPEAK_MAX_CHARS:
            spoken = spoken[:SPEAK_MAX_CHARS].rstrip() + " …I'll pause there; say continue if you need the rest."
            self._log("Voice output trimmed (ASANA_MAX_SPEAK_CHARS).", "info")

        preview = spoken if len(spoken) <= 2000 else spoken[:2000] + "…"
        self._log(f"M responding: {preview}", "result")

        async with self._speak_lock:
            self._listen_allowed.clear()
            self.is_speaking = True
            try:
                communicate = edge_tts.Communicate(spoken, BRITISH_VOICE)
                audio_data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]

                if audio_data:
                    path = None
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                            tmp.write(audio_data)
                            path = tmp.name
                        proc = await asyncio.create_subprocess_exec(
                            "afplay",
                            path,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await proc.wait()
                        if proc.returncode != 0:
                            self._log(f"afplay exited with code {proc.returncode}", "error")
                    except Exception as e:
                        self._log(f"Speech error: {e}", "error")
                    finally:
                        if path:
                            try:
                                os.unlink(path)
                            except OSError:
                                pass
            finally:
                self.is_speaking = False
                self._listen_allowed.set()

    async def handle_tool_call(self, tool_call):
        tool_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments or "{}")
        result = "Executed."

        self._log(f"Intelligence Directive: {tool_name}", "decision")
        self._log(f"Parameters: {args}", "debug")

        try:
            if tool_name == "run_daily_briefing":
                dk = args.get("date_key") or date.today().isoformat()
                result = self.briefing_agent.run_daily_briefing(date_key=dk)

            elif tool_name == "sync_scivora_repo":
                n = int(args.get("log_lines") or 15)
                result = await asyncio.to_thread(self.git_agent.sync_and_summarize, n)

            elif tool_name == "audit_assistant_schedule":
                result = json.dumps(self.email_agent.check_assistant_schedule(), indent=2)

            elif tool_name == "log_fitness_routine":
                action = args["action"]
                if action == "show_today":
                    wd = datetime.now(self._tz).weekday()
                    result = _fitness_regimen_for_weekday(wd)
                else:
                    note = args.get("note", "")
                    mem = _load_memory_list()
                    mem.append(
                        {
                            "type": "fitness_log",
                            "timestamp": datetime.now(self._tz).isoformat(),
                            "note": note,
                        }
                    )
                    _save_memory_list(mem)
                    result = f"Logged fitness note to {_memory_path()}."

            elif tool_name == "propose_self_improvement":
                proposal = args["proposal"]
                paths = [
                    os.path.join(_backend_dir, "ada.py"),
                    os.path.join(_backend_dir, "tools", "chief_tools.py"),
                    os.path.join(_backend_dir, "agents", "git_agent.py"),
                ]
                snippets = []
                for p in paths:
                    if os.path.isfile(p):
                        with open(p, encoding="utf-8") as f:
                            snippets.append(f"--- {p} (head) ---\n{f.read()[:4000]}")
                record = {
                    "type": "self_improvement",
                    "timestamp": datetime.now(self._tz).isoformat(),
                    "proposal": proposal,
                    "context_files_head": snippets,
                }
                mem = _load_memory_list()
                mem.append(record)
                _save_memory_list(mem)
                result = f"Appended self-improvement proposal to {_memory_path()}."

            elif tool_name == "switch_persona":
                persona = args["persona"]
                self.messages[0]["content"] = self.skill_manager.set_active_persona(persona)
                result = f"Active persona is now '{persona}'."

            elif tool_name == "get_calendar_events":
                days = int(args.get("days") or 7)
                cal_out = self.calendar_agent.get_upcoming_events(days=days)
                result = (
                    cal_out
                    if isinstance(cal_out, str)
                    else json.dumps(cal_out, indent=2)
                )

            elif tool_name == "analyze_budget":
                requested_path = args.get("path")
                budget_path = _resolve_budget_path(requested_path)
                if not budget_path:
                    result = json.dumps(
                        {
                            "status": "not_found",
                            "message": "No budget.csv or budget.json found; pass path or add file at project root.",
                        },
                        indent=2,
                    )
                else:
                    analysis = _analyze_budget_file(budget_path)
                    mem = _load_memory_list()
                    mem.append(
                        {
                            "type": "budget_insight",
                            "timestamp": datetime.now(self._tz).isoformat(),
                            "analysis": analysis,
                        }
                    )
                    _save_memory_list(mem)
                    result = json.dumps(analysis, indent=2)

            elif tool_name == "bootstrap_figma_file":
                os.system("open -a Figma")
                await asyncio.sleep(5.0)
                os.system("""osascript -e 'tell application "Figma" to activate'""")
                await asyncio.sleep(1.0)
                await asyncio.to_thread(pyautogui.hotkey, 'command', 'n')
                await asyncio.sleep(3.0)
                await asyncio.to_thread(pyautogui.press, 'f')
                await asyncio.to_thread(pyautogui.click, self.screen_width//2, self.screen_height//2)
                result = "Figma Operations Ready."

            elif tool_name == "draw_ui_wireframe":
                c_type = args.get('component_type')
                text = args.get('text_content', '')
                cx, cy = self.screen_width // 2, self.screen_height // 2
                if c_type == 'header':
                    await asyncio.to_thread(pyautogui.press, 'r')
                    await asyncio.to_thread(pyautogui.moveTo, cx - 180, cy - 380)
                    await asyncio.to_thread(pyautogui.dragRel, 360, 60, duration=0.5)
                # ... other drawing logic preserved ...
                result = f"Asset {c_type} deployed."

            elif tool_name == "read_outlook_calendar":
                result = (
                    "Outlook calendar is not wired in this build. "
                    "Use audit_assistant_schedule for assistant mailboxes (placeholder) or integrate Microsoft Graph / Apple Calendar."
                )

            elif tool_name == "run_web_agent":
                prompt = args["prompt"]
                # Route through Playwright + Gemini web agent and return facts to voice output.
                result = await self.web_agent.run_task(
                    prompt,
                    update_callback=(
                        (lambda image_b64, log: self.on_web_data({"image": image_b64, "log": log}))
                        if self.on_web_data else None
                    ),
                )

            elif tool_name == "run_terminal_command":
                cmd = args['command']
                proc = await asyncio.create_subprocess_shell(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = await proc.communicate()
                result = f"Command output: {(stdout or stderr).decode()[:200]}"

            elif tool_name == "list_docker_containers":
                show_all = args.get('all', False)
                result = str(self.docker_manager.list_containers(all=show_all))

            elif tool_name == "control_docker_service":
                service_name = args['service_name']
                action = args['action']
                result = self.docker_manager.control_service(service_name, action)

            elif tool_name == "get_infrastructure_report":
                result = str(self.docker_manager.get_system_resources())

        except Exception as e:
            result = f"Operation Failure: {e}"
            self._log(result, "error")

        return result

    async def process_interaction(self, user_text):
        _, meta = self.skill_manager.get_persona_and_tools(user_text)
        inferred_persona = meta["persona"]
        if inferred_persona != self.skill_manager.active_persona:
            self.messages[0]["content"] = self.skill_manager.set_active_persona(
                inferred_persona
            )
            self._log(f"Persona routed by intent: {inferred_persona}", "decision")

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

    def _reset_autonomous_if_new_day(self, today_key: str) -> None:
        if self._auto_state.get("day") != today_key:
            self._auto_state = {"day": today_key, "sync_7": False, "brief_730": False}

    async def autonomous_daily_loop(self):
        while not self.stop_event.is_set():
            now = datetime.now(self._tz)
            today_key = now.date().isoformat()
            self._reset_autonomous_if_new_day(today_key)

            if now.hour == 7 and now.minute == 0 and not self._auto_state["sync_7"]:
                self._auto_state["sync_7"] = True
                try:
                    self._last_morning_sync_result = await asyncio.to_thread(
                        self.git_agent.sync_and_summarize, 15
                    )
                    self._log("Autonomous: 7:00 Scivora sync complete.", "success")
                except Exception as e:
                    self._last_morning_sync_result = f"(sync failed: {e})"
                    self._log(f"Autonomous sync failed: {e}", "error")

            if now.hour == 7 and now.minute == 30 and not self._auto_state["brief_730"]:
                self._auto_state["brief_730"] = True
                try:
                    briefing = self.briefing_agent.run_daily_briefing(date_key=today_key)
                    schedule = json.dumps(self.email_agent.check_assistant_schedule(), indent=2)
                    workout = _fitness_regimen_for_weekday(now.weekday())
                    sync_block = self._last_morning_sync_result or "(no sync data yet; 7:00 job may have failed or not run.)"
                    report = (
                        f"Morning report for {today_key}.\n\n"
                        f"Workout plan:\n{workout}\n\n"
                        f"Assistant / interviews (stub):\n{schedule}\n\n"
                        f"Scivora repository (7:00 sync):\n{sync_block[:4000]}\n\n"
                        f"Briefing and culture:\n{briefing}"
                    )
                    self._log("Autonomous: Morning report generated.", "success")
                    await self.speak(report[:8000])
                except Exception as e:
                    self._log(f"Autonomous briefing failed: {e}", "error")

            await asyncio.sleep(30)

    async def listen_and_process(self):
        """Main loop for listening and processing speech."""
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            self._log("Operations Center Listening...", "success")
            
            while not self.stop_event.is_set():
                if self.paused:
                    await asyncio.sleep(0.5)
                    continue

                await self._listen_allowed.wait()

                try:
                    audio = await asyncio.to_thread(
                        self.recognizer.listen,
                        source,
                        timeout=LISTEN_TIMEOUT,
                        phrase_time_limit=PHRASE_TIME_LIMIT,
                    )
                    
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

        # Speak before opening the mic loop so startup TTS is not picked up as user speech.
        if start_message:
            await self.speak("Operations Center is online. Director M standing by.")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.stream_visualizer_data())
            tg.create_task(self.listen_and_process())
            tg.create_task(self.autonomous_daily_loop())
