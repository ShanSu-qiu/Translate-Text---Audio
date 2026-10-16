"""HTTP wrapper so the orchestrator can trigger this step."""
from fastapi import FastAPI

import cli

app = FastAPI()


@app.post("/run")
def run():
    cli.download()
    cli.translate()
    cli.upload()
    return {"status": "ok"}
