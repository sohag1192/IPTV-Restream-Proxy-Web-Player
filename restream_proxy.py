"""
Restream Proxy Server
High-performance, zero-dependency HTTP server that:
- Serves proxied M3U playlists
- Rewrites HLS manifests (master and variant playlists)
- Proxies video TS segments with required headers (User-Agent, Referer, Origin)
- Provides Web Player UI and JSON REST API
- Supports CORS for in-browser playback
"""

import os
import sys
import ssl
import json
import socket
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional, Dict

from playlist_manager import PlaylistManager, Channel

# Disable strict SSL verification for upstream proxying if needed
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads for concurrent streaming."""
    daemon_threads = True
    allow_reuse_address = True


class RestreamHandler(BaseHTTPRequestHandler):
    playlist_mgr: PlaylistManager = None
    server_host: str = "localhost"
    server_port: int = 8080

    # Suppress default log messages to keep terminal clean; print custom events
    def log_message(self, format, *args):
        # Only log non-200 or important requests
        status_code = args[1] if len(args) > 1 else ""
        if status_code not in ("200", "206"):
            sys.stderr.write(f"[{self.log_date_time_string()}] {self.address_string()} - {format % args}\n")

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Web UI Root
        if path == "/" or path == "/index.html" or path == "/player":
            self.serve_static_file("index.html", "text/html; charset=utf-8")
            return

        # 2. Static files
        if path.startswith("/static/"):
            filename = path[8:]
            content_type = "text/plain"
            if filename.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif filename.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif filename.endswith(".html"):
                content_type = "text/html; charset=utf-8"
            self.serve_static_file(filename, content_type)
            return

        # 3. Channels API: /api/channels
        if path == "/api/channels":
            self.handle_api_channels(query)
            return

        # 4. Groups API: /api/groups
        if path == "/api/groups":
            self.handle_api_groups()
            return

        # 5. Proxied M3U Playlist: /playlist.m3u
        if path == "/playlist.m3u" or path == "/channels.m3u":
            self.handle_proxied_playlist(query)
            return

        # 6. Channel Stream M3U8: /channel/<cid>.m3u8
        if path.startswith("/channel/") and path.endswith(".m3u8"):
            cid_str = path[9:-5]
            try:
                cid = int(cid_str)
                self.handle_channel_stream(cid)
            except ValueError:
                self.send_error(400, "Invalid channel ID")
            return

        # 7. Sub-manifest Proxy: /proxy/m3u8
        if path == "/proxy/m3u8":
            self.handle_proxy_m3u8(query)
            return

        # 8. TS Segment Proxy: /proxy/ts
        if path == "/proxy/ts":
            self.handle_proxy_ts(query)
            return

        # 9. Key Proxy: /proxy/key
        if path == "/proxy/key":
            self.handle_proxy_key(query)
            return

        # 10. Health check
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","service":"restream_proxy"}')
            return

        self.send_error(404, "Not Found")

    # -------------------------------------------------------------
    # Handlers
    # -------------------------------------------------------------
    def get_base_url(self) -> str:
        host_header = self.headers.get("Host")
        if host_header:
            return f"http://{host_header}"
        return f"http://{self.server_host}:{self.server_port}"

    def serve_static_file(self, filename: str, content_type: str):
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        safe_path = os.path.abspath(os.path.join(static_dir, filename))
        if not safe_path.startswith(static_dir) or not os.path.isfile(safe_path):
            self.send_error(404, "File Not Found")
            return

        try:
            with open(safe_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def handle_api_channels(self, query: Dict):
        group_filter = query.get("group", [""])[0]
        search_filter = query.get("q", [""])[0]
        channels = self.playlist_mgr.search_channels(query=search_filter, group=group_filter)
        
        base_url = self.get_base_url()
        data = []
        for ch in channels:
            ch_data = ch.to_dict()
            ch_data["stream_url"] = f"{base_url}/channel/{ch.cid}.m3u8"
            data.append(ch_data)

        payload = json.dumps({"total": len(data), "channels": data}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def handle_api_groups(self):
        groups = ["All"] + self.playlist_mgr.groups
        payload = json.dumps(groups).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def handle_proxied_playlist(self, query: Dict):
        group_filter = query.get("group", [""])[0]
        base_url = self.get_base_url()
        m3u_content = self.playlist_mgr.generate_proxied_m3u(base_url, filter_group=group_filter)
        payload = m3u_content.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="restream_playlist.m3u"')
        self.send_header("Content-Length", str(len(payload)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def handle_channel_stream(self, cid: int):
        channel = self.playlist_mgr.get_channel(cid)
        if not channel:
            self.send_error(404, "Channel not found")
            return
        self.rewrite_and_serve_manifest(channel.url, channel)

    def handle_proxy_m3u8(self, query: Dict):
        target_url = query.get("url", [""])[0]
        cid_str = query.get("cid", ["0"])[0]
        if not target_url:
            self.send_error(400, "Missing target url")
            return

        channel = self.playlist_mgr.get_channel(int(cid_str)) if cid_str.isdigit() else None
        self.rewrite_and_serve_manifest(target_url, channel)

    def rewrite_and_serve_manifest(self, manifest_url: str, channel: Optional[Channel]):
        """Fetches upstream M3U8, rewrites variant playlists and segments to proxy, and streams."""
        headers = {}
        if channel and channel.headers:
            headers.update(channel.headers)

        try:
            req = urllib.request.Request(manifest_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12, context=SSL_CONTEXT) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            self.send_error(502, f"Upstream M3U8 fetch failed: {e}")
            return

        base_url = self.get_base_url()
        cid = channel.cid if channel else 0
        rewritten_m3u8 = self._rewrite_hls_content(content, manifest_url, base_url, cid)
        payload = rewritten_m3u8.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _rewrite_hls_content(self, m3u8_text: str, current_manifest_url: str, base_proxy_url: str, cid: int) -> str:
        lines = m3u8_text.splitlines()
        output_lines = []
        last_tag = ""

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                output_lines.append(line)
                continue

            if trimmed.startswith("#"):
                # Handle encryption key line
                if trimmed.startswith("#EXT-X-KEY:") and 'URI="' in trimmed:
                    line = self._rewrite_quoted_uri(trimmed, current_manifest_url, f"{base_proxy_url}/proxy/key", cid)
                # Handle init map segment line
                elif trimmed.startswith("#EXT-X-MAP:") and 'URI="' in trimmed:
                    line = self._rewrite_quoted_uri(trimmed, current_manifest_url, f"{base_proxy_url}/proxy/ts", cid)
                
                output_lines.append(line)
                last_tag = trimmed.split(":", 1)[0]
                continue

            # This is a URI line
            abs_url = urllib.parse.urljoin(current_manifest_url, trimmed)
            encoded_url = urllib.parse.quote(abs_url, safe="")

            if last_tag in ("#EXT-X-STREAM-INF", "#EXT-X-I-FRAME-STREAM-INF"):
                # Sub-manifest
                rewritten = f"{base_proxy_url}/proxy/m3u8?url={encoded_url}&cid={cid}"
            elif last_tag == "#EXTINF":
                # Media segment
                rewritten = f"{base_proxy_url}/proxy/ts?url={encoded_url}&cid={cid}"
            else:
                # Fallback based on extension or path
                if ".m3u8" in abs_url.lower():
                    rewritten = f"{base_proxy_url}/proxy/m3u8?url={encoded_url}&cid={cid}"
                else:
                    rewritten = f"{base_proxy_url}/proxy/ts?url={encoded_url}&cid={cid}"

            output_lines.append(rewritten)
            last_tag = ""

        return "\n".join(output_lines)

    def _rewrite_quoted_uri(self, tag_line: str, current_manifest_url: str, endpoint: str, cid: int) -> str:
        import re
        def repl(match):
            original_uri = match.group(1)
            abs_uri = urllib.parse.urljoin(current_manifest_url, original_uri)
            enc_uri = urllib.parse.quote(abs_uri, safe="")
            return f'URI="{endpoint}?url={enc_uri}&cid={cid}"'
        return re.sub(r'URI="([^"]+)"', repl, tag_line)

    def handle_proxy_ts(self, query: Dict):
        """Streams media segment directly to client with required upstream headers."""
        target_url = query.get("url", [""])[0]
        cid_str = query.get("cid", ["0"])[0]
        if not target_url:
            self.send_error(400, "Missing target url")
            return

        channel = self.playlist_mgr.get_channel(int(cid_str)) if cid_str.isdigit() else None
        headers = {}
        if channel and channel.headers:
            headers.update(channel.headers)

        # Forward client Range header if requested
        client_range = self.headers.get("Range")
        if client_range:
            headers["Range"] = client_range

        try:
            req = urllib.request.Request(target_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "video/mp2t")
                content_length = resp.headers.get("Content-Length")
                content_range = resp.headers.get("Content-Range")

                self.send_response(status)
                self.send_header("Content-Type", content_type)
                if content_length:
                    self.send_header("Content-Length", content_length)
                if content_range:
                    self.send_header("Content-Range", content_range)
                self.send_header("Accept-Ranges", "bytes")
                self.send_cors_headers()
                self.end_headers()

                # Stream in chunks
                buffer_size = 65536
                while True:
                    chunk = resp.read(buffer_size)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected / skipped forward, standard behavior in media streaming
            pass
        except Exception as e:
            try:
                self.send_error(502, f"Segment proxy failed: {e}")
            except Exception:
                pass

    def handle_proxy_key(self, query: Dict):
        target_url = query.get("url", [""])[0]
        cid_str = query.get("cid", ["0"])[0]
        channel = self.playlist_mgr.get_channel(int(cid_str)) if cid_str.isdigit() else None
        headers = channel.headers if channel else {}

        try:
            req = urllib.request.Request(target_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT) as resp:
                data = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/octet-stream"))
                self.send_header("Content-Length", str(len(data)))
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self.send_error(502, f"Key fetch failed: {e}")


def get_local_ip() -> str:
    """Finds the LAN IP address of this machine for Smart TV / phone streaming."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_server(port: int = 8080, playlist_url: str = None, host: str = "0.0.0.0"):
    """Starts the Restream Proxy Server."""
    pm = PlaylistManager(source_url=playlist_url) if playlist_url else PlaylistManager()
    print("=" * 60)
    print("       RESTREAM PROXY & IPTV WEB SERVER")
    print("=" * 60)
    print("Loading channel playlist...")
    pm.load_playlist()

    local_ip = get_local_ip()

    RestreamHandler.playlist_mgr = pm
    RestreamHandler.server_host = local_ip
    RestreamHandler.server_port = port

    server_address = (host, port)
    httpd = ThreadedHTTPServer(server_address, RestreamHandler)

    print("-" * 60)
    print(f"[*] Server running on port {port}")
    print(f"[*] Local Web Player:       http://localhost:{port}")
    print(f"[*] Network Web Player:     http://{local_ip}:{port}")
    print(f"[*] Full Proxied M3U URL:   http://{local_ip}:{port}/playlist.m3u")
    print(f"[*] Sports Only M3U URL:    http://{local_ip}:{port}/playlist.m3u?group=Sports")
    print("-" * 60)
    print("Open http://localhost:{port} in any browser or load the M3U into VLC!")
    print("Press Ctrl+C to stop the server.")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Shutting down server gracefully...")
        httpd.shutdown()
        httpd.server_close()
        print("[+] Server stopped.")


if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port=port)
