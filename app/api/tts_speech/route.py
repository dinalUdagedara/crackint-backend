"""Text-to-speech for voice mock interviews: POST /tts returns mp3 audio."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.rate_limit import llm_rate_limit
from app.config import settings
from app.services.llm import LLMUnavailableError, synthesize_speech

router = APIRouter()


class SpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to speak (truncated to TTS_MAX_CHARS).")


@router.post(
    "",
    dependencies=[Depends(llm_rate_limit)],
    name="Text to speech",
    summary="Speak text (mp3). 503 when TTS is disabled or unavailable; clients fall back to browser speech.",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
)
async def text_to_speech(body: SpeechRequest):
    if not settings.TTS_ENABLED:
        raise HTTPException(status_code=503, detail="Text-to-speech is disabled.")
    text = body.text.strip()[: settings.TTS_MAX_CHARS]
    try:
        audio = await synthesize_speech(text=text, model=settings.TTS_MODEL, voice=settings.TTS_VOICE)
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail="Text-to-speech failed.") from e
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
