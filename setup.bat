@echo off
REM One-time setup: creates a private Python environment and installs dependencies.
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && python --version >nul 2>nul && set PY=python
if not defined PY (
  echo Python was not found. Installing Python 3.12 with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python installed. Close this window and double-click setup.bat again.
  pause
  exit /b 0
)
%PY% -m venv .venv || (echo Could not create the environment. Python 3.11+ is required. & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt || (pause & exit /b 1)
echo.
echo Setup complete. Double-click "Launch Dashboard.bat" to start.
pause
