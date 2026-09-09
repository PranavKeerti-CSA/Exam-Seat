#!/bin/bash

echo "======================================"
echo " Starting Exam Seating Allocator "
echo "======================================"

# Navigate to the correct directory
cd "$(dirname "$0")/examhall---school-exam-seating-allocator"

# Kill any existing processes on the ports to prevent address in use errors
lsof -ti :8000 | xargs kill -9 2>/dev/null
lsof -ti :5174 | xargs kill -9 2>/dev/null
lsof -ti :5173 | xargs kill -9 2>/dev/null

# Start backend
echo "-> Starting Backend Server on port 8000..."
source venv/bin/activate
cd backend
python3 run.py &
BACKEND_PID=$!
cd ..

# Start frontend
echo "-> Starting Frontend Server on port 5174..."
npm run dev -- --port 5174 &
FRONTEND_PID=$!

echo "-> Servers started successfully. Opening browser..."
sleep 3
open http://localhost:5174

echo ""
echo "Press [CTRL+C] in this window to stop the servers."

# Wait for background processes to keep terminal open
wait $FRONTEND_PID $BACKEND_PID
