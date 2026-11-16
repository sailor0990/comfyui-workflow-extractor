@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set APP_NAME=ComfyUI Workflow Extractor
set VERSION=1.1
set VENV=build_venv
set ZIPNAME=ComfyUI-Workflow-Extractor-v%VERSION%-Windows.zip

echo ============================================
echo  ComfyUI Workflow Extractor v%VERSION% - Windows build
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH. Install Python 3.9+ from python.org first.
  pause
  exit /b 1
)

echo [1/5] Creating virtual environment...
if not exist "%VENV%" (
  python -m venv "%VENV%"
)

echo [2/5] Installing dependencies...
call "%VENV%\Scripts\python.exe" -m pip install --upgrade pip -q
call "%VENV%\Scripts\pip.exe" install -r requirements.txt -q
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)

echo [3/5] Building EXE with PyInstaller...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
call "%VENV%\Scripts\pyinstaller.exe" --noconfirm --clean "ComfyUI Workflow Extractor-windows.spec"
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  pause
  exit /b 1
)

echo [4/5] Verifying output...
if not exist "dist\ComfyUI-Workflow-Extractor.exe" (
  echo [ERROR] dist\ComfyUI-Workflow-Extractor.exe not found.
  pause
  exit /b 1
)

echo [5/5] Packaging ZIP...
if exist "%ZIPNAME%" del /q "%ZIPNAME%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\ComfyUI-Workflow-Extractor.exe' -DestinationPath '%ZIPNAME%' -Force"
if errorlevel 1 (
  echo [WARN] Compress-Archive failed; single EXE is still available in dist\
)

echo.
echo ============================================
echo  Done.
echo    EXE : dist\ComfyUI-Workflow-Extractor.exe
echo    ZIP : %ZIPNAME%
echo.
echo  Note: Windows 10/11 ships WebView2 Runtime.
echo  On older LTSC builds install it from Microsoft:
echo    https://developer.microsoft.com/microsoft-edge/webview2/
echo ============================================
pause
