import os
import sys

# --- THE HOMING PIGEON FIX ---
# This forces the brain to look in its own folder for .env, not where the terminal is.
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
# -----------------------------

import socketio
import uvicorn
from fastapi import FastAPI
import asyncio
import json

# Fix for Windows (keep just in case, harmless on Mac)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import ada
from kasa_agent import KasaAgent

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
app_socketio = socketio.ASGIApp(sio, app)

audio_loop = None
kasa_agent = KasaAgent()

SETTINGS = {
    "face_auth_enabled": False,
    "tool_permissions": {
        "run_web_agent": True,
        "write_file": True,
        "read_directory": True,
        "read_file": True,
        "control_light": True,
        "create_project": True,
        "switch_project": True
    },
    "kasa_devices": [],
    "camera_flipped": False
}

@app.get("/status")
async def status_check():
    return {"status": "running", "service": "ASANA Backend"}

@app.on_event("startup")
async def startup_event():
    print("[ASANA] Initializing Kasa Agent...")
    await kasa_agent.initialize()

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit('status', {'msg': 'Connected to ASANA Backend'})
    await sio.emit('settings', SETTINGS)
    # Force Auth Success for no-camera mode
    await sio.emit('auth_status', {'authenticated': True, 'user': 'Admin'})

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.event
async def start_audio(sid, data=None):
    global audio_loop
    print("Starting ASANA Audio Loop...")
    
    def on_transcription(data):
        asyncio.create_task(sio.emit('transcription', data))

    def on_web_data(data):
        asyncio.create_task(sio.emit('browser_frame', data))
        
    def on_project_update(name):
        asyncio.create_task(sio.emit('project_update', {'project': name}))
        
    def on_tool_confirmation(data):
        asyncio.create_task(sio.emit('tool_confirmation_request', data))

    def on_device_update(devices):
        asyncio.create_task(sio.emit('kasa_devices', devices))

    # --- NEW LOGGING HANDLER ---
    def on_log(log_data):
        # Emit log entry to frontend
        asyncio.create_task(sio.emit('log_entry', log_data))

    if audio_loop:
        audio_loop.stop()

    # Initialize ASANA 
    # ENABLE SCREEN MODE for vision capabilities
    audio_loop = ada.AudioLoop(
        video_mode="screen", 
        on_audio_data=lambda d: asyncio.create_task(sio.emit('audio_data', {'data': list(d)})),
        on_web_data=on_web_data,
        on_transcription=on_transcription,
        on_tool_confirmation=on_tool_confirmation,
        on_project_update=on_project_update,
        on_device_update=on_device_update,
        on_log=on_log, # <--- Pass the logger here
        input_device_index=1, 
        kasa_agent=kasa_agent
    )
    
    if data and data.get('muted'):
        audio_loop.set_paused(True)

    asyncio.create_task(audio_loop.run(start_message="Asana is online."))
    await sio.emit('status', {'msg': 'ASANA Started'})

@sio.event
async def stop_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.stop()
        audio_loop = None
    await sio.emit('status', {'msg': 'ASANA Stopped'})

@sio.event
async def pause_audio(sid):
    if audio_loop:
        print("Pausing Audio (Mute)...")
        audio_loop.set_paused(True)

@sio.event
async def resume_audio(sid):
    if audio_loop:
        print("Resuming Audio (Unmute)...")
        audio_loop.set_paused(False)

@sio.event
async def user_input(sid, data):
    if audio_loop and audio_loop.session:
        print(f"User Input: {data['text']}")
        await audio_loop.session.send(input=data['text'], end_of_turn=True)

@sio.event
async def confirm_tool(sid, data):
    if audio_loop:
        print(f"Tool Confirmation: {data}")
        audio_loop.resolve_tool_confirmation(data['id'], data['confirmed'])

@sio.event
async def discover_kasa(sid):
    print("Discovering Kasa devices...")
    try:
        devices = await kasa_agent.discover_devices()
        dev_list = []
        if isinstance(devices, dict):
            for ip, d in devices.items():
                dev_list.append({"ip": ip, "alias": d.alias, "is_on": d.is_on, "type": "bulb" if d.is_bulb else "plug"})
        elif isinstance(devices, list):
            for d in devices:
                ip = getattr(d, 'host', '0.0.0.0')
                dev_list.append({"ip": ip, "alias": d.alias, "is_on": d.is_on, "type": "bulb" if d.is_bulb else "plug"})
        await sio.emit('kasa_devices', dev_list)
    except Exception as e:
        print(f"Error discovering Kasa devices: {e}")

@sio.event
async def get_settings(sid):
    await sio.emit('settings', SETTINGS)

@sio.event
async def update_settings(sid, data):
    global SETTINGS
    print(f"Update settings: {data}")
    if 'face_auth_enabled' in data:
        SETTINGS['face_auth_enabled'] = data['face_auth_enabled']
    if 'camera_flipped' in data:
        SETTINGS['camera_flipped'] = data['camera_flipped']
    if 'tool_permissions' in data:
        SETTINGS['tool_permissions'].update(data['tool_permissions'])
    await sio.emit('settings', SETTINGS)

if __name__ == "__main__":
    uvicorn.run("server:app_socketio", host="127.0.0.1", port=8000, reload=True)
