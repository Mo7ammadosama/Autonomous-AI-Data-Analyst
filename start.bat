@echo off
echo Starting DataMind AI Platform...

echo.
echo [1/2] Starting Backend (FastAPI on port 8001)...
start "DataMind Backend" cmd /k "cd /d "%~dp0backend" && venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8001 --reload"

timeout /t 3 /nobreak > nul

echo [2/2] Starting Frontend (Next.js on port 3000)...
start "DataMind Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ✓ Backend:  http://localhost:8001
echo ✓ Frontend: http://localhost:3000
echo ✓ API Docs: http://localhost:8001/docs
echo.
pause
