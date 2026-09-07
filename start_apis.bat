@echo off
REM START ALL API ENDPOINTS - Windows Batch Script
REM =============================================

echo 🚀 Starting Kenya Audit Transparency APIs...
echo ==============================================

REM Check if we're in the right directory
if not exist "start_all_apis.py" (
    echo ❌ Error: Please run this script from the project root directory
    pause
    exit /b 1
)

echo.
echo 🔧 Starting Modernized Data-Driven API (Port 8004)...
start /b cmd /c "cd apis && python modernized_api.py"

REM Wait a moment  
timeout /t 2 /nobreak >nul

echo 🔧 Starting Main Backend API (Port 8000)...
start /b cmd /c "cd backend && python main.py"

REM Wait for initialization
timeout /t 3 /nobreak >nul

echo.
echo 🎉 ALL APIs STARTED!
echo ===================
echo 🔧 Modernized Data-Driven API:    http://localhost:8004
echo 🏛️ Main Backend API:              http://localhost:8000
echo.
echo 🧪 Test with Postman collection or visit URLs above
echo ⚠️  Close this window or press Ctrl+C to stop monitoring
echo.
echo 👀 Monitoring APIs... 

REM Keep window open for monitoring
:monitor
timeout /t 5 /nobreak >nul
goto monitor
