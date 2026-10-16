"""HTTP wrapper so the orchestrator can trigger this step."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import cli

app = FastAPI()


class RunRequest(BaseModel):
    language: str


@app.post("/run")
def run(req: RunRequest):
    try:
        cli.download()
        cli.translate(req.language)
        cli.upload(req.language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "language": req.language}
