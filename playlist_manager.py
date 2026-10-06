"""
Playlist Manager for M3U Streams
Handles fetching, parsing, caching, and querying channels from the remote M3U playlist.
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Any

DEFAULT_PLAYLIST_URL = "https://raw.githubusercontent.com/reyad27s/Playlist/refs/heads/main/playlist.m3u"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlist_cache.json")
RAW_M3U_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlist_raw.m3u")
DEFAULT_UA = "Mozilla/5.0 (Linux; Android 14; 22071219AI Build/UP1A.231005.007) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.7871.181 Mobile Safari/537.36"
DEFAULT_REFERER = "https://hridoytv.pages.dev/"
DEFAULT_ORIGIN = "https://hridoytv.pages.dev"


class Channel:
    def __init__(self, cid: int, name: str, url: str, group: str = "General", 
                 logo: str = "", tvg_id: str = "", headers: Optional[Dict[str, str]] = None,
                 raw_info: str = ""):
        self.cid = cid
        self.name = name
        self.url = url
        self.group = group or "General"
        self.logo = logo
        self.tvg_id = tvg_id
        self.raw_info = raw_info
        self.headers = headers or {}
        # Ensure default fallback headers if not present
        if "User-Agent" not in self.headers:
            self.headers["User-Agent"] = DEFAULT_UA
        if "Referer" not in self.headers:
            self.headers["Referer"] = DEFAULT_REFERER
        if "Origin" not in self.headers:
            self.headers["Origin"] = DEFAULT_ORIGIN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.cid,
            "name": self.name,
            "url": self.url,
            "group": self.group,
            "logo": self.logo,
            "tvg_id": self.tvg_id,
            "headers": self.headers
        }


class PlaylistManager:
    def __init__(self, source_url: str = DEFAULT_PLAYLIST_URL, cache_ttl_seconds: int = 3600):
        self.source_url = source_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.channels: List[Channel] = []
        self.channel_map: Dict[int, Channel] = {}
        self.groups: List[str] = []
        self.last_fetch_time: float = 0.0

    def load_playlist(self, force_refresh: bool = False) -> List[Channel]:
        """Load playlist from remote URL or local cache."""
        now = time.time()
        # Check if memory cache is valid
        if self.channels and not force_refresh and (now - self.last_fetch_time < self.cache_ttl_seconds):
            return self.channels

        # Try to download from source URL
        raw_text = None
        try:
            print(f"[PlaylistManager] Fetching playlist from {self.source_url} ...")
            req = urllib.request.Request(self.source_url, headers={"User-Agent": DEFAULT_UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8", errors="ignore")
            # Save raw file cache
            try:
                with open(RAW_M3U_CACHE, "w", encoding="utf-8") as f:
                    f.write(raw_text)
            except Exception:
                pass
            print(f"[PlaylistManager] Downloaded {len(raw_text)} bytes successfully.")
        except Exception as e:
            print(f"[PlaylistManager] Failed to fetch remote playlist: {e}")
            if os.path.exists(RAW_M3U_CACHE):
                print(f"[PlaylistManager] Loading from local raw cache: {RAW_M3U_CACHE}")
                try:
                    with open(RAW_M3U_CACHE, "r", encoding="utf-8") as f:
                        raw_text = f.read()
                except Exception as ex:
                    print(f"[PlaylistManager] Cache read error: {ex}")

        if not raw_text:
            if self.channels:
                return self.channels
            raise RuntimeError("Unable to load playlist from both remote and cache.")

        self.channels = self._parse_m3u(raw_text)
        self.channel_map = {ch.cid: ch for ch in self.channels}
        
        # Calculate distinct groups
        group_set = set()
        for ch in self.channels:
            if ch.group:
                group_set.add(ch.group)
        self.groups = sorted(list(group_set))
        self.last_fetch_time = time.time()
        
        print(f"[PlaylistManager] Successfully loaded {len(self.channels)} channels across {len(self.groups)} categories.")
        return self.channels

    def _parse_m3u(self, content: str) -> List[Channel]:
        """Parses M3U file supporting #EXTINF, #EXTVLCOPT headers and URLs."""
        lines = content.splitlines()
        channels: List[Channel] = []
        
        current_data: Optional[Dict[str, Any]] = None
        channel_id_counter = 1

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("#EXTINF:"):
                # Save previous channel if completed
                if current_data and current_data.get("url"):
                    ch = Channel(
                        cid=channel_id_counter,
                        name=current_data.get("name", f"Channel {channel_id_counter}"),
                        url=current_data["url"],
                        group=current_data.get("group", "General"),
                        logo=current_data.get("logo", ""),
                        tvg_id=current_data.get("tvg_id", ""),
                        headers=current_data.get("headers", {}),
                        raw_info=current_data.get("raw_info", "")
                    )
                    channels.append(ch)
                    channel_id_counter += 1

                # Begin new channel
                current_data = {
                    "raw_info": line,
                    "headers": {},
                    "name": "",
                    "group": "General",
                    "logo": "",
                    "tvg_id": ""
                }

                # Extract channel name (after last comma)
                comma_idx = line.rfind(",")
                if comma_idx != -1:
                    current_data["name"] = line[comma_idx + 1:].strip()

                # Extract attributes
                m_group = re.search(r'group-title="([^"]*)"', line)
                if m_group:
                    current_data["group"] = m_group.group(1).strip()

                m_logo = re.search(r'tvg-logo="([^"]*)"', line)
                if m_logo:
                    current_data["logo"] = m_logo.group(1).strip()

                m_id = re.search(r'tvg-id="([^"]*)"', line)
                if m_id:
                    current_data["tvg_id"] = m_id.group(1).strip()

            elif line.startswith("#EXTVLCOPT:"):
                if current_data is not None:
                    opt = line[11:].strip()
                    if opt.startswith("http-user-agent="):
                        current_data["headers"]["User-Agent"] = opt.split("=", 1)[1]
                    elif opt.startswith("http-referrer="):
                        current_data["headers"]["Referer"] = opt.split("=", 1)[1]
                    elif opt.startswith("http-origin="):
                        current_data["headers"]["Origin"] = opt.split("=", 1)[1]

            elif not line.startswith("#"):
                if current_data is not None:
                    if not current_data.get("url"):
                        current_data["url"] = line

        # Flush last channel
        if current_data and current_data.get("url"):
            ch = Channel(
                cid=channel_id_counter,
                name=current_data.get("name", f"Channel {channel_id_counter}"),
                url=current_data["url"],
                group=current_data.get("group", "General"),
                logo=current_data.get("logo", ""),
                tvg_id=current_data.get("tvg_id", ""),
                headers=current_data.get("headers", {}),
                raw_info=current_data.get("raw_info", "")
            )
            channels.append(ch)

        return channels

    def get_channel(self, cid: int) -> Optional[Channel]:
        if not self.channels:
            self.load_playlist()
        return self.channel_map.get(cid)

    def search_channels(self, query: str = "", group: str = "") -> List[Channel]:
        if not self.channels:
            self.load_playlist()
        results = self.channels
        if group and group != "All":
            results = [ch for ch in results if ch.group.lower() == group.lower()]
        if query:
            q = query.lower()
            results = [ch for ch in results if q in ch.name.lower() or q in ch.group.lower()]
        return results

    def generate_proxied_m3u(self, base_server_url: str, filter_group: str = "") -> str:
        """
        Generates a standard M3U playlist pointing to this local proxy server.
        Every stream URL becomes: {base_server_url}/channel/{id}.m3u8
        """
        if not self.channels:
            self.load_playlist()

        channels_to_export = self.channels
        if filter_group and filter_group != "All":
            channels_to_export = [ch for ch in channels_to_export if ch.group.lower() == filter_group.lower()]

        lines = ["#EXTM3U"]
        for ch in channels_to_export:
            # Format EXTINF with tvg tags
            logo_attr = f' tvg-logo="{ch.logo}"' if ch.logo else ""
            id_attr = f' tvg-id="{ch.tvg_id}"' if ch.tvg_id else ""
            group_attr = f' group-title="{ch.group}"' if ch.group else ""
            extinf = f'#EXTINF:-1{id_attr}{logo_attr}{group_attr},{ch.name}'
            
            stream_url = f"{base_server_url.rstrip('/')}/channel/{ch.cid}.m3u8"
            lines.append(extinf)
            lines.append(stream_url)

        return "\n".join(lines) + "\n"
