"""
Self-Assessment App — Main Entry Point
"""
import os, sys
import logging
from pathlib import Path

# Clean path from Hermes contamination
os.environ["PYTHONPATH"] = ""
for key in list(os.environ.keys()):
    if 'hermes' in key.lower() and key in os.environ:
        del os.environ[key]

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="ICC Self-Assessment", version="1.0.0")

# Mount static files
static_dir = Path(__file__).parent / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Import API router
from app.api import router
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>ICC Self-Assessment</h1><p>Frontend not found.</p>"


@app.on_event("startup")
def startup():
    from app.database import init_db
    from app.seeder import seed
    init_db()
    seed()
    logging.info("✅ Self-Assessment App ready")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8020))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
