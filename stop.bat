@echo off
cd /d "%~dp0"
start "Local QQ Agent Stop" powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0debug_stop.ps1"

