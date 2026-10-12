"""Socket.IO connection auth and STT stream lifecycle."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import socketio

from app.auth.jwt import create_access_token
from app.ws import ws_manager


@pytest.fixture
def known_user(monkeypatch):
    user_id = uuid.uuid4()

    async def fake_user_exists(uid):
        return uid == user_id

    monkeypatch.setattr(ws_manager, "user_exists", fake_user_exists)
    return user_id


def test_extract_token_prefers_auth_payload():
    environ = {"HTTP_AUTHORIZATION": "Bearer header-token"}
    assert ws_manager.extract_token(environ, {"token": "auth-token"}) == "auth-token"
    assert ws_manager.extract_token(environ, None) == "header-token"
    assert ws_manager.extract_token({}, {"token": "  "}) is None
    assert ws_manager.extract_token({"HTTP_AUTHORIZATION": "Basic abc"}, None) is None


async def test_authenticate_valid_token(known_user):
    token = create_access_token({"sub": str(known_user)})
    assert await ws_manager.authenticate({}, {"token": token}) == known_user


@pytest.mark.parametrize(
    "auth",
    [None, {}, {"token": "not-a-jwt"}, {"token": create_access_token({"sub": "not-a-uuid"})}],
)
async def test_authenticate_rejects_bad_tokens(known_user, auth):
    assert await ws_manager.authenticate({}, auth) is None


async def test_authenticate_rejects_unknown_user(known_user):
    token = create_access_token({"sub": str(uuid.uuid4())})
    assert await ws_manager.authenticate({}, {"token": token}) is None


async def test_connect_refuses_without_token(known_user):
    with pytest.raises(socketio.exceptions.ConnectionRefusedError):
        await ws_manager.connect("sid-1", {}, None)


async def test_connect_saves_user_on_session(known_user, monkeypatch):
    save = AsyncMock()
    monkeypatch.setattr(ws_manager.sio_server, "save_session", save)
    token = create_access_token({"sub": str(known_user)})
    await ws_manager.connect("sid-2", {}, {"token": token})
    save.assert_awaited_once_with("sid-2", {"user_id": known_user})


# --- STT service ---------------------------------------------------------


def _fake_stream():
    stream = MagicMock()
    stream.input_stream.end_stream = AsyncMock()
    stream.output_stream = MagicMock()
    return stream


@pytest.fixture
def stt(monkeypatch):
    from app.api.stt import service as stt_service

    streams = []

    class FakeClient:
        def __init__(self, region):
            pass

        async def start_stream_transcription(self, **kwargs):
            s = _fake_stream()
            streams.append(s)
            return s

    monkeypatch.setattr(stt_service, "TranscribeStreamingClient", FakeClient)
    monkeypatch.setattr(stt_service.SpeechToTextService, "run_handler", AsyncMock())
    monkeypatch.setattr(stt_service.SpeechToTextService.TranscribeHandler, "__init__", lambda self, o, sid: None)
    svc = stt_service.SpeechToTextService()
    return svc, streams, stt_service


async def test_second_start_ends_previous_stream(stt):
    svc, streams, _ = stt
    await svc.start_audio("sid")
    await svc.start_audio("sid")
    assert len(streams) == 2
    streams[0].input_stream.end_stream.assert_awaited_once()
    assert svc.active_streams["sid"]["stream"] is streams[1]
    await svc.end_audio("sid")


async def test_disconnect_ends_stream_and_cancels_timeout(stt):
    svc, streams, _ = stt
    await svc.start_audio("sid")
    timeout_task = svc.active_streams["sid"]["timeout_task"]
    await svc.handle_disconnect("sid")
    await asyncio.sleep(0)
    assert "sid" not in svc.active_streams
    assert timeout_task.cancelled()
    streams[0].input_stream.end_stream.assert_awaited_once()


async def test_stream_ends_after_max_duration(stt, monkeypatch):
    svc, streams, stt_service = stt
    monkeypatch.setattr(stt_service.settings, "STT_MAX_STREAM_SECONDS", 0)
    emit = AsyncMock()
    monkeypatch.setattr(stt_service.sio_server, "emit", emit)
    await svc.start_audio("sid")
    await svc.active_streams["sid"]["timeout_task"]
    assert "sid" not in svc.active_streams
    streams[0].input_stream.end_stream.assert_awaited_once()
    emit.assert_awaited_once()
    assert emit.await_args.args[0] == "STT_TIMEOUT"
