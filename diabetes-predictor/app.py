import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(APP_DIR / "data" / "suggestions.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
CATEGORIES = {"Feature idea", "Usability", "Model or data", "Bug report", "Other"}

app = FastAPI(title="GlucoGuide Suggestions API", version="1.0.0", description="Shared suggestion store and exports for Diabetes Predictor AI.")
origins_raw = os.getenv("CORS_ORIGINS", "*").strip()
origins = [x.strip() for x in origins_raw.split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])

class SuggestionIn(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    suggestion: str = Field(min_length=1, max_length=5000)

# Lightweight per-process abuse protection. Use a reverse proxy/WAF for production-grade controls.
_rate_lock = Lock()
_recent_posts: dict[str, list[float]] = {}
RATE_LIMIT = int(os.getenv("POSTS_PER_HOUR_PER_IP", "20"))

def connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS suggestions (
            id TEXT PRIMARY KEY,
            createdAt TEXT NOT NULL,
            category TEXT NOT NULL,
            suggestion TEXT NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_created ON suggestions(createdAt)")

init_db()

def serialize(row):
    return {"id": row["id"], "createdAt": row["createdAt"], "category": row["category"], "suggestion": row["suggestion"]}

def all_suggestions():
    with connect() as con:
        rows = con.execute("SELECT id, createdAt, category, suggestion FROM suggestions ORDER BY createdAt ASC, id ASC").fetchall()
    return [serialize(row) for row in rows]

def markdown_document(items):
    lines = ["# GlucoGuide Website Suggestions", "", f"Compiled: {datetime.now(timezone.utc).isoformat()}", f"Total suggestions: {len(items)}", "", "Review these product suggestions before using them to guide product or model changes. Suggestions are feedback, not clinical observations or training labels.", ""]
    if not items:
        lines += ["_No suggestions have been submitted._", ""]
    for i, item in enumerate(items, 1):
        lines += [f"## {i}. {item['category']}", "", f"- Submitted: {item['createdAt']}", f"- Reference: {item['id']}", "", item["suggestion"], ""]
    return "\n".join(lines)

@app.get("/health")
def health():
    return {"status": "ok", "service": "glucoguide-suggestions", "database": "sqlite"}

@app.get("/api/suggestions")
def list_suggestions(response: Response):
    response.headers["Cache-Control"] = "no-store"
    items = all_suggestions()
    return {"project": "Diabetes Predictor AI / GlucoGuide", "count": len(items), "suggestions": items}

@app.post("/api/suggestions", status_code=201)
def create_suggestion(payload: SuggestionIn, request: Request, response: Response):
    category = payload.category.strip()
    suggestion = payload.suggestion.strip()
    if category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of: {', '.join(sorted(CATEGORIES))}")
    if not suggestion:
        raise HTTPException(status_code=422, detail="suggestion cannot be blank")
    # Do not log IPs or retain them; only use them transiently for rate limiting.
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _rate_lock:
        recent = [t for t in _recent_posts.get(ip, []) if now - t < 3600]
        if len(recent) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Too many submissions from this connection. Please try again later.")
        recent.append(now)
        _recent_posts[ip] = recent
    created = datetime.now(timezone.utc).isoformat()
    item = {"id": str(uuid4()), "createdAt": created, "category": category, "suggestion": suggestion}
    with connect() as con:
        con.execute("INSERT INTO suggestions (id, createdAt, category, suggestion) VALUES (?, ?, ?, ?)", (item["id"], item["createdAt"], item["category"], item["suggestion"]))
    response.headers["Cache-Control"] = "no-store"
    return item

@app.get("/api/suggestions/export.json")
def export_json(response: Response):
    response.headers["Content-Disposition"] = 'attachment; filename="suggestions.json"'
    response.headers["Cache-Control"] = "no-store"
    return {"project": "Diabetes Predictor AI / GlucoGuide", "exportedAt": datetime.now(timezone.utc).isoformat(), "suggestions": all_suggestions()}

@app.get("/api/suggestions/export.md")
def export_markdown(response: Response):
    response.headers["Content-Disposition"] = 'attachment; filename="glucoguide_suggestions.md"'
    response.headers["Cache-Control"] = "no-store"
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(markdown_document(all_suggestions()), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="glucoguide_suggestions.md"', "Cache-Control": "no-store"})
