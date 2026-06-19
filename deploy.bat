@echo off
cd /d "%~dp0"
start "Local QQ Agent Deploy" powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0debug_start.ps1"

