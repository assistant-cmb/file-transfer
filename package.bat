@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 package_release.py %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo 未找到 Python 3，无法执行打包。
        pause
        exit /b 1
    )
    python package_release.py %*
)

if errorlevel 1 (
    pause
    exit /b 1
)

echo.
pause
