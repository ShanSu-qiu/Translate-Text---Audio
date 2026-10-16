"""Turn a free-form user request into an orchestrator intent using Gemini."""
import os
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

GCP_PROJECT = "project-e8f5a204-d5ce-4c07-9c7"
GCP_LOCATION = "us-central1"
DEFAULT_MODEL = "gemini-2.5-flash-lite"

# Kept in sync with SUPPORTED_LANGUAGES in api.py
Language = Literal["en", "fr", "es", "de", "it", "ja", "zh"]
Intent = Literal["transcript", "podcast_text", "translated_text", "audio", "unsupported"]


class Classification(BaseModel):
    intent: Intent
    languages: list[Language]
    unsupported_languages: list[str]
    reason: str


SYSTEM_PROMPT = """You route requests for a podcast pipeline. The pipeline takes a recorded
English audio clip, transcribes it, expands it into a podcast script, can translate the
script, and can turn the script into spoken audio.

Pick exactly one intent:
- transcript: the user only wants the raw transcription of the recording.
- podcast_text: the user wants the podcast script / written text in English.
- translated_text: the user wants the script as text in one or more other languages.
- audio: the user wants spoken audio / a podcast to listen to, in any language.
- unsupported: the request has nothing to do with this pipeline.

Languages, as codes: en (English), fr (French), es (Spanish), de (German), it (Italian),
ja (Japanese), zh (Chinese / Mandarin). Map any way the user names a language, in any language, to these codes.
- Put every requested language that is not in that list into unsupported_languages,
  using its English name.
- For audio with no language mentioned, use ["en"].
- For translated_text, never include en.
- For transcript, podcast_text and unsupported, use [].

reason: one short sentence explaining the choice."""

client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)


def classify(query):
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=Classification,
            temperature=0,
        ),
    )
    if response.parsed is None:
        raise ValueError(f"Could not parse classifier output: {response.text}")
    return response.parsed
