let allChannels = [];
let selectedGroup = "All";
let hlsInstance = null;
let currentChannel = null;

const videoPlayer = document.getElementById("videoPlayer");
const playerPlaceholder = document.getElementById("playerPlaceholder");
const channelsGrid = document.getElementById("channelsGrid");
const searchInput = document.getElementById("searchInput");
const groupsFilterContainer = document.getElementById("groupsFilterContainer");
const channelCountBadge = document.getElementById("channelCountBadge");
const playlistUrlText = document.getElementById("playlistUrlText");
const copyM3uBtn = document.getElementById("copyM3uBtn");
const copyStreamUrlBtn = document.getElementById("copyStreamUrlBtn");
const vlcLinkBtn = document.getElementById("vlcLinkBtn");
const nowPlayingCard = document.getElementById("nowPlayingCard");
const nowPlayingLogo = document.getElementById("nowPlayingLogo");
const nowPlayingTitle = document.getElementById("nowPlayingTitle");
const nowPlayingGroup = document.getElementById("nowPlayingGroup");
const nowPlayingStatus = document.getElementById("nowPlayingStatus");
const toast = document.getElementById("toast");

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  const m3uUrl = `${window.location.origin}/playlist.m3u`;
  playlistUrlText.innerText = m3uUrl;

  loadGroups();
  loadChannels();

  // Search filter
  searchInput.addEventListener("input", () => {
    filterAndRenderChannels();
  });

  // Copy M3U button
  copyM3uBtn.addEventListener("click", () => {
    copyToClipboard(m3uUrl, "Full M3U Playlist URL copied!");
  });

  // Copy Stream URL button
  copyStreamUrlBtn.addEventListener("click", () => {
    if (currentChannel) {
      copyToClipboard(currentChannel.stream_url, `Stream URL for "${currentChannel.name}" copied!`);
    }
  });
});

function showToast(message) {
  toast.innerText = message;
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
  }, 2500);
}

function copyToClipboard(text, successMsg) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(successMsg);
  }).catch(() => {
    // Fallback
    const input = document.createElement("input");
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    document.body.removeChild(input);
    showToast(successMsg);
  });
}

async function loadGroups() {
  try {
    const res = await fetch("/api/groups");
    const groups = await res.json();
    renderGroupPills(groups);
  } catch (err) {
    console.error("Failed to load groups:", err);
  }
}

function renderGroupPills(groups) {
  groupsFilterContainer.innerHTML = "";
  groups.forEach((grp) => {
    const btn = document.createElement("button");
    btn.className = `pill-btn ${grp === selectedGroup ? "active" : ""}`;
    btn.innerText = grp;
    btn.addEventListener("click", () => {
      selectedGroup = grp;
      document.querySelectorAll(".pill-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      filterAndRenderChannels();
    });
    groupsFilterContainer.appendChild(btn);
  });
}

async function loadChannels() {
  try {
    const res = await fetch("/api/channels");
    const data = await res.json();
    allChannels = data.channels || [];
    channelCountBadge.innerText = `${allChannels.length} Channels`;
    filterAndRenderChannels();
  } catch (err) {
    console.error("Failed to load channels:", err);
    channelsGrid.innerHTML = `<div class="empty-state"><p>Error connecting to backend server.</p></div>`;
  }
}

function filterAndRenderChannels() {
  const query = searchInput.value.trim().toLowerCase();
  const filtered = allChannels.filter((ch) => {
    const matchGroup = selectedGroup === "All" || ch.group.toLowerCase() === selectedGroup.toLowerCase();
    const matchQuery = !query || ch.name.toLowerCase().includes(query) || ch.group.toLowerCase().includes(query);
    return matchGroup && matchQuery;
  });

  if (filtered.length === 0) {
    channelsGrid.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        <p>No channels found matching "${searchInput.value}"</p>
      </div>`;
    return;
  }

  channelsGrid.innerHTML = "";
  filtered.forEach((ch) => {
    const card = document.createElement("div");
    card.className = `channel-card ${currentChannel && currentChannel.id === ch.id ? "active" : ""}`;
    
    const fallbackLogo = `data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='44' height='44' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2'><rect x='2' y='7' width='20' height='15' rx='2' ry='2'></rect><polyline points='17 2 12 7 7 2'></polyline></svg>`;
    const logoSrc = ch.logo || fallbackLogo;

    card.innerHTML = `
      <div class="card-top">
        <img class="card-logo" src="${logoSrc}" alt="${ch.name}" loading="lazy" onerror="this.src='${fallbackLogo}'">
        <div class="card-info">
          <div class="card-title" title="${ch.name}">${ch.name}</div>
          <div class="card-group">${ch.group}</div>
        </div>
      </div>
      <div class="card-footer">
        <span class="card-channel-id">CH #${ch.id}</span>
        <span class="play-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          Play
        </span>
      </div>
    `;

    card.addEventListener("click", () => {
      playChannel(ch);
    });

    channelsGrid.appendChild(card);
  });
}

function playChannel(channel) {
  currentChannel = channel;

  // Highlight active card
  document.querySelectorAll(".channel-card").forEach((c) => c.classList.remove("active"));
  const cards = document.querySelectorAll(".channel-card");
  // Update Now Playing UI
  playerPlaceholder.style.display = "none";
  nowPlayingCard.style.display = "flex";
  nowPlayingTitle.innerText = channel.name;
  nowPlayingGroup.innerText = channel.group;
  nowPlayingStatus.innerText = "Buffering...";
  nowPlayingLogo.src = channel.logo || "";

  // Set VLC link (using vlc:// protocol)
  vlcLinkBtn.href = `vlc://${channel.stream_url}`;

  // Destroy previous HLS instance
  if (hlsInstance) {
    hlsInstance.destroy();
    hlsInstance = null;
  }

  const streamUrl = channel.stream_url;
  console.log(`[Player] Loading stream: ${streamUrl}`);

  if (Hls.isSupported()) {
    hlsInstance = new Hls({
      enableWorker: true,
      lowLatencyMode: true,
      backBufferLength: 60,
      manifestLoadingTimeOut: 15000,
      levelLoadingTimeOut: 15000,
    });

    hlsInstance.loadSource(streamUrl);
    hlsInstance.attachMedia(videoPlayer);

    hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
      nowPlayingStatus.innerText = "Live";
      videoPlayer.play().catch((e) => {
        console.warn("Autoplay was prevented by browser:", e);
        nowPlayingStatus.innerText = "Click play";
      });
    });

    hlsInstance.on(Hls.Events.ERROR, (event, data) => {
      console.warn("HLS Event Error:", data);
      if (data.fatal) {
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            nowPlayingStatus.innerText = "Network Retry...";
            hlsInstance.startLoad();
            break;
          case Hls.ErrorTypes.MEDIA_ERROR:
            nowPlayingStatus.innerText = "Recovering...";
            hlsInstance.recoverMediaError();
            break;
          default:
            nowPlayingStatus.innerText = "Stream Offline / Error";
            hlsInstance.destroy();
            break;
        }
      }
    });
  } else if (videoPlayer.canPlayType("application/vnd.apple.mpegurl")) {
    // Native Safari / iOS HLS
    videoPlayer.src = streamUrl;
    videoPlayer.addEventListener("loadedmetadata", () => {
      nowPlayingStatus.innerText = "Live";
      videoPlayer.play();
    });
  } else {
    nowPlayingStatus.innerText = "HLS not supported in browser";
    alert("HLS playback is not natively supported in this browser. Please use Chrome/Firefox/Edge or VLC.");
  }
}
