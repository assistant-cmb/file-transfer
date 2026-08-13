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
where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found. Reinstall Node.js with npm included.
  pause
  exit /b 1
)

echo Installing locked dependencies...
call npm ci --include=optional
if errorlevel 1 (
  echo Dependency installation failed. Check the network and run setup.bat again.
  pause
  exit /b 1
)
node -e "const sharp=require('sharp');process.exit(sharp.versions.sharp==='0.35.3'?0:1)"
if errorlevel 1 (
  echo sharp version or native binary verification failed. Delete node_modules and run setup.bat again.
  pause
  exit /b 1
)
echo Setup complete. You can now run start.bat.
pause
exit /b 0
