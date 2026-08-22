@echo off
echo ===========================================
echo Building Standalone YT Downloader Service
echo ===========================================

cd /d "%~dp0\..\backend"
pip install -r requirements.txt

python setup.py build

:: Explicitly copy the VERSION file to the dist folder to guarantee it is included
copy /Y VERSION "dist\YTService\VERSION"

echo Done. Please place ffmpeg.exe and ffprobe.exe in backend\dist\YTService\
