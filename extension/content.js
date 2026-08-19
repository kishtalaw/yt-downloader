const BACKEND = "http://127.0.0.1:8000";

function createProgressCard(title) {
  let card = document.getElementById("yt-idm-card");
  if (card) card.remove();

  card = document.createElement("div");
  card.id = "yt-idm-card";
  card.innerHTML = `
    <div class="idm-header">
      <span class="idm-title"></span>
      <button class="idm-close-btn" id="idm-close">✕</button>
    </div>
    <div class="idm-status-text" id="idm-status">Starting download...</div>
    <div class="idm-bar-container">
      <div class="idm-bar" id="idm-bar" style="width: 0%;"></div>
    </div>
    <div class="idm-stats">
      <span id="idm-percent">0%</span>
      <span id="idm-speed">--</span>
      <span id="idm-eta">--:--</span>
    </div>
    <button class="idm-folder-btn" id="idm-open-folder" style="display:none;">📁 Open Downloads Folder</button>
  `;

  const titleElement = card.querySelector(".idm-title");
  titleElement.title = title;
  titleElement.textContent = title;
  document.body.appendChild(card);

  document.getElementById("idm-close").onclick = () => card.remove();
  document.getElementById("idm-open-folder").onclick = () => fetch(`${BACKEND}/open-folder`);

  return card;
}

function pollProgress(taskId, card) {
  const bar = document.getElementById("idm-bar");
  const status = document.getElementById("idm-status");
  const percentText = document.getElementById("idm-percent");
  const speedText = document.getElementById("idm-speed");
  const etaText = document.getElementById("idm-eta");
  const openFolderBtn = document.getElementById("idm-open-folder");

  const interval = setInterval(async () => {
    try {
      const res = await fetch(`${BACKEND}/progress?task_id=${taskId}`);
      if (!res.ok) return;
      const data = await res.json();

      bar.style.animation = "none";
      bar.style.background = "#cc0000";
      const pct = Math.min(100, Math.max(0, data.percent || 0));
      bar.style.width = `${pct}%`;
      percentText.innerText = `${pct.toFixed(1)}%`;
      speedText.innerText = data.speed || "--";
      etaText.innerText = `ETA: ${data.eta || "--:--"}`;

      if (data.status === "downloading") {
        status.innerText = "Downloading...";
      } else if (data.status === "retrying") {
        status.innerText = "Refreshing the video link and resuming...";
      } else if (data.status === "merging") {
        status.innerText = "Merging audio and video (MP4)...";
      } else if (data.status === "completed") {
        clearInterval(interval);
        bar.style.width = "100%";
        bar.style.background = "#2ba640";
        status.innerText = "✓ Download Complete!";
        percentText.innerText = "100%";
        speedText.innerText = "";
        etaText.innerText = "";
        openFolderBtn.style.display = "block";
      } else if (data.status === "error") {
        clearInterval(interval);
        status.innerText = `❌ Download failed: ${data.error || "Check the service log."}`;
        status.style.color = "#ff4e4e";
        bar.style.background = "#ff4e4e";
      }
    } catch (e) {
      clearInterval(interval);
    }
  }, 600);
}

function injectFloatingButton() {
  if (!window.location.pathname.startsWith("/watch")) return;

  // FIX: If the button already exists, just clear its cached menu.
  // This forces it to scan for new formats using the new video URL.
  let existingContainer = document.getElementById("yt-floating-bar");
  if (existingContainer) {
    let existingMenu = existingContainer.querySelector(".yt-dl-menu");
    if (existingMenu) {
      existingMenu.innerHTML = ""; // Wipe the old video's formats
    }
    return;
  }

  const player = document.querySelector("#movie_player");
  if (!player) {
    setTimeout(injectFloatingButton, 500);
    return;
  }

  const container = document.createElement("div");
  container.id = "yt-floating-bar";

  const btn = document.createElement("button");
  btn.className = "yt-dl-btn";
  btn.innerHTML = `<span>⬇</span> Download`;

  const menu = document.createElement("div");
  menu.className = "yt-dl-menu";

  btn.onclick = async (e) => {
    e.stopPropagation();
    menu.classList.toggle("show");

    if (menu.classList.contains("show") && menu.children.length === 0) {
      menu.innerHTML = "<div class='yt-dl-status'>Scanning formats...</div>";
      try {
        const videoUrl = window.location.href;
        const res = await fetch(`${BACKEND}/formats?url=${encodeURIComponent(videoUrl)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Could not scan this video.");
        menu.innerHTML = "";

        const header = document.createElement("div");
        header.className = "yt-dl-path-info";
        header.innerText = `Folder: ${data.download_path.split('\\').pop()}`;
        menu.appendChild(header);

        data.formats.forEach((fmt) => {
          const item = document.createElement("button");
          item.className = "yt-dl-item";
          item.innerText = fmt.label;
          item.onclick = async () => {
            try {
              menu.classList.remove("show");
              const dlRes = await fetch(`${BACKEND}/start-task?url=${encodeURIComponent(videoUrl)}&format_id=${encodeURIComponent(fmt.format_id)}&container=${encodeURIComponent(fmt.ext)}`);
              const dlData = await dlRes.json();
              if (!dlRes.ok) throw new Error(dlData.detail || "Could not start the download.");

              const card = createProgressCard(data.title || "YouTube Video");
              pollProgress(dlData.task_id, card);
            } catch (err) {
              menu.classList.add("show");
              menu.innerHTML = "";
              const message = document.createElement("div");
              message.className = "yt-dl-status error";
              message.textContent = err.message || "Could not start the download.";
              menu.appendChild(message);
            }
          };
          menu.appendChild(item);
        });
      } catch (err) {
        menu.innerHTML = "";
        const message = document.createElement("div");
        message.className = "yt-dl-status error";
        message.textContent = err.message || "Service is unavailable.";
        menu.appendChild(message);
      }
    }
  };

  document.addEventListener("click", () => menu.classList.remove("show"));
  container.appendChild(btn);
  container.appendChild(menu);
  player.appendChild(container);
}

// Re-run the injection/cache-clearing logic every time the user clicks a new video
window.addEventListener("yt-navigate-finish", injectFloatingButton);
injectFloatingButton();
