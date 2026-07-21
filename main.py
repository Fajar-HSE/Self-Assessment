"""
Self-Assessment App — Main Entry Point
"""
import os
import sys
import json
import logging
from pathlib import Path

os.environ["PYTHONPATH"] = ""  # Remove Hermes contamination
sys.path = [p for p in sys.path if 'hermes-agent' not in p]

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# Add this project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ICC Self-Assessment", version="1.0.0")


# ─── Serve Frontend ───

@app.get("/", response_class=HTMLResponse)
def index():
    return _serve_html("index.html")


@app.get("/app/{path:path}", response_class=HTMLResponse)
def app_pages(path: str):
    # whitelist safe paths
    safe = ["assessment", "results", "profile", "schemes", "login"]
    page = path.split("/")[0]
    if page in safe or page == "":
        return _serve_html("index.html")
    return _serve_html(f"static/{path}")


def _serve_html(name: str) -> str:
    html_path = os.path.join(os.path.dirname(__file__), "static", name)
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    return f"<h1>404 - {name} not found</h1>", 404


# ─── Mount API ───

from .api import router
app.include_router(router)


# ─── Startup ───

@app.on_event("startup")
def startup():
    from .database import init_db
    from .seeder import seed
    init_db()
    seed()
    logging.info("✅ Self-Assessment App ready")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8020))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
