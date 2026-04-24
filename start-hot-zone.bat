@echo off
setlocal

echo Starting core module...
call "%~dp0stack.ps1" start core
exit /b %errorlevel%
