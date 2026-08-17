@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  py -3.10 -c "import sys;raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_py310
  py -3 -c "import sys;raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_py
)

where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys;raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_python
)
where python3 >nul 2>nul
if not errorlevel 1 (
  python3 -c "import sys;raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_python3
)
goto missing

:run_py310
py -3.10 setup.py %*
goto finished

:run_py
py -3 setup.py %*
goto finished

:run_python
python setup.py %*
goto finished

:run_python3
python3 setup.py %*

:finished
set "STATUS=%ERRORLEVEL%"
if not "%STATUS%"=="0" pause
exit /b %STATUS%

:missing
echo No usable Python 3.10 or newer installation was found.
echo The Windows py launcher may contain a stale entry. The script also tried python and python3.
pause
exit /b 1
