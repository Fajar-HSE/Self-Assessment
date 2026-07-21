#!/usr/bin/env python3
"""Install dependencies for self-assessment app."""
import subprocess, sys, os

# Clean path
env = os.environ.copy()
for k in list(env.keys()):
    if 'hermes' in k.lower():
        env.pop(k, None)

venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'Scripts', 'python.exe')
venv_pip = os.path.join(os.path.dirname(__file__), 'venv', 'Scripts', 'pip.exe')

pkgs = ['fastapi', 'uvicorn', 'sqlalchemy', 'aiosqlite', 'httpx', 'jinja2', 'python-multipart', 'python-dotenv']

for pkg in pkgs:
    print(f"Installing {pkg}...")
    r = subprocess.run([venv_pip, 'install', pkg], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        r2 = subprocess.run([venv_pip, 'install', pkg], capture_output=True, text=True)
        if r2.returncode != 0:
            print(f"FAILED: {pkg} - {r2.stderr[-300:]}")
        else:
            print(f"OK {pkg}")
    else:
        print(f"OK {pkg}")

print("\n--- Verification ---")
r = subprocess.run([venv_python, '-c', 'import fastapi, uvicorn, sqlalchemy, httpx, jinja2, dotenv; print("All imports OK")'], capture_output=True, text=True, env=env)
print(r.stdout or r.stderr[:500])
