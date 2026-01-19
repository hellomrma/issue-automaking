@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
    echo [run] .venv 이 없습니다. 먼저 다음을 실행하세요:
    echo   python -m venv .venv
    echo   install.bat 또는 python -m pip install -r requirements.txt
    exit /b 1
)
call .venv\Scripts\activate.bat
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
