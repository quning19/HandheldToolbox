@echo off
setlocal
cd /d "%~dp0"
if not exist "retrolibx\.venv\Scripts\pythonw.exe" (
  echo Please install the desktop dependencies. See docs/WINDOWS_GUI.md.
  pause
  exit /b 1
)
start "" "retrolibx\.venv\Scripts\pythonw.exe" "%~dp0launch_gui.py"
