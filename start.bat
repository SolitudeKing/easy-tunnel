@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo uv was not found. Install it from https://docs.astral.sh/uv/ first.
    pause
    exit /b 1
)

uv run python main.py
if errorlevel 1 pause
