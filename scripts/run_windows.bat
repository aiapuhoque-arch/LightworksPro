@echo off
cd /d "%~dp0.."
if not exist config.json (
    echo config.json not found.
    echo Copy config.example.json to config.json and fill in your Azure App Client ID.
    pause
    exit /b 1
)
python __main__.py %*
