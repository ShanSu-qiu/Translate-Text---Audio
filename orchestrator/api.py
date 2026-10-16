from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from classifier import classify

SOURCE_LANGUAGE = "en"
# Must match the VOICES table in synthesis_audio/cli.py and Language in classifier.py
SUPPORTED_LANGUAGES = ["en", "fr", "es", "de", "it", "ja"]

SERVICES = {
    "transcribe": "http://transcribe-audio:8000",
    "generate":   "http://generate-text:8000",
    "translate":  "http://translate-text:8000",
    "synthesis":  "http://synthesis-audio:8000",
}
STEP_TIMEOUT_SECONDS = 600

# A step is (service, language); language is None for steps that are language independent.


def depends(step):
    service, language = step
    if service == "transcribe":
        return []
    if service == "generate":
        return [("transcribe", None)]
    if service == "translate":
        return [("generate", None)]
    # synthesis: English reads the generated text, other languages need a translation first
    if language == SOURCE_LANGUAGE:
        return [("generate", None)]
    return [("translate", language)]


def target(intent, language):
    if intent == "transcript":
        return ("transcribe", None)
    if intent == "podcast_text":
        return ("generate", None)
    if intent == "translated_text":
        if language == SOURCE_LANGUAGE:
            return ("generate", None)
        return ("translate", language)
    return ("synthesis", language)


LANGUAGE_INDEPENDENT_INTENTS = {"transcript", "podcast_text"}


def build_plan(intent, languages):
    if intent in LANGUAGE_INDEPENDENT_INTENTS:
        return resolve([target(intent, None)])
    if not languages:
        raise HTTPException(status_code=400, detail=f"intent '{intent}' needs at least one language")
    return resolve([target(intent, lang) for lang in languages])


def resolve(targets):
    order = []
    def visit(step):
        for dep in depends(step):
            visit(dep)
        if step not in order:
            order.append(step)
    for t in targets:
        visit(t)
    return order


class Request(BaseModel):
    intent: Literal["transcript", "podcast_text", "translated_text", "audio"]
    languages: list[str] = [SOURCE_LANGUAGE]


def describe(step):
    service, language = step
    return f"{service}:{language}" if language else service


app = FastAPI()


@app.get("/languages")
def languages():
    return {"source": SOURCE_LANGUAGE, "supported": SUPPORTED_LANGUAGES}


def execute(intent, languages):
    unsupported = [lang for lang in languages if lang not in SUPPORTED_LANGUAGES]
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported languages {unsupported}, choose from {SUPPORTED_LANGUAGES}",
        )

    plan = build_plan(intent, languages)
    done = []
    for step in plan:
        service, language = step
        body = {"language": language} if language else None
        try:
            r = httpx.post(f"{SERVICES[service]}/run", json=body, timeout=STEP_TIMEOUT_SECONDS)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "plan": [describe(s) for s in plan],
                    "done": done,
                    "failed": describe(step),
                    "error": str(e),
                },
            )
        done.append(describe(step))
    return {"plan": [describe(s) for s in plan], "done": done, "status": "ok"}


@app.post("/run")
def run(req: Request):
    return execute(req.intent, req.languages)


class Ask(BaseModel):
    query: str


def classify_or_fail(query):
    try:
        result = classify(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"classifier failed: {e}")
    if result.intent == "unsupported":
        raise HTTPException(status_code=400, detail={"classification": result.model_dump()})
    if result.unsupported_languages:
        raise HTTPException(
            status_code=400,
            detail={
                "classification": result.model_dump(),
                "error": f"unsupported languages {result.unsupported_languages}, "
                         f"choose from {SUPPORTED_LANGUAGES}",
            },
        )
    return result


@app.post("/classify")
def classify_only(req: Ask):
    """Show how a request would be understood, without running anything."""
    result = classify_or_fail(req.query)
    plan = build_plan(result.intent, result.languages)
    return {"classification": result.model_dump(), "plan": [describe(s) for s in plan]}


@app.post("/ask")
def ask(req: Ask):
    """Classify a free-form request with the LLM, then run the matching pipeline."""
    result = classify_or_fail(req.query)
    return {"classification": result.model_dump(), **execute(result.intent, result.languages)}
