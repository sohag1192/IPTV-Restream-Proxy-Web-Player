"""
RTMP Re-streamer Module
Restreams channels from the M3U playlist to RTMP targets
(YouTube Live, Facebook Live, Twitch, Kick, custom RTMP/SRT servers) using FFmpeg.
"""

import sys
import shutil
import subprocess
from typing import Optional
from playlist_manager import PlaylistManager, Channel


def check_ffmpeg_available() -> bool:
    """Checks if FFmpeg binary is installed and present in PATH."""
    return shutil.which("ffmpeg") is not None


def build_ffmpeg_command(
    stream_url: str,
    rtmp_target: str,
    headers: Optional[dict] = None,
    transcode: bool = False,
    reconnect: bool = True
) -> list:
    """
    Builds the FFmpeg command line arguments.
    """
    cmd = ["ffmpeg"]

    # Reconnection flags for resilient live streaming
    if reconnect:
        cmd.extend([
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5"
        ])

    # Pass headers if streaming directly from upstream
    if headers:
        header_lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        cmd.extend(["-headers", header_lines])

    # Read input at native framerate (-re)
    cmd.extend(["-re", "-i", stream_url])

    if transcode:
        # Re-encode video (H.264) and audio (AAC) for strict RTMP compliance
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-b:v", "3000k",
            "-maxrate", "3500k",
            "-bufsize", "6000k",
            "-pix_fmt", "yuv420p",
            "-g", "50",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100"
        ])
    else:
        # Stream copy (ultrafast, low CPU usage)
        cmd.extend([
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k"
        ])

    # FLV output for RTMP
    cmd.extend(["-f", "flv", rtmp_target])
    return cmd


def start_restream(
    channel_id: int,
    rtmp_target: str,
    playlist_mgr: PlaylistManager,
    use_local_proxy: bool = True,
    proxy_port: int = 8080,
    transcode: bool = False
):
    """
    Executes FFmpeg to forward the channel to RTMP.
    """
    if not check_ffmpeg_available():
        print("\n[ERROR] FFmpeg is not installed or not found in system PATH!")
        print("Please install FFmpeg to use the RTMP restream feature:")
        print("  Windows: winget install Gyan.FFmpeg")
        print("  Linux:   sudo apt install ffmpeg")
        print("  Mac:     brew install ffmpeg\n")
        return False

    channel = playlist_mgr.get_channel(channel_id)
    if not channel:
        print(f"[ERROR] Channel with ID {channel_id} not found.")
        return False

    if use_local_proxy:
        stream_url = f"http://localhost:{proxy_port}/channel/{channel.cid}.m3u8"
        headers = None
    else:
        stream_url = channel.url
        headers = channel.headers

    print("=" * 60)
    print(f"[*] Starting RTMP Restream for: {channel.name} (CH #{channel.cid})")
    print(f"[*] Category:      {channel.group}")
    print(f"[*] Source URL:    {stream_url}")
    print(f"[*] RTMP Target:   {rtmp_target}")
    print(f"[*] Transcoding:   {'Enabled (H.264+AAC)' if transcode else 'Disabled (Direct Copy)'}")
    print("=" * 60)

    cmd = build_ffmpeg_command(stream_url, rtmp_target, headers=headers, transcode=transcode)
    print("[*] Executing command:")
    print(" ".join(cmd))
    print("-" * 60)
    print("Streaming in progress... Press Ctrl+C to stop.")

    try:
        proc = subprocess.Popen(cmd)
        proc.wait()
    except KeyboardInterrupt:
        print("\n[!] Stopping RTMP stream...")
        proc.terminate()
        proc.wait()
        print("[+] Stream stopped.")
    return True


if __name__ == "__main__":
    pm = PlaylistManager()
    pm.load_playlist()

    if len(sys.argv) < 3:
        print("Usage: python rtmp_streamer.py <channel_id> <rtmp_url_with_key>")
        print("Example: python rtmp_streamer.py 5 rtmp://a.rtmp.youtube.com/live2/xxxx-xxxx-xxxx-xxxx")
        sys.exit(1)

    cid = int(sys.argv[1])
    target = sys.argv[2]
    start_restream(cid, target, pm)
