@echo off
rem Start the Q-Shield Atlas web app on http://127.0.0.1:8000/ (Windows, Anaconda Prompt).
cd /d "%~dp0"
call conda activate pqc & python -m atlas_web --port 8000
