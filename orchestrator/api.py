import os
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import jobs
import library
from classifier import check_classification, classify
from pipeline import (
    INTENTS, SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, PlanError, build_plan, describe,
)

TEXT_KINDS = ("transcript", "script", "translation")
STREAM_CHUNK_BYTES = 256 * 1024
GCS_READ_CHUNK_BYTES = 1024 * 1024
WAIT_POLL_SECONDS = 1

app = FastAPI(title="Mega Pipeline")

# The web UI is served from this app locally; a separately hosted UI (e.g. Vercel) must be listed here
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:9000").split(",")
        if o.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Range"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)


class Request(BaseModel):
    intent: Literal["transcript", "podcast_text", "translated_text", "audio"]
    languages: list[str] = [SOURCE_LANGUAGE]


class Ask(BaseModel):
    query: str


class JobRequest(BaseModel):
    query: str | None = None
    intent: str | None = None
    languages: list[str] = []


# ---------- pipeline ----------

@app.get("/languages")
def languages():
    return {"source": SOURCE_LANGUAGE, "supported": SUPPORTED_LANGUAGES, "intents": INTENTS}


def submit_job(**kwargs):
    try:
        return jobs.submit(**kwargs)
    except PlanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except jobs.JobBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))


def wait_for(job):
    while job.finished_at is None:
        time.sleep(WAIT_POLL_SECONDS)
        job = jobs.store.get(job.id)
    if job.status == "failed":
        status = 400 if not job.plan else 502
        raise HTTPException(status_code=status, detail=job.to_dict())
    return job.to_dict()


@app.post("/jobs", status_code=202)
def create_job(req: JobRequest):
    """Start a pipeline run in the background. Poll GET /jobs/{id} for progress."""
    query = (req.query or "").strip()
    if query:
        return submit_job(query=query).to_dict()
    if not req.intent:
        raise HTTPException(status_code=400, detail="send either a query or an intent")
    return submit_job(intent=req.intent, languages=req.languages).to_dict()


@app.get("/jobs/latest")
def latest_job():
    job = jobs.store.latest()
    if job is None:
        raise HTTPException(status_code=404, detail="no jobs yet")
    return job.to_dict()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.post("/run")
def run(req: Request):
    """Run an intent and wait for it to finish."""
    return wait_for(submit_job(intent=req.intent, languages=req.languages))


@app.post("/classify")
def classify_only(req: Ask):
    """Show how a request would be understood, without running anything."""
    try:
        result = classify(req.query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"classifier failed: {e}")
    try:
        check_classification(result)
        plan = build_plan(result.intent, result.languages)
    except PlanError as e:
        raise HTTPException(status_code=400, detail={"classification": result.model_dump(), "error": str(e)})
    return {"classification": result.model_dump(), "plan": [describe(s) for s in plan]}


@app.post("/ask")
def ask(req: Ask):
    """Classify a free-form request with the LLM, run it, and wait for it to finish."""
    return wait_for(submit_job(query=req.query))


# ---------- recordings ----------

def check_recording_id(rec_id):
    if not library.is_recording_id(rec_id):
        raise HTTPException(status_code=400, detail="invalid recording id")


@app.get("/recordings")
def recordings():
    return library.list_recordings()


@app.post("/recordings", status_code=201)
async def upload_recording(file: UploadFile):
    data = await file.read(library.MAX_UPLOAD_BYTES + 1)
    try:
        rec_id = library.save_upload(file.filename, file.content_type, data)
    except library.InvalidUpload as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": rec_id}


@app.get("/recordings/{rec_id}/text/{kind}")
def recording_text(rec_id: str, kind: str, language: str | None = None):
    check_recording_id(rec_id)
    if kind not in TEXT_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {TEXT_KINDS}")
    if kind == "translation" and not (language and library.is_language_code(language)):
        raise HTTPException(status_code=400, detail="translation needs a language")
    try:
        text = library.read_text(kind, rec_id, language)
    except library.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": rec_id, "kind": kind, "language": language, "text": text}


def stream_bytes(blob, start, end):
    """Yield blob bytes start..end (inclusive) as they arrive from GCS, so playback starts fast."""
    remaining = end - start + 1
    with blob.open("rb", chunk_size=GCS_READ_CHUNK_BYTES) as f:
        f.seek(start)
        while remaining > 0:
            chunk = f.read(min(STREAM_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def audio_response(blob, range_header):
    """Serve a GCS object with HTTP range support (Safari will not play audio without it)."""
    size = blob.size
    media_type = blob.content_type or "application/octet-stream"
    if not range_header:
        return StreamingResponse(
            stream_bytes(blob, 0, size - 1),
            media_type=media_type,
            headers={"Content-Length": str(size), "Accept-Ranges": "bytes"},
        )
    span = library.parse_range(range_header, size)
    if span is None:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    start, end = span
    return StreamingResponse(
        stream_bytes(blob, start, end),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
        },
    )


@app.get("/recordings/{rec_id}/source")
def recording_source(rec_id: str, range: str | None = Header(default=None)):
    check_recording_id(rec_id)
    try:
        blob = library.find_input(rec_id)
    except library.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return audio_response(blob, range)


@app.get("/recordings/{rec_id}/audio/{language}")
def recording_audio(rec_id: str, language: str, range: str | None = Header(default=None)):
    check_recording_id(rec_id)
    if not library.is_language_code(language):
        raise HTTPException(status_code=400, detail="invalid language")
    try:
        blob = library.get_audio_blob(rec_id, language)
    except library.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return audio_response(blob, range)


# ---------- web UI ----------

# Mounted last so the API routes above take precedence
WEB_DIR = os.environ.get("WEB_DIR", "/web")
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
