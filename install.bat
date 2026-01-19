@echo off
cd /d "%~dp0"
echo [install] 프로젝트 폴더: %CD%
echo.

REM 가상환경이 있으면 활성화 후 설치
if exist .venv\Scripts\activate.bat (
    echo [install] .venv 사용
    call .venv\Scripts\activate.bat
) else (
    echo [install] 전역 Python 사용 (가상환경 없음)
)

echo [install] pip install -r requirements.txt
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [install] 오류 발생. 아래를 순서대로 확인하세요:
    echo   1. python --version 으로 Python 3.10 이상인지 확인
    echo   2. python -m pip --version 으로 pip 사용 가능 여부 확인
    exit /b 1
)

echo.
echo [install] 완료.
pause
