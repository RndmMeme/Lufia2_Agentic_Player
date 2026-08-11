@echo off
setlocal
cd /d "%~dp0"

set "MODEL_STARTER=D:\KoboldCpp\models\start_nanbeige_server-cuda.bat"
set "GOAL=Traverse every room of the Secret Skills Cave tutorial loop, solve required puzzles, defeat only required blocking enemies, and return to the dungeon entrance where you started."
set "CHECK_ONLY=0"
if /I "%~1"=="--check" set "CHECK_ONLY=1"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    pause
    exit /b 1
)

if /I "%~1"=="--stop" (
    python tools\session_control.py stop
    if errorlevel 1 exit /b 1
    exit /b 0
)
if /I "%~1"=="--status" (
    python tools\session_control.py status
    if errorlevel 1 exit /b 1
    exit /b 0
)

python tools\session_control.py assert-clear
if errorlevel 1 (
    pause
    exit /b 1
)

python tools\start_or_wait_model_server.py --starter "%MODEL_STARTER%" --wait-seconds 180
if errorlevel 1 (
    echo ERROR: Model server preflight failed.
    pause
    exit /b 1
)

echo Checking Mesen Lua bridge...
python wram_discovery\mesen_bridge.py doctor
if errorlevel 1 (
    echo ERROR: Mesen Lua bridge is unavailable. Reload the project Lua bridge and try again.
    pause
    exit /b 1
)
python -c "from wram_discovery.mesen_bridge import MesenFileBridge; b=MesenFileBridge(); b.start(); p=b.ping()['protocol_version']; a=b.recovery_anchor_info(); assert p >= 4 and a['anchor_bytes'] > 0; print('Read-only slot 3 recovery anchor:', a['path'], a['anchor_bytes'], 'bytes')"
if errorlevel 1 (
    echo ERROR: Mesen Lua bridge protocol 4 and a readable slot 3 anchor are required.
    pause
    exit /b 1
)
if "%CHECK_ONLY%"=="1" (
    echo Preflight successful. No agent session was started.
    exit /b 0
)
echo Starting bounded 20-hour learning session...
python tools\run_long_session.py ^
    --hours 20 ^
    --cycle-minutes 15 ^
    --cycle-actions 400 ^
    --max-unchanged-cycles 4 ^
    --recovery slot3 ^
    --recovery-pause-seconds 30 ^
    --goal "%GOAL%"

set "RESULT=%ERRORLEVEL%"
echo.
echo Long learning session finished with exit code %RESULT%.
echo Run artifacts are under data\runs\long_YYYYMMDD_HHMMSS.
pause
exit /b %RESULT%
