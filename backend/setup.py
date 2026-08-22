import sys
from cx_Freeze import setup, Executable

build_exe_options = {
    "packages": ["os", "sys", "threading", "pathlib", "tkinter", "pystray", "PIL", "uvicorn", "fastapi", "browser_cookie3"],
    "includes": [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "server",
        "updater",
    ],
    "include_files": ["VERSION"],
    "build_exe": "dist/YTService"
}

base = "Win32GUI" if sys.platform == "win32" else None

setup(
    name="YTService",
    version="1.0.6",
    description="YT Downloader Service",
    options={"build_exe": build_exe_options},
    executables=[Executable("tray.py", base=base, target_name="YTService.exe")]
)
