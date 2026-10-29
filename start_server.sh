#!/bin/bash
cd /home/aravindh/.gemini/antigravity/scratch/Q-Transplant/backend/backend
exec ../../venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
