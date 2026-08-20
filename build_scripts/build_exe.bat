@echo off
echo ===========================================
echo Building Standalone YT Downloader Service
echo ===========================================

cd /d "%~dp0\..\backend"
pip install -r requirements.txt

pyinstaller --noconfirm --onedir --windowed ^
  --add-data "VERSION;." ^
  --hidden-import="uvicorn.logging" ^
  --hidden-import="uvicorn.loops" ^
  --hidden-import="uvicorn.loops.auto" ^
  --hidden-import="uvicorn.protocols.http.auto" ^
  --hidden-import="uvicorn.protocols.websockets.auto" ^
  --hidden-import="uvicorn.lifespan.on" ^
  --hidden-import="uvicorn.lifespan.off" ^
  --name "YTService" tray.py

:: Explicitly copy the VERSION file to the dist folder to guarantee it is included
copy /Y VERSION "dist\YTService\VERSION"

echo Done. Please place ffmpeg.exe and ffprobe.exe in backend\dist\YTService\
pause
