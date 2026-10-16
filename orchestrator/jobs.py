"""Run pipeline requests in the background so clients can poll step-by-step progress."""
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, replace

from classifier import classify, check_classification
from pipeline import PlanError, StepError, build_plan, describe, run_step

MAX_JOBS_KEPT = 50


class JobBusyError(RuntimeError):
    """Another job is still running. Components share local folders, so jobs run one at a time."""


@dataclass(frozen=True)
class Job:
    id: str
    query: str | None
    intent: str | None
    languages: tuple[str, ...]
    status: str  # classifying | running | done | failed
    created_at: float
    classification: dict | None = None
    plan: tuple[str, ...] = ()
    done: tuple[str, ...] = ()
    current: str | None = None
    error: str | None = None
    warnings: tuple[str, ...] = ()
    finished_at: float | None = None

    def to_dict(self):
        return asdict(self)


@dataclass
class JobStore:
    _jobs: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def latest(self):
        with self._lock:
            return max(self._jobs.values(), key=lambda j: j.created_at, default=None)

    def put(self, job):
        with self._lock:
            self._jobs[job.id] = job
            # Forget the oldest finished jobs so memory stays bounded
            finished = sorted(
                (j for j in self._jobs.values() if j.finished_at),
                key=lambda j: j.created_at,
            )
            for old in finished[: max(0, len(self._jobs) - MAX_JOBS_KEPT)]:
                del self._jobs[old.id]

    def start(self, job):
        """Store a new job, refusing if another one is still active."""
        with self._lock:
            if any(j.finished_at is None for j in self._jobs.values()):
                raise JobBusyError("another job is still running, wait for it to finish")
            self._jobs[job.id] = job


store = JobStore()


def submit(query=None, intent=None, languages=()):
    """Create a job and start it in a background thread. Returns the new job."""
    if query is None:
        # Validate a direct intent request up front so bad input fails immediately
        build_plan(intent, list(languages))
    job = Job(
        id=uuid.uuid4().hex[:12],
        query=query,
        intent=intent,
        languages=tuple(languages),
        status="classifying" if query else "running",
        created_at=time.time(),
    )
    store.start(job)
    threading.Thread(target=_run, args=(job.id,), daemon=True).start()
    return job


def _update(job_id, **changes):
    job = replace(store.get(job_id), **changes)
    store.put(job)
    return job


def _fail(job_id, message):
    return _update(job_id, status="failed", current=None, error=message, finished_at=time.time())


def _run(job_id):
    # Last line of defence: a job must never stay "running", or it blocks every later job
    try:
        _execute(job_id)
    except Exception as e:
        _fail(job_id, f"unexpected error: {e}")


def _execute(job_id):
    job = store.get(job_id)
    try:
        if job.query:
            result = classify(job.query)
            job = _update(
                job_id,
                classification=result.model_dump(),
                intent=result.intent,
                languages=tuple(result.languages),
            )
            check_classification(result)
        plan = build_plan(job.intent, list(job.languages))
        job = _update(job_id, status="running", plan=tuple(describe(s) for s in plan))
    except PlanError as e:
        _fail(job_id, str(e))
        return
    except Exception as e:  # classifier/LLM failures
        _fail(job_id, f"could not understand the request: {e}")
        return

    for step in plan:
        name = describe(step)
        job = _update(job_id, current=name)
        try:
            reply = run_step(step)
        except StepError as e:
            _fail(job_id, f"step {name} failed: {e}")
            return
        # A step can succeed overall while skipping individual recordings
        skipped = tuple(f"{f['id']}: {f['error']}" for f in reply.get("failed", []))
        job = _update(job_id, done=job.done + (name,), warnings=job.warnings + skipped)
    _update(job_id, status="done", current=None, finished_at=time.time())
