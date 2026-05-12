@echo off
REM Build LosslessBob for Windows
REM Run from the project root: tools\build_windows.bat

echo Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building executable...
pyinstaller losslessbob.spec

echo.
echo Build complete: dist\LosslessBob\LosslessBob.exe
echo.
echo Post-build: create data\ folder next to the .exe if it does not exist.
if not exist dist\LosslessBob\data mkdir dist\LosslessBob\data

pause
