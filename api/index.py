"""
Vercel serverless entry point.
Exports the FastAPI app as 'handler' for Vercel Python runtime.
"""
import os, sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

# Clean path
os.environ["PYTHONPATH"] = ""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.api import router
from app.database import init_db
from app.seeder import seed

app = FastAPI(title="ICC Self-Assessment", version="1.0.0")

# Mount static files
static_dir = root / "app" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include API router
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>ICC Self-Assessment</h1><p>Frontend not found.</p>"


@app.on_event("startup")
def startup():
    init_db()
    seed()


# Vercel ASGI handler
handler = app
