@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Please install Node.js 20.9.0 or newer.
  pause
  exit /b 1
)
node -e "const [major,minor]=process.versions.node.split('.').map(Number);process.exit(major>20||(major===20&&minor>=9)?0:1)"
if errorlevel 1 (
  echo Node.js 20.9.0 or newer is required.
  pause
  exit /b 1
)
node -e "const sharp=require('sharp');process.exit(sharp.versions.sharp==='0.35.3'?0:1)" >nul 2>nul
if errorlevel 1 (
  echo sharp 0.35.3 is missing or its native binary cannot load. Run setup.bat first.
  pause
  exit /b 1
)
node src\cli.js serve
set "STATUS=%ERRORLEVEL%"
if not "%STATUS%"=="0" pause
exit /b %STATUS%
