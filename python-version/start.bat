@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
  set "PYTHON_ARGS="
  goto validate
)
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
  goto validate
)
where python >nul 2>nul
if errorlevel 1 goto missing
set "PYTHON_EXE=python"
set "PYTHON_ARGS="

:validate
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys;raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto old_version
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import PIL;raise SystemExit(0 if PIL.__version__ == '12.3.0' else 1)" >nul 2>nul
if errorlevel 1 goto missing_dependency
"%PYTHON_EXE%" %PYTHON_ARGS% -m file_transfer serve
set "STATUS=%ERRORLEVEL%"
if not "%STATUS%"=="0" pause
exit /b %STATUS%

:missing
echo Python 3 was not found. Please install Python 3.11 or newer.
pause
exit /b 1

:old_version
echo Python 3.11 or newer is required.
pause
exit /b 1

:missing_dependency
echo Pillow 12.3.0 is missing. Run setup.bat first.
pause
exit /b 1
