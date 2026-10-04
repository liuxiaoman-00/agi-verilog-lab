@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Push agi-verilog-lab to GitHub

set "REPO=C:\Users\liumi\WorkBuddy\2026-10-02-20-04-02\agi-verilog-lab"
set "GITEXE=C:\Program Files\Git\cmd\git.exe"
set "REPOURL=https://github.com/liuxiaoman-00/agi-verilog-lab.git"

echo ============================================================
echo    Push agi-verilog-lab to GitHub
echo ============================================================
echo.
echo Target repository:
echo   %REPOURL%
echo.
echo Press ENTER directly to use it.
echo (Or paste a different HTTPS URL first, then press ENTER)
echo.
set /p "REPOURL=Repository URL (default above): "

if "%REPOURL%"=="" (
  echo.
  echo No URL entered. Cancelled.
  pause
  exit /b 1
)

if not exist "%GITEXE%" (
  echo.
  echo ERROR: system Git not found at %GITEXE%
  pause
  exit /b 1
)

echo.
echo [1/3] Setting remote ...
"%GITEXE%" -C "%REPO%" remote remove origin 2>nul
"%GITEXE%" -C "%REPO%" remote add origin %REPOURL%
if errorlevel 1 goto FAIL

echo [2/3] Ensuring branch is main ...
"%GITEXE%" -C "%REPO%" branch -M main

echo.
echo [3/3] Uploading now.
echo IMPORTANT: a GitHub login window will appear.
echo            Log in and click the green Authorize button.
echo            If it asks for username/password instead, cancel,
echo            then read section 4 of docs\06 GitHub guide.
echo.

"%GITEXE%" -C "%REPO%" push -u origin main
if errorlevel 1 goto FAIL

echo.
echo ============================================================
echo  SUCCESS!  Now check:
echo  https://github.com/liuxiaoman-00/agi-verilog-lab
echo ============================================================
echo.
pause
exit /b 0

:FAIL
echo.
echo ============================================================
echo  FAILED. Do not panic - open this file and read section 7:
echo  docs\06_GitHub^^公开仓库_手把手.md
echo ============================================================
echo.
pause
exit /b 1
