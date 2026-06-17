@echo off
REM Thin wrapper for shell:startup / Task Scheduler. Delegates to start.bat
REM so the launch logic stays in one place.

cd /d "%~dp0"
call start.bat
