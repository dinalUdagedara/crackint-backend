import asyncio
import logging

import boto3
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from botocore.config import Config

from app.config import settings
from app.ws.ws_manager import sio_server

logger = logging.getLogger("app.stt")

class SpeechToTextService:
    def __init__(self):
        # AWS configuration
        self.aws_config = Config(
            region_name=settings.AWS_DEFAULT_REGION,
            signature_version="v4",
            retries={"max_attempts": 10, "mode": "standard"},
        )

        self.active_streams = {}

    # Inner Handler Class
    class TranscribeHandler(TranscriptResultStreamHandler):
        def __init__(self, output_stream, sid):
            super().__init__(output_stream)
            self.sid = sid

        async def handle_transcript_event(self, transcript_event: TranscriptEvent):
            try:
                if hasattr(transcript_event.transcript, "results"):
                    results = transcript_event.transcript.results
                    for result in results:
                        if hasattr(result, "alternatives"):
                            for alt in result.alternatives:
                                transcript = alt.transcript
                                is_partial = result.is_partial
                                logger.debug(
                                    f"Session {self.sid} - Transcription: {transcript}, Is partial: {is_partial}"
                                )

                                # Emit the transcription result back to the client
                                await sio_server.emit(
                                    "TRANSCRIBE",
                                    {
                                        "transcript": transcript,
                                        "is_partial": is_partial,
                                    },
                                    to=self.sid,
                                )
                        else:
                            logger.debug(
                                f"Session {self.sid} - No alternatives in result"
                            )
                else:
                    logger.debug(f"Session {self.sid} - No results in transcript event")
            except Exception as e:
                logger.error(
                    f"Error processing transcript event for session {self.sid}: {e}"
                )

    async def start_audio(self, sid):
        try:
            # Create a new TranscribeStreamingClient for this session
            transcribe_client = TranscribeStreamingClient(
                region=settings.AWS_DEFAULT_REGION,
            )

            stream = await transcribe_client.start_stream_transcription(
                language_code="en-US",
                media_sample_rate_hz=16000,
                media_encoding="pcm",
            )
            handler = self.TranscribeHandler(stream.output_stream, sid)
            self.active_streams[sid] = {
                "stream": stream,
                "handler": handler,
                "transcribe_client": transcribe_client,  # Keep the client alive
            }

            # Run the handler in the background
            asyncio.create_task(self.run_handler(handler, sid))
        except Exception as e:
            logger.error(f"Error starting stream transcription for session {sid}: {e}")

    async def run_handler(self, handler, sid):
        try:
            await handler.handle_events()
        except Exception as e:
            logger.error(f"Error in handler for session {sid}: {e}")

    async def handle_audio_data(self, sid, data):
        if sid in self.active_streams:
            try:
                await self.active_streams[sid]["stream"].input_stream.send_audio_event(
                    audio_chunk=data
                )
            except Exception as e:
                logger.error(f"Error sending audio event for session {sid}: {e}")
        else:
            logger.debug(f"No active stream for session {sid}")

    async def end_audio(self, sid):
        if sid in self.active_streams:
            try:
                await self.active_streams[sid]["stream"].input_stream.end_stream()
                del self.active_streams[sid]
            except Exception as e:
                logger.error(f"Error ending stream for session {sid}: {e}")
        else:
            logger.debug(f"No active stream to end for session {sid}")

    async def handle_disconnect(self, sid):
        if sid in self.active_streams:
            try:
                await self.active_streams[sid]["stream"].input_stream.end_stream()
                del self.active_streams[sid]
            except Exception as e:
                logger.error(f"Error ending stream for disconnected session {sid}: {e}")
