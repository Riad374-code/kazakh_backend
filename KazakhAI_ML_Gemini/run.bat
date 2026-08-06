@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\uvicorn.exe" (
    echo .venv not found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat
echo Starting Khudaferin Logic API on http://localhost:8000
echo Swagger docs: http://localhost:8000/docs
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
