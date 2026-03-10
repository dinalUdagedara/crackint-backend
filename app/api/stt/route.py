from fastapi import APIRouter

from app.api.stt.service import SpeechToTextService
from app.ws.ws_manager import sio_server

router = APIRouter()

speech_to_text_service = SpeechToTextService()

@sio_server.on("START_AUDIO")
async def handle_start_audio(sid, data):
    await speech_to_text_service.start_audio(sid)

@sio_server.on("AUDIO_DATA")
async def handle_audio_data(sid, data):
    await speech_to_text_service.handle_audio_data(sid, data)

@sio_server.on("END_AUDIO")
async def handle_end_audio(sid, data):
    await speech_to_text_service.end_audio(sid)

@sio_server.on("disconnect")
async def handle_disconnect(sid):
    await speech_to_text_service.handle_disconnect(sid)
