import os
import sys
import json
import subprocess
import threading
import time
import urllib.request
import logging
import zipfile
import io
import re
import uuid
from urllib.parse import parse_qs, quote, urlsplit
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

APP_DIR = Path(__file__).resolve().parent
APP_DATA = Path(os.getenv('APPDATA', str(Path.home()))) / "YTDownloader"
APP_DATA.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(APP_DATA / "service.log"), 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Silence the /progress polling spam in the console
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/progress" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

CONFIG_FILE = APP_DATA / "config.json"
YTDLP_PATH = APP_DATA / "yt-dlp.exe"
DENO_PATH = APP_DATA / "deno.exe"

DOWNLOAD_TASKS = {}

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def normalise_youtube_url(url: str) -> str:
    """Return a canonical single-video YouTube URL without timestamps/playlists."""
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Enter a valid YouTube video URL.") from exc

    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in YOUTUBE_HOSTS:
        raise HTTPException(status_code=400, detail="Only YouTube video URLs are supported.")

    video_id = ""
    if host.endswith("youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
        video_id = parsed.path.strip("/").split("/")[1] if len(parsed.path.strip("/").split("/")) > 1 else ""

    # YouTube IDs are normally eleven characters, but do not make the backend
    # reject a future valid format solely because of that implementation detail.
    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
        raise HTTPException(status_code=400, detail="The YouTube URL does not contain a video ID.")

    return f"https://www.youtube.com/watch?v={quote(video_id)}"

def get_ffmpeg_dir() -> str:
    candidates = [
        APP_DIR,
        APP_DIR / "dist" / "YTService",
        Path(r"C:\Program Files (x86)\YTDownloader"),
        APP_DATA
    ]
    for p in candidates:
        if (p / "ffmpeg.exe").exists():
            return str(p)
    return str(APP_DIR)

def get_download_path() -> Path:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                saved_path = Path(cfg.get("download_path", ""))
                if saved_path.exists():
                    return saved_path
        except Exception:
            pass
    return Path.home() / "Downloads"

def set_download_path(new_path: str):
    data = {"download_path": new_path}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def ensure_dependencies():
    if not YTDLP_PATH.exists():
        logging.info("Downloading yt-dlp.exe...")
        try:
            urllib.request.urlretrieve("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", str(YTDLP_PATH))
        except Exception as e:
            pass
    else:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run([str(YTDLP_PATH), "-U"], capture_output=True, creationflags=flags)

    if not DENO_PATH.exists():
        try:
            deno_url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
            response = urllib.request.urlopen(deno_url)
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                z.extract("deno.exe", str(APP_DATA))
        except Exception as e:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=ensure_dependencies, daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.youtube.com",
        "https://m.youtube.com",
        "https://music.youtube.com",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/config")
def get_config():
    return {"download_path": str(get_download_path())}

@app.get("/open-folder")
def open_folder():
    path = get_download_path()
    if os.name == 'nt':
        os.startfile(str(path))
    return {"status": "opened"}

@app.get("/formats")
def get_formats(url: str = Query(...)):
    clean_url = normalise_youtube_url(url)

    cmd = [
        str(YTDLP_PATH), "-J", "--no-playlist", 
        "--rm-cache-dir", 
        "--js-runtimes", f"deno:{str(DENO_PATH)}",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        clean_url
    ]

    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=flags)
        data = json.loads(proc.stdout)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="yt-dlp is still starting. Try again in a moment.") from exc
    except subprocess.CalledProcessError as exc:
        logging.error("Format extraction failed for %s: %s", clean_url, exc.stderr)
        raise HTTPException(status_code=400, detail="Could not read formats for this video. Update yt-dlp or try another video.") from exc
    except json.JSONDecodeError as exc:
        logging.exception("yt-dlp returned invalid format JSON for %s", clean_url)
        raise HTTPException(status_code=502, detail="yt-dlp returned an invalid response. Try again shortly.") from exc

    available_formats = []
    seen_resolutions = set()

    for f in data.get("formats", []):
        height = f.get("height")
        vcodec = f.get("vcodec", "none")
        if height and vcodec != "none" and height not in seen_resolutions and f.get("ext") == "mp4":
            seen_resolutions.add(height)
            available_formats.append({
                "format_id": f"{f['format_id']}+bestaudio[ext=m4a]/{f['format_id']}+bestaudio/{f['format_id']}",
                "label": f"{height}p (MP4)",
                "ext": "mp4",
                "height": height
            })

    available_formats.sort(key=lambda x: x["height"], reverse=True)
    available_formats.append({"format_id": "bestaudio", "label": "Audio Only (MP3)", "ext": "mp3", "height": 0})

    return {"title": data.get("title"), "download_path": str(get_download_path()), "formats": available_formats}

def _run_download_process(task_id: str, cmd: list):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    percent_regex = re.compile(r'(\d+(?:\.\d+)?)%')
    speed_regex = re.compile(r'at\s+([0-9.]+[kKMGT]?i?B/s)')
    eta_regex = re.compile(r'ETA\s+([0-9:]+)')

    # Google Video URLs can expire during a longer download. Restarting yt-dlp
    # obtains a fresh URL while it resumes the existing .part file.
    for attempt in range(2):
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                creationflags=flags
            )
        except OSError as exc:
            logging.exception("Could not start download task %s", task_id)
            DOWNLOAD_TASKS[task_id].update(status="error", error=str(exc))
            return

        output_tail = []
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            output_tail.append(line)
            output_tail = output_tail[-20:]

            if "[download] Destination:" in line:
                DOWNLOAD_TASKS[task_id].update(percent=0.0, speed="--", eta="--:--", status="downloading")

            p_match = percent_regex.search(line)
            if p_match:
                DOWNLOAD_TASKS[task_id]["percent"] = float(p_match.group(1))
                if DOWNLOAD_TASKS[task_id]["status"] in {"starting", "retrying"}:
                    DOWNLOAD_TASKS[task_id]["status"] = "downloading"

            s_match = speed_regex.search(line)
            if s_match:
                DOWNLOAD_TASKS[task_id]["speed"] = s_match.group(1)

            e_match = eta_regex.search(line)
            if e_match:
                DOWNLOAD_TASKS[task_id]["eta"] = e_match.group(1)

            if "[Merger]" in line or "Merging" in line or "Fixing" in line:
                DOWNLOAD_TASKS[task_id].update(status="merging", percent=99.0)

        proc.wait()
        if proc.returncode == 0:
            DOWNLOAD_TASKS[task_id].update(status="completed", percent=100.0)
            return

        is_forbidden = any("http error 403" in line.lower() or "403: forbidden" in line.lower() for line in output_tail)
        if attempt == 0 and is_forbidden:
            logging.warning("Download task %s received HTTP 403; refreshing the video URL and resuming.", task_id)
            DOWNLOAD_TASKS[task_id].update(status="retrying", error=None, speed="--", eta="--:--")
            time.sleep(2)
            continue

        error = "\n".join(output_tail[-5:]) or f"yt-dlp exited with code {proc.returncode}."
        logging.error("Download task %s failed: %s", task_id, error)
        DOWNLOAD_TASKS[task_id].update(status="error", error=error)
        return

@app.get("/start-task")
def trigger_download(url: str = Query(...), format_id: str = Query(...)):
    clean_url = normalise_youtube_url(url)
    dest_folder = get_download_path()
    dest_folder.mkdir(parents=True, exist_ok=True)
    task_id = str(uuid.uuid4())
    out_template = str(dest_folder / "%(title).200B [%(id)s].%(ext)s")
    ffmpeg_dir = get_ffmpeg_dir()
    is_audio = format_id == "bestaudio"

    # The format selector comes from this extension's format list. Limiting its
    # characters makes malformed requests fail early while still supporting
    # yt-dlp's ``video+bestaudio/fallback`` selector syntax.
    if not re.fullmatch(r"[A-Za-z0-9._+\-/=\[\]<>*,:]+", format_id):
        raise HTTPException(status_code=400, detail="Invalid download format.")

    cmd = [
        str(YTDLP_PATH),
        "-f", format_id,
        "-o", out_template,
        "-N", "4",
        "--retries", "10",
        "--fragment-retries", "10",
        "--file-access-retries", "3",
        "--force-ipv4",
        "--newline",
        "--no-playlist",
        "--ffmpeg-location", ffmpeg_dir,
        "--js-runtimes", f"deno:{str(DENO_PATH)}",
        "--extractor-args", "youtube:player_client=web_embedded",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        clean_url
    ]

    if is_audio:
        cmd.extend(["--extract-audio", "--audio-format", "mp3"])
    else:
        cmd.extend(["--merge-output-format", "mp4"])

    DOWNLOAD_TASKS[task_id] = {
        "status": "starting",
        "percent": 0.0,
        "speed": "--",
        "eta": "--:--",
        "error": None
    }

    threading.Thread(target=_run_download_process, args=(task_id, cmd), daemon=True).start()
    return {"task_id": task_id, "destination": str(dest_folder)}

@app.get("/progress")
def get_progress(task_id: str = Query(...)):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
