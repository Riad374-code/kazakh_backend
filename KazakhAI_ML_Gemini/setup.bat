@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  Khudaferin - local environment setup (Windows)
echo ============================================================
python -m venv .venv
if errorlevel 1 ( echo Failed to create venv & exit /b 1 )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 ( echo Dependency install failed & exit /b 1 )
echo.
echo  Setup complete! Run the project with:  run.bat
echo  Full AI verification:                   .venv\Scripts\python verify_ai_engine.py
echo.
