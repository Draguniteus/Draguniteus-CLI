@echo off
set PYTHONPATH=%~dp0src
set ANTHROPIC_API_KEY=%ANTHROPIC_API_KEY%
python -m draguniteus %*