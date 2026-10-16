import pytest

import library
from library import InvalidUpload, parse_range, summarize


def test_summarize_groups_outputs_by_recording():
    names = [
        "input_audios/",
        "input_audios/input-a.mp3",
        "input_audios/input-b.webm",
        "text_prompts/sophies/input-a.txt",
        "text_paragraphs/sophies/input-a.txt",
        "text_translated/fr/sophies/input-a.txt",
        "text_translated/zh/sophies/input-a.txt",
        "output_audios/zh/sophies/input-a.wav",
        "output_audios/en/sophies/input-a.wav",
        "text_prompts/sophies/input-b.txt",
    ]
    result = summarize(names, {"input_audios/input-a.mp3": 100, "input_audios/input-b.webm": 200})

    assert [r["id"] for r in result] == ["input-b", "input-a"]  # newest first
    a = result[1]
    assert a["input"] == "input_audios/input-a.mp3"
    assert a["transcript"] and a["script"]
    assert a["translations"] == ["fr", "zh"]
    assert a["audio"] == ["en", "zh"]
    b = result[0]
    assert b["transcript"] and not b["script"]
    assert b["translations"] == [] and b["audio"] == []


def test_summarize_skips_old_layout_other_groups_and_orphans():
    names = [
        "input_audios/input-a.mp3",
        "text_translated/sophies/input-a.txt",       # old layout without a language
        "output_audios/sophies/input-a.mp3",          # old layout
        "output_audios/fr/someone-else/input-a.wav",  # another group
        "text_prompts/sophies/input-gone.txt",        # source audio was deleted
        "input_audios/notes.txt",                     # not a recording
    ]
    result = summarize(names, {})
    assert [r["id"] for r in result] == ["input-a"]
    assert result[0]["translations"] == [] and result[0]["audio"] == []


@pytest.mark.parametrize("header, expected", [
    ("bytes=0-1", (0, 1)),
    ("bytes=100-199", (100, 199)),
    ("bytes=900-", (900, 999)),          # open-ended, clipped to the file
    ("bytes=-100", (900, 999)),          # last 100 bytes
    ("bytes=500-5000", (500, 999)),      # end past the file is clipped
    ("bytes=1000-", None),               # starts past the end
    ("bytes=-", None),
    ("items=0-1", None),
    ("", None),
])
def test_parse_range(header, expected):
    assert parse_range(header, 1000) == expected


def test_parse_range_caps_open_ended_requests():
    size = 100 * 1024 * 1024
    start, end = parse_range("bytes=0-", size)
    assert (start, end) == (0, library.MAX_RANGE_BYTES - 1)


@pytest.mark.parametrize("filename, content_type, data, message", [
    ("notes.txt", "text/plain", b"x", "unsupported audio type"),
    ("clip.mp3", "audio/mpeg", b"", "empty"),
    ("clip.mp3", "audio/mpeg", b"x" * (library.MAX_UPLOAD_BYTES + 1), "larger than"),
])
def test_save_upload_rejects_bad_files(filename, content_type, data, message):
    with pytest.raises(InvalidUpload, match=message):
        library.save_upload(filename, content_type, data)


def test_save_upload_uses_mime_type_when_name_has_no_extension(monkeypatch):
    uploaded = {}

    class FakeBlob:
        def __init__(self, name):
            uploaded["name"] = name

        def upload_from_string(self, data, content_type):
            uploaded["content_type"] = content_type

    class FakeBucket:
        def blob(self, name):
            return FakeBlob(name)

    monkeypatch.setattr(library, "_bucket", lambda: FakeBucket())
    rec_id = library.save_upload("blob", "audio/webm;codecs=opus", b"audio")

    assert library.is_recording_id(rec_id)
    assert uploaded["name"] == f"input_audios/{rec_id}.webm"
    assert uploaded["content_type"] == "audio/webm"


@pytest.mark.parametrize("value, ok", [
    ("input-20261016-120000-abc123", True),
    ("input-test", True),
    ("../secrets", False),
    ("input-a/../../x", False),
    ("output-a", False),
])
def test_is_recording_id(value, ok):
    assert library.is_recording_id(value) is ok
