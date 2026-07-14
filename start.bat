@echo off
setlocal
cd /d "%~dp0"

python -c "import importlib.metadata as m; raise SystemExit(0 if m.version('flet') == '0.28.3' and m.version('flet-desktop') == '0.28.3' else 1)" >nul 2>&1
if errorlevel 1 (
    echo Installing EasyTunnel dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

python main.py
if errorlevel 1 pause
