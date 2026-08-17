@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto install

where py >nul 2>nul
if not errorlevel 1 goto create_with_py
where python >nul 2>nul
if not errorlevel 1 goto create_with_python
echo Python 3 was not found. Please install Python 3.11 or newer.
pause
exit /b 1

:create_with_py
py -3 -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto old_version
echo Creating Python virtual environment...
py -3 -m venv .venv
if errorlevel 1 goto create_failed
goto install

:create_with_python
python -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto old_version
echo Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 goto create_failed

:install
".venv\Scripts\python.exe" -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto old_version
echo Installing locked dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -c "import PIL;raise SystemExit(0 if PIL.__version__ == '12.3.0' else 1)"
if errorlevel 1 goto verify_failed
echo Setup complete. Return to the project root and run start.bat.
pause
exit /b 0

:old_version
echo Python 3.11 or newer is required.
pause
exit /b 1

:create_failed
echo Could not create .venv. Make sure the Python venv module is available.
pause
exit /b 1

:install_failed
echo Dependency installation failed. Check the network and run setup.bat again.
pause
exit /b 1

:verify_failed
echo Pillow version verification failed. Delete .venv and run setup.bat again.
pause
exit /b 1
