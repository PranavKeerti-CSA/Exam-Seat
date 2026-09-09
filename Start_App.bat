@echo off
echo ======================================
echo  Starting Exam Seating Allocator 
echo ======================================

:: Navigate to the project directory
cd "%~dp0examhall---school-exam-seating-allocator"

:: Kill processes on port 8000 and 5174 (optional but good practice)
FOR /F "tokens=5" %%T IN ('netstat -a -n -o ^| findstr :8000') DO (
    TaskKill.exe /PID %%T /F 2>NUL
)
FOR /F "tokens=5" %%T IN ('netstat -a -n -o ^| findstr :5174') DO (
    TaskKill.exe /PID %%T /F 2>NUL
)

echo -^> Starting Backend Server...
cd backend
:: Open backend in a new window so we don't block
start "Backend Server" cmd /k "..\venv\Scripts\activate && python run.py"
cd ..

echo -^> Starting Frontend Server...
:: Open frontend in a new window
start "Frontend Server" cmd /k "npm run dev -- --port 5174"

echo -^> Waiting for servers to initialize...
timeout /t 3 /nobreak > NUL

echo -^> Opening browser...
start http://localhost:5174

echo Done! You can close this small launcher window.
