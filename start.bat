@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if exist "python-version\.venv\Scripts\python.exe" (
  "python-version\.venv\Scripts\python.exe" start.py %*
  set "STATUS=!ERRORLEVEL!"
  if not "!STATUS!"=="0" pause
  exit /b !STATUS!
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
  if not errorlevel 1 (
    py -3 start.py %*
    set "STATUS=!ERRORLEVEL!"
    if not "!STATUS!"=="0" pause
    exit /b !STATUS!
  )
)

where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto missing
python start.py %*
set "STATUS=%ERRORLEVEL%"
if not "%STATUS%"=="0" pause
exit /b %STATUS%

:missing
echo The unified launcher requires Python 3.11 or newer.
pause
exit /b 1
