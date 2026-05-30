@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean trunow_portal.spec

echo.
echo Build complete. Check the dist\TRUNOWPortal folder.
endlocal
