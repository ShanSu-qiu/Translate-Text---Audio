"""Plan and run pipeline steps. No web framework here so jobs and routes can share it."""
import httpx

SOURCE_LANGUAGE = "en"
# Must match the VOICES table in synthesis_audio/cli.py and Language in classifier.py
SUPPORTED_LANGUAGES = ["en", "fr", "es", "de", "it", "ja", "zh"]
INTENTS = ["transcript", "podcast_text", "translated_text", "audio"]
LANGUAGE_INDEPENDENT_INTENTS = {"transcript", "podcast_text"}

SERVICES = {
    "transcribe": "http://transcribe-audio:8000",
    "generate":   "http://generate-text:8000",
    "translate":  "http://translate-text:8000",
    "synthesis":  "http://synthesis-audio:8000",
}
STEP_TIMEOUT_SECONDS = 600

# A step is (service, language); language is None for steps that are language independent.


class PlanError(ValueError):
    """The request cannot be turned into a plan (bad intent or languages)."""


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


def build_plan(intent, languages):
    if intent not in INTENTS:
        raise PlanError(f"unknown intent '{intent}', choose from {INTENTS}")
    unsupported = [lang for lang in languages if lang not in SUPPORTED_LANGUAGES]
    if unsupported:
        raise PlanError(f"unsupported languages {unsupported}, choose from {SUPPORTED_LANGUAGES}")
    if intent in LANGUAGE_INDEPENDENT_INTENTS:
        return resolve([target(intent, None)])
    if not languages:
        raise PlanError(f"intent '{intent}' needs at least one language")
    return resolve([target(intent, lang) for lang in languages])


def describe(step):
    service, language = step
    return f"{service}:{language}" if language else service


class StepError(RuntimeError):
    """A component could not run its step."""


def run_step(step):
    """Call one component's /run and return its JSON reply. Raises StepError if it fails."""
    service, language = step
    body = {"language": language} if language else None
    try:
        r = httpx.post(f"{SERVICES[service]}/run", json=body, timeout=STEP_TIMEOUT_SECONDS)
    except httpx.HTTPError as e:
        raise StepError(f"could not reach {service}: {e}") from e
    if r.is_error:
        # Components report problems as FastAPI {"detail": ...}; fall back to the status line
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        raise StepError(detail or f"{service} returned HTTP {r.status_code}, see its logs")
    return r.json()
