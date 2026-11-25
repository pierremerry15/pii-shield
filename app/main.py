"""Demo web app.

uvicorn app.main:app --reload      # then open http://localhost:8000
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from baselines.pathreview_original import PIIScrubber as Original
from baselines.pathreview_pr98 import PIIScrubber as PR98
from pii_shield import Shield
from pii_shield.llm import DEFAULT_MODEL, guarded_complete

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
MAX_CHARS = 20_000

app = FastAPI(title="PII Shield", version="2.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/docs-assets", StaticFiles(directory=ROOT / "docs"), name="docs-assets")

shield = Shield()
baselines = {"original": Original(), "pr98": PR98()}

SAMPLES = {
    "Resume header": (
        "Ana Diaz | (555) 201-3344 | ana.diaz@example.com\n"
        "2400 Sixth St NW, Apt 4B, Washington, DC 20059\n"
        "London office: +44 20 7946 0123\n\n"
        "Managed 12 engineers on the Way of Code project and shipped 2 features "
        "to the Court reporting tool. Released v1.12.3 on 2026-11-11."
    ),
    "Tricky prose": (
        "Ran 5 marathons and like to run on weekends. Led 3 teams that ship a park view "
        "feature. Handled 100 200 3000 requests per second at peak. ZIP 20059-1234."
    ),
    "Payment + SSN": (
        "Applicant SSN 457-55-5462. Charge card 4111 1111 1111 1111 exp 09/28. Invoice 4111 1111 1111 1112 was voided."
    ),
}


class ScanIn(BaseModel):
    text: str = Field(max_length=MAX_CHARS)


class LLMIn(BaseModel):
    text: str = Field(max_length=MAX_CHARS)
    instruction: str = Field(default="Rewrite this as a two-sentence professional summary.", max_length=2000)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "llm_enabled": bool(os.environ.get("ANTHROPIC_API_KEY")), "model": DEFAULT_MODEL}


@app.get("/api/samples")
def samples():
    return SAMPLES


@app.post("/api/scan")
def scan(body: ScanIn):
    out = {}
    for name, engine in baselines.items():
        out[name] = {"scrubbed": engine.scrub(body.text), "detections": engine.detect(body.text)}
    typed = shield.scrub(body.text, mode="typed")
    out["v2"] = {
        "scrubbed": shield.scrub(body.text).text,
        "detections": typed.detections,
        "typed": typed.text,
        "mapping": typed.mapping,
    }
    return out


@app.post("/api/llm")
def llm(body: LLMIn):
    try:
        result = guarded_complete(body.text, body.instruction)
    except Exception as exc:  # surface SDK/auth errors to the UI instead of a bare 500
        raise HTTPException(status_code=502, detail=f"LLM call failed: {type(exc).__name__}: {exc}") from exc
    return result.__dict__


@app.get("/api/eval")
def eval_results():
    path = ROOT / "eval" / "results.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run `python -m eval.run_eval` first.")
    return json.loads(path.read_text(encoding="utf-8"))
