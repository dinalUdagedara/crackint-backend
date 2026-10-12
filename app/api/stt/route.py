from fastapi import APIRouter

from app.api.stt.service import SpeechToTextService
from app.ws.ws_manager import get_socket_user_id, sio_server

router = APIRouter()

speech_to_text_service = SpeechToTextService()


async def _is_authenticated(sid) -> bool:
    # connect() refuses unauthenticated sockets; this guards against handlers firing for a stale sid.
    return await get_socket_user_id(sid) is not None


@sio_server.on("START_AUDIO")
async def handle_start_audio(sid, data):
    if not await _is_authenticated(sid):
        return
    await speech_to_text_service.start_audio(sid)

@sio_server.on("AUDIO_DATA")
async def handle_audio_data(sid, data):
    if not await _is_authenticated(sid):
        return
    await speech_to_text_service.handle_audio_data(sid, data)

@sio_server.on("END_AUDIO")
async def handle_end_audio(sid, data):
    await speech_to_text_service.end_audio(sid)

@sio_server.on("disconnect")
async def handle_disconnect(sid):
    await speech_to_text_service.handle_disconnect(sid)
