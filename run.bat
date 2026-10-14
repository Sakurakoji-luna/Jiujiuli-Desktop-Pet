@echo off
rem DesktopSprite 启动脚本（UTF-8 控制台，避免中文乱码）
chcp 65001 >nul
cd /d %~dp0
python main.py
pause
