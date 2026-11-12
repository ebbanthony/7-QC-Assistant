@echo off
REM One-time setup: creates a private Python environment and installs dependencies.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -m venv .venv || (echo Python 3.11+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt || (pause & exit /b 1)
echo.
echo Setup complete. Double-click "Launch Dashboard.bat" to start.
pause
