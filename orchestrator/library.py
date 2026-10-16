"""Read pipeline results from the GCS bucket and accept new recordings."""
import functools
import os
import re
import time
import uuid

from google.cloud import storage

GCP_PROJECT = "project-e8f5a204-d5ce-4c07-9c7"
BUCKET_NAME = "sophie-mega-pipeline"
GROUP_NAME = "sophies"

INPUT_PREFIX = "input_audios/"
TRANSCRIPT_PREFIX = f"text_prompts/{GROUP_NAME}/"
SCRIPT_PREFIX = f"text_paragraphs/{GROUP_NAME}/"
TRANSLATED_ROOT = "text_translated/"
AUDIO_ROOT = "output_audios/"

ALLOWED_UPLOAD_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}
# Speech-to-Text takes at most 10 MB of inline audio, which is how transcribe_audio sends it
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# Cap open-ended range requests so a single response never loads a whole 30 MB file
MAX_RANGE_BYTES = 4 * 1024 * 1024

RECORDING_ID = re.compile(r"^input-[A-Za-z0-9_-]+$")
LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}$")

@functools.cache
def _bucket():
    # Created on first use so importing this module (e.g. in tests) needs no credentials
    return storage.Client(project=GCP_PROJECT).bucket(BUCKET_NAME)


class NotFound(LookupError):
    pass


class InvalidUpload(ValueError):
    pass


def is_recording_id(value):
    return bool(RECORDING_ID.match(value))


def is_language_code(value):
    return bool(LANGUAGE_CODE.match(value))


def _stem(name):
    return os.path.splitext(os.path.basename(name))[0]


def summarize(blob_names, input_times):
    """Group bucket object names into one summary per recording.

    blob_names: every object name in the bucket. input_times: {input object name: unix time}.
    Pure function so it can be unit tested without GCS.
    """
    recordings = {}

    def entry(rec_id):
        return recordings.setdefault(rec_id, {
            "id": rec_id, "input": None, "created_at": None,
            "transcript": False, "script": False, "translations": [], "audio": [],
        })

    for name in blob_names:
        if name.endswith("/"):
            continue
        rec_id = _stem(name)
        if not is_recording_id(rec_id):
            continue
        if name.startswith(INPUT_PREFIX):
            entry(rec_id).update(input=name, created_at=input_times.get(name))
        elif name.startswith(TRANSCRIPT_PREFIX):
            entry(rec_id)["transcript"] = True
        elif name.startswith(SCRIPT_PREFIX):
            entry(rec_id)["script"] = True
        elif name.startswith(TRANSLATED_ROOT) or name.startswith(AUDIO_ROOT):
            # <root>/<language>/<group>/<id>.<ext>; older layouts without a language are skipped
            parts = name.split("/")
            if len(parts) != 4 or parts[2] != GROUP_NAME or not is_language_code(parts[1]):
                continue
            key = "translations" if name.startswith(TRANSLATED_ROOT) else "audio"
            entry(rec_id)[key].append(parts[1])

    for rec in recordings.values():
        rec["translations"].sort()
        rec["audio"].sort()
    # Only recordings whose source audio still exists, newest first
    return sorted(
        (r for r in recordings.values() if r["input"]),
        key=lambda r: r["created_at"] or 0,
        reverse=True,
    )


def list_recordings():
    names = []
    input_times = {}
    for blob in _bucket().list_blobs():
        names.append(blob.name)
        if blob.name.startswith(INPUT_PREFIX) and blob.time_created:
            input_times[blob.name] = blob.time_created.timestamp()
    return summarize(names, input_times)


def text_path(kind, rec_id, language=None):
    if kind == "transcript":
        return f"{TRANSCRIPT_PREFIX}{rec_id}.txt"
    if kind == "script":
        return f"{SCRIPT_PREFIX}{rec_id}.txt"
    return f"{TRANSLATED_ROOT}{language}/{GROUP_NAME}/{rec_id}.txt"


def read_text(kind, rec_id, language=None):
    blob = _bucket().get_blob(text_path(kind, rec_id, language))
    if blob is None:
        raise NotFound(f"no {kind} for {rec_id}")
    return blob.download_as_text()


def find_input(rec_id):
    for blob in _bucket().list_blobs(prefix=f"{INPUT_PREFIX}{rec_id}."):
        return blob
    raise NotFound(f"no recording {rec_id}")


def get_audio_blob(rec_id, language):
    blob = _bucket().get_blob(f"{AUDIO_ROOT}{language}/{GROUP_NAME}/{rec_id}.wav")
    if blob is None:
        raise NotFound(f"no {language} audio for {rec_id}")
    return blob


def parse_range(header, size):
    """Parse a single 'bytes=start-end' Range header. Returns (start, end) inclusive, or None."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", (header or "").strip())
    if not match or size == 0:
        return None
    start_s, end_s = match.groups()
    if start_s == "" and end_s == "":
        return None
    if start_s == "":  # suffix range: last N bytes
        start, end = max(0, size - int(end_s)), size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else min(size - 1, start + MAX_RANGE_BYTES - 1)
    end = min(end, size - 1)
    if start > end:
        return None
    return start, end


def save_upload(filename, content_type, data):
    """Store a new recording as input_audios/input-<timestamp>-<rand><ext>. Returns its id."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_TYPES:
        # Browser recordings may arrive without a useful name; fall back to the MIME type
        by_type = {v: k for k, v in ALLOWED_UPLOAD_TYPES.items()}
        ext = by_type.get((content_type or "").split(";")[0].strip())
    if not ext:
        raise InvalidUpload(f"unsupported audio type, use one of {sorted(ALLOWED_UPLOAD_TYPES)}")
    if not data:
        raise InvalidUpload("the file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidUpload(f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    rec_id = f"input-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    blob = _bucket().blob(f"{INPUT_PREFIX}{rec_id}{ext}")
    blob.upload_from_string(data, content_type=ALLOWED_UPLOAD_TYPES[ext])
    return rec_id
