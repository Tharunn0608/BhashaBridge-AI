@echo off
REM BhashaBridge AI - one-step setup and run for Windows.
setlocal
cd /d "%~dp0"
title BhashaBridge AI

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  echo During install, tick "Add python.exe to PATH". Then run this file again.
  pause
  exit /b 1
)

if not exist venv (
  echo Creating virtual environment...
  %PY% -m venv venv
  if errorlevel 1 ( echo Could not create the virtual environment. & pause & exit /b 1 )
)
call venv\Scripts\activate.bat

echo Installing dependencies (first run takes a minute)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 ( echo Dependency installation failed. Check your internet connection. & pause & exit /b 1 )

if not exist .env (
  copy /y .env.example .env >nul
  echo.
  echo Created .env. Notepad will open: replace your_new_api_key with your real Gnani API key,
  echo save the file, close Notepad, then run run.bat again.
  notepad .env
  pause
  exit /b 0
)
findstr /c:"your_new_api_key" .env >nul && echo NOTE: .env still has the placeholder GNANI_API_KEY. Voice features need your real key.

echo.
echo Starting BhashaBridge AI at http://127.0.0.1:5000   (press Ctrl+C to stop)
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5000"
python app.py
pause
