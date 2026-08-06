@echo off
echo Setting up Python venv for AASHRAY ML service...

cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating venv and installing requirements...
call .venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo Starting ML classifier service on port 5001...
python app.py

pause
