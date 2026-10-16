import pytest

from pipeline import PlanError, build_plan, describe


def plan_names(intent, languages):
    return [describe(s) for s in build_plan(intent, languages)]


def test_transcript_needs_no_language():
    assert plan_names("transcript", []) == ["transcribe"]


def test_podcast_text_ignores_languages():
    assert plan_names("podcast_text", ["fr"]) == ["transcribe", "generate"]


def test_english_audio_skips_translation():
    assert plan_names("audio", ["en"]) == ["transcribe", "generate", "synthesis:en"]


def test_multi_language_audio_shares_upstream_steps():
    assert plan_names("audio", ["fr", "en", "zh"]) == [
        "transcribe", "generate",
        "translate:fr", "synthesis:fr",
        "synthesis:en",
        "translate:zh", "synthesis:zh",
    ]


def test_translated_text_in_english_is_just_the_script():
    assert plan_names("translated_text", ["en", "es"]) == ["transcribe", "generate", "translate:es"]


def test_duplicate_languages_run_once():
    assert plan_names("audio", ["fr", "fr"]) == ["transcribe", "generate", "translate:fr", "synthesis:fr"]


@pytest.mark.parametrize("intent, languages, message", [
    ("audio", [], "needs at least one language"),
    ("translated_text", [], "needs at least one language"),
    ("audio", ["ko"], "unsupported languages"),
    ("dance", ["en"], "unknown intent"),
])
def test_rejects_unrunnable_requests(intent, languages, message):
    with pytest.raises(PlanError, match=message):
        build_plan(intent, languages)


class FakeResponse:
    def __init__(self, status, body=None, text=""):
        self.status_code = status
        self.is_error = status >= 400
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def test_run_step_returns_component_reply(monkeypatch):
    import pipeline
    monkeypatch.setattr(pipeline.httpx, "post", lambda *a, **k: FakeResponse(200, {"failed": [{"id": "input-x", "error": "bad"}]}))
    assert pipeline.run_step(("transcribe", None)) == {"failed": [{"id": "input-x", "error": "bad"}]}


@pytest.mark.parametrize("response, message", [
    (FakeResponse(400, {"detail": "Unsupported language 'xx'"}), "Unsupported language 'xx'"),
    (FakeResponse(500, None, "Internal Server Error"), "returned HTTP 500"),
])
def test_run_step_surfaces_component_errors(monkeypatch, response, message):
    import pipeline
    monkeypatch.setattr(pipeline.httpx, "post", lambda *a, **k: response)
    with pytest.raises(pipeline.StepError, match=message):
        pipeline.run_step(("synthesis", "xx"))
