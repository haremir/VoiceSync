import uuid
import aiofiles
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config  # loads .env and validates API_KEY on import
from tts_engine import TTSEngine, VOICES_DIR, OUTPUTS_DIR

# ---------------------------------------------------------------------------
# Singleton engine instance
# ---------------------------------------------------------------------------
engine = TTSEngine()

# ---------------------------------------------------------------------------
# In-memory task store
# ---------------------------------------------------------------------------
task_status: dict[str, str] = {}   # task_id -> "processing" | "done" | "error: ..."
task_result: dict[str, str] = {}   # task_id -> "/audio/filename.mp3"

# ---------------------------------------------------------------------------
# Lifespan: load model once at startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the TTS engine into memory when the application starts."""
    engine.load()
    yield
    # (cleanup goes here if needed in the future)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="VoiceSync API",
    description="Open-source voice cloning TTS service powered by Chatterbox.",
    version="0.1.0",
    lifespan=lifespan,
)

# Serve generated MP3 files under /audio
app.mount("/audio", StaticFiles(directory=str(OUTPUTS_DIR)), name="audio")

# Serve test environment website at /test-site
app.mount("/test-site", StaticFiles(directory="test_environment", html=True), name="test-site")

# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
def require_auth(x_api_key: str = Header(default=None)) -> None:
    """Validate the X-API-Key header against the configured API_KEY."""
    if x_api_key != config.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz API key.",
        )

# ---------------------------------------------------------------------------
# Pydantic request model
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    text: str
    voice_id: str
    language: str = "tr"

# ---------------------------------------------------------------------------
# Background task worker (plain Python function — runs in thread pool)
# ---------------------------------------------------------------------------
def run_tts(task_id: str, text: str, voice_id: str, language: str) -> None:
    """Execute TTS synthesis and update the in-memory task store."""
    try:
        output_filename = f"{task_id}.mp3"
        out_path = engine.generate(
            text=text,
            voice_id=voice_id,
            output_filename=output_filename,
            language=language,
        )
        task_result[task_id] = f"/audio/{out_path.name}"
        task_status[task_id] = "done"
    except Exception as e:
        task_status[task_id] = f"error: {e}"

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a TTS generation job",
    dependencies=[Depends(require_auth)],
)
async def generate(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """
    Accepts a text payload, queues an asynchronous TTS job, and immediately
    returns a task_id the client can poll via GET /status/{task_id}.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'text' alanı boş olamaz.",
        )

    task_id = str(uuid.uuid4())
    task_status[task_id] = "processing"

    background_tasks.add_task(
        run_tts,
        task_id=task_id,
        text=request.text,
        voice_id=request.voice_id,
        language=request.language,
    )

    return {"task_id": task_id, "status": "processing"}


@app.get(
    "/status/{task_id}",
    summary="Poll the status of a TTS job",
    dependencies=[Depends(require_auth)],
)
async def get_status(task_id: str):
    """
    Returns the current status of a task.
    When the task is done, includes the `audio_url` of the generated MP3.
    """
    current_status = task_status.get(task_id)
    if current_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{task_id}' kimliğine sahip görev bulunamadı.",
        )

    response: dict = {"task_id": task_id, "status": current_status}

    if current_status == "done":
        response["audio_url"] = task_result.get(task_id)

    return response


@app.get(
    "/voices",
    summary="List available reference voices",
    dependencies=[Depends(require_auth)],
)
async def list_voices():
    """
    Returns a list of available voice IDs (stem names of .wav files
    stored in the voices/ directory).
    """
    voices = [p.stem for p in VOICES_DIR.glob("*.wav")]
    return {"voices": voices}


@app.post(
    "/voices/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new reference voice",
    dependencies=[Depends(require_auth)],
)
async def upload_voice(
    voice_id: str,
    file: UploadFile = File(...),
):
    """
    Saves the uploaded audio file as `voices/{voice_id}.wav`.
    Existing voices with the same ID will be overwritten.
    """
    destination = VOICES_DIR / f"{voice_id}.wav"
    contents = await file.read()
    async with aiofiles.open(destination, "wb") as f:
        await f.write(contents)

    return {
        "message": f"'{voice_id}' sesi başarıyla yüklendi.",
        "voice_id": voice_id,
        "path": str(destination),
    }


@app.get(
    "/health",
    summary="Health check (no auth required)",
    # No Depends(require_auth) — intentionally public for monitoring tools
)
async def health():
    """Public health-check endpoint. Returns engine device information."""
    return {"status": "ok", "device": engine.device}
