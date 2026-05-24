@echo off
title ChandramaCAD
echo Starting ChandramaCAD...
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe main.py
) else if exist "C:\Users\chipl\Documents\Chandrama Navigation\Hot Wire\CMASHotWire\.venv\Scripts\python.exe" (
    "C:\Users\chipl\Documents\Chandrama Navigation\Hot Wire\CMASHotWire\.venv\Scripts\python.exe" main.py
) else (
    python main.py
)
pause
