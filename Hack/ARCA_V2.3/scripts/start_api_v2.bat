@echo off
setlocal
set "PROJECT_DIR=%~dp0.."
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo ERROR: ARCA V2 virtual environment is missing: "%PYTHON_EXE%"
  exit /b 1
)
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 (
  echo ERROR: Port 8000 is already occupied. ARCA V2 API was not started.
  exit /b 1
)
pushd "%PROJECT_DIR%"
echo ARCA V2 API: http://127.0.0.1:8000
echo OpenAPI docs: http://127.0.0.1:8000/docs
"%PYTHON_EXE%" -m uvicorn backend.main:app --app-dir "%PROJECT_DIR%" --host 127.0.0.1 --port 8000
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
