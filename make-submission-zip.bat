@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo  打包赛事提交材料
echo  队伍: 本科生组 / U104 / 冲冲
echo ============================================================
echo.

python package_submission.py
if errorlevel 1 (
  echo.
  echo [失败] 打包未完成。请检查上面的错误信息。
  pause
  exit /b 1
)

echo.
echo 打开 submit 文件夹查看生成的 ZIP...
start "" "%~dp0submit"
echo.
pause
