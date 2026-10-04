@echo off
chcp 65001 >nul
setlocal
title Push agi-verilog-lab to GitHub

set "REPO=C:\Users\liumi\WorkBuddy\2026-10-02-20-04-02\agi-verilog-lab"
set "GITEXE=C:\Program Files\Git\cmd\git.exe"

echo ============================================================
echo    Push agi-verilog-lab to GitHub
echo ============================================================
echo.
echo Step 1: On your new GitHub repo page, click the green
echo         "Code" button and copy the HTTPS line.
echo.
echo         Example:
echo         https://github.com/yourname/agi-verilog-lab.git
echo.
echo Step 2: Paste it below (right-click = paste in this window),
echo         then press Enter.
echo.
set /p "REPOURL=Repository URL: "

if "%REPOURL%"=="" (
  echo.
  echo No URL entered. Cancelled.
  pause
  exit /b 1
)

if not exist "%GITEXE%" (
  echo.
  echo ERROR: system Git not found at %GITEXE%
  echo Ask your assistant for help.
  pause
  exit /b 1
)

echo.
echo Preparing repository ...
"%GITEXE%" -C "%REPO%" remote remove origin 2>nul
"%GITEXE%" -C "%REPO%" remote add origin %REPOURL%
"%GITEXE%" -C "%REPO%" branch -M main

echo.
echo Uploading. If a browser window pops up, log in and authorize.
echo.
"%GITEXE%" -C "%REPO%" push -u origin main

echo.
if errorlevel 1 (
  echo FAILED. Check section 7 of:
  echo docs\06_GitHub^^公开仓库_手把手.md
) else (
  echo SUCCESS! Open https://github.com to see your repo.
)
echo.
pause
