@echo off
echo ===========================================
echo Building Standalone YT Downloader Service
echo ===========================================

cd /d "%~dp0\..\backend"
pip install -r requirements.txt

pyinstaller --noconfirm --onedir --windowed ^
  --hidden-import="uvicorn.logging" ^
  --hidden-import="uvicorn.loops" ^
  --hidden-import="uvicorn.loops.auto" ^
  --hidden-import="uvicorn.protocols.http.auto" ^
  --hidden-import="uvicorn.protocols.websockets.auto" ^
  --hidden-import="uvicorn.lifespan.on" ^
  --hidden-import="uvicorn.lifespan.off" ^
  --name "YTService" tray.py

echo Done. Please place ffmpeg.exe and ffprobe.exe in backend\dist\YTService\
pause