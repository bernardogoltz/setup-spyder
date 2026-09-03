@echo off
REM Local shortcut on Windows: same verbose flow as the setup-spyder package.
cd /d "%~dp0"
uv run setup-spyder %*
exit /b %ERRORLEVEL%
