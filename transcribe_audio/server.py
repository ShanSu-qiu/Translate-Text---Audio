"""HTTP wrapper so the orchestrator can trigger this step."""
from fastapi import FastAPI

import cli

app = FastAPI()


@app.post("/run")
def run():
    cli.download()
    failures = cli.transcribe()
    cli.upload()
    # Recordings that could not be transcribed are reported, not fatal, so the rest still flow on
    return {"status": "ok", "failed": [{"id": rec_id, "error": error} for rec_id, error in failures]}
