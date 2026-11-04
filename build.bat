@echo off
cd /d "%~dp0"
echo Building OrbitRx Propagation Monitor...
pip install -r requirements.txt --quiet || exit /b 1
python -m pytest -q || exit /b 1
pyinstaller OrbitRxMonitor.spec --noconfirm || exit /b 1
echo Build complete: dist\OrbitRxMonitor.exe
echo Optional installer: iscc installer\OrbitRxMonitor.iss
