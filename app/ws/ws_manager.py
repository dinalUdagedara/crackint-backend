import logging

import socketio


logger = logging.getLogger(__name__)

sio_server = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


def create_sio_app(other_app=None):
    return socketio.ASGIApp(
        socketio_server=sio_server,
        other_asgi_app=other_app,
        socketio_path="/ws/socket.io",
    )


@sio_server.event
async def connect(sid, environ):
    logger.info("Socket connected %s", sid)


@sio_server.event
async def disconnect(sid):
    logger.info("Socket disconnected %s", sid)

