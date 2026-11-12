@echo off
REM Starts the dashboard and opens it in your browser (http://localhost:8501).
cd /d "%~dp0"
if not exist .venv\Scripts\streamlit.exe (echo Run setup.bat first. & pause & exit /b 1)
.venv\Scripts\streamlit run app.py --server.headless false --browser.gatherUsageStats false
