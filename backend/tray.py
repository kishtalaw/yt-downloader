import os
import sys
import threading
from pathlib import Path

# =========================================================================
# 1. CRITICAL FIX: PyInstaller --windowed sets sys.stdout/stderr to None. 
# Uvicorn assumes a console exists and crashes instantly when it tries to print.
# We redirect all "prints" and internal logs to a physical file here.
# =========================================================================
APP_DATA = Path(os.getenv('APPDATA', 'C:\\')) / "YTDownloader"
APP_DATA.mkdir(parents=True, exist_ok=True)
log_stream = open(APP_DATA / "service_console.log", "a", encoding="utf-8")
sys.stdout = log_stream
sys.stderr = log_stream

# Import UI and Server components AFTER fixing the output stream
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
import pystray
from PIL import Image, ImageDraw
import uvicorn
import server
import updater

def create_tray_icon():
    img = Image.new('RGB', (64, 64), color=(20, 20, 20))
    d = ImageDraw.Draw(img)
    d.polygon([(32, 50), (16, 20), (48, 20)], fill=(255, 0, 0))
    return img

def open_download_folder(icon, item):
    path = server.get_download_path()
    os.startfile(str(path))

def _tk_folder_picker():
    """Runs the Tkinter folder picker safely in an isolated thread."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(initialdir=str(server.get_download_path()), title="Select YouTube Downloads Directory")
    if selected:
        server.set_download_path(selected)
    root.destroy()

def choose_download_folder(icon, item):
    # =========================================================================
    # 2. CRITICAL FIX: Pystray runs in the main thread. Tkinter blocks it.
    # Offloading this to a separate thread prevents the window from freezing.
    # =========================================================================
    threading.Thread(target=_tk_folder_picker, daemon=True).start()

def manual_update_ytdlp(icon, item):
    threading.Thread(target=server.ensure_and_update_ytdlp, daemon=True).start()

def _tk_check_app_update():
    """Runs the update check from a Tkinter dialog thread."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    current_version = updater._read_local_version()
    msg = f"YT Downloader\nCurrent Version: {current_version}\n\nWould you like to check for app updates?"

    if messagebox.askyesno("About / Update", msg, parent=root):
        # We need to temporarily increase the timeout for manual checks since the user is waiting
        print("Checking for app updates manually...")
        if updater.check_for_update_and_install():
            messagebox.showinfo("Updating", "An update was found and is being installed. The application will now close.", parent=root)
            root.destroy()
            os._exit(0)
        else:
            messagebox.showinfo("Update", "You are already on the latest version, or no update could be found.", parent=root)

    root.destroy()

def check_app_update(icon, item):
    threading.Thread(target=_tk_check_app_update, daemon=True).start()

def quit_app(icon, item):
    icon.stop()
    os._exit(0)

def run_api_server():
    print("Starting Uvicorn Server on http://127.0.0.1:8000 ...") # Safely logs to service_console.log
    uvicorn.run(server.app, host="127.0.0.1", port=8000, log_level="info")

if __name__ == "__main__":
    # Check for app updates BEFORE starting the server or tray icon.
    # If an update is launched, exit immediately to release file locks
    # so the silent installer can overwrite the executable.
    try:
        print("Checking for app updates...")
        if updater.check_for_update_and_install():
            print("Update installer launched. Exiting current process.")
            sys.exit(0)
    except Exception as e:
        print(f"Auto-updater failed: {e}")

    server_thread = threading.Thread(target=run_api_server, daemon=True)
    server_thread.start()

    menu = pystray.Menu(
        pystray.MenuItem("Select Download Folder", choose_download_folder),
        pystray.MenuItem("Open Downloads Folder", open_download_folder),
        pystray.MenuItem("Update yt-dlp Engine", manual_update_ytdlp),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("About / Update App", check_app_update),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", quit_app)
    )

    tray = pystray.Icon("YTDownloader", create_tray_icon(), "YT Floating Downloader", menu)
    tray.run()