@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 goto use_py
where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto old_version
python -m file_transfer serve
if errorlevel 1 pause
exit /b %errorlevel%

:use_py
py -3 -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto old_version
py -3 -m file_transfer serve
if errorlevel 1 pause
exit /b %errorlevel%

:missing
echo Python 3 was not found. Please install Python 3.11 or newer.
pause
exit /b 1

:old_version
echo Python 3.11 or newer is required.
pause
exit /b 1
