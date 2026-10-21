@echo off
setlocal
set "PROJECT_DIR=%~dp0.."
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo ERROR: V1 virtual environment is missing: "%PYTHON_EXE%"
  exit /b 1
)
netstat -ano | findstr /R /C:":8501 .*LISTENING" >nul
if not errorlevel 1 (
  echo ERROR: Port 8501 is already occupied. V1 was not started.
  exit /b 1
)
pushd "%PROJECT_DIR%"
set "ARCA_MODE=mock"
echo ARCA V1: http://localhost:8501
"%PYTHON_EXE%" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
