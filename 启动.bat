@echo off
chcp 65001 >nul
cd /d "%~dp0"
python gui.py
if errorlevel 1 (
  echo.
  echo 启动失败，试试先运行：python --version
  pause
)