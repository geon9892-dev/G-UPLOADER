@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [G-UPLOADER] 처음 실행입니다. 필요한 프로그램을 설치합니다. 몇 분 걸릴 수 있습니다.
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Python 3.12를 찾지 못했습니다. https://www.python.org 에서 설치한 뒤 다시 실행해 주세요.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  nvidia-smi > nul 2>&1 && ".venv\Scripts\python.exe" -m pip install -r requirements-gpu.txt
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
