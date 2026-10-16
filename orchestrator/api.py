import httpx
from fastapi import FastAPI
from pydantic import BaseModel

SERVICES = {
    "transcribe": "http://transcribe-audio:8000",
    "generate":   "http://generate-text:8000",
    "synth_en":   "http://synthesis-audio-en:8000",
    "translate":  "http://translate-text:8000",
    "synth_fr":   "http://synthesis-audio:8000",
}
DEPENDS = {
    "transcribe": [],
    "generate":   ["transcribe"],
    "synth_en":   ["generate"],
    "translate":  ["generate"],
    "synth_fr":   ["translate"],
}
INTENTS = {
    "transcript":    ["transcribe"],
    "podcast_text":  ["generate"],
    "english_audio": ["synth_en"],
    "french_audio":  ["synth_fr"],
    "everything":    ["synth_en", "synth_fr"],
}

def resolve(targets):
    order = []
    def visit(step):
        for dep in DEPENDS[step]:
            visit(dep)
        if step not in order:
            order.append(step)
    for t in targets:
        visit(t)
    return order

class Request(BaseModel):
    intent: str

app = FastAPI()

@app.post("/run")
def run(req: Request):
    if req.intent not in INTENTS:
        return {"error": f"unknown intent, choose from {list(INTENTS)}"}
    plan = resolve(INTENTS[req.intent])
    done = []
    for step in plan:
        try:
            r = httpx.post(f"{SERVICES[step]}/run", timeout=600)
            r.raise_for_status()
            done.append(step)
        except Exception as e:
            return {"plan": plan, "done": done, "failed": step, "error": str(e)}
    return {"plan": plan, "done": done, "status": "ok"}