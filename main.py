#!/usr/bin/env python3
"""
Restream Suite - Master CLI
Interactive console for starting the restream proxy, playing channels,
restreaming to RTMP (YouTube/Facebook/Twitch), and exporting playlists.
"""

import sys
import os
import subprocess
import webbrowser
from playlist_manager import PlaylistManager
from restream_proxy import run_server, get_local_ip
from rtmp_streamer import start_restream, check_ffmpeg_available


def banner():
    print("""
================================================================
   ____           __                             ____ _____  __  __ 
  / __ \___  ___ / /_________ ___ ___ _  __ __  /  _// _ \ \/ / / / 
 / /_/ / -_)(_-</ __/ __/ -_) _ `/  ' \ / // / _/ / / ___/\  / /_/  
/ _, _/\__//___/\__/_/  \__/\_,_/_/_/_/ \_, / /___//_/     /_/ (_)   
/_/ |_|                                /___/                        
================================================================
   Live HLS Proxy, Web Player & RTMP Re-broadcasting Suite
================================================================
""")


def menu_print_channels(pm: PlaylistManager):
    q = input("\nEnter search keyword (or press Enter for all): ").strip()
    channels = pm.search_channels(query=q)
    print(f"\nFound {len(channels)} channels:")
    print("-" * 75)
    print(f"{'ID':<6} | {'Category':<15} | {'Channel Name'}")
    print("-" * 75)
    for ch in channels[:50]:
        print(f"#{ch.cid:<5} | {ch.group[:14]:<15} | {ch.name}")
    if len(channels) > 50:
        print(f"... and {len(channels) - 50} more channels.")
    print("-" * 75)


def menu_export_m3u(pm: PlaylistManager):
    local_ip = get_local_ip()
    port = input("Enter server port (default 8080): ").strip() or "8080"
    base_url = f"http://{local_ip}:{port}"
    output_filename = input("Enter output filename (default 'proxied_playlist.m3u'): ").strip() or "proxied_playlist.m3u"
    
    m3u_text = pm.generate_proxied_m3u(base_url)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(m3u_text)
    
    print(f"\n[+] Successfully exported {len(pm.channels)} channels to '{output_filename}'!")
    print(f"[+] Every channel points to your local proxy at {base_url}")


def menu_play_channel_vlc(pm: PlaylistManager):
    cid_str = input("Enter channel ID to play (e.g. 1): ").strip()
    if not cid_str.isdigit():
        print("[!] Invalid channel ID.")
        return
    ch = pm.get_channel(int(cid_str))
    if not ch:
        print("[!] Channel not found.")
        return

    local_ip = get_local_ip()
    proxy_url = f"http://localhost:8080/channel/{ch.cid}.m3u8"
    print(f"\n[*] Playing {ch.name} via local proxy: {proxy_url}")
    
    # Try VLC
    vlc_path = None
    for p in [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]:
        if os.path.exists(p):
            vlc_path = p
            break
            
    if vlc_path:
        print("[*] Launching VLC Player...")
        subprocess.Popen([vlc_path, proxy_url])
    else:
        print("[*] VLC not found in default location. Opening in default web browser player...")
        webbrowser.open("http://localhost:8080")


def menu_rtmp_stream(pm: PlaylistManager):
    print("\n--- RTMP Restreamer (YouTube / Facebook / Twitch) ---")
    cid_str = input("Enter channel ID to restream (e.g. 5 for A sports): ").strip()
    if not cid_str.isdigit():
        print("[!] Invalid channel ID.")
        return
    cid = int(cid_str)
    ch = pm.get_channel(cid)
    if not ch:
        print("[!] Channel not found.")
        return

    print(f"Selected: {ch.name} ({ch.group})")
    print("\nCommon RTMP URLs:")
    print(" - YouTube:  rtmp://a.rtmp.youtube.com/live2/<YOUR_STREAM_KEY>")
    print(" - Facebook: rtmps://live-api-s.facebook.com:443/rtmp/<YOUR_STREAM_KEY>")
    print(" - Twitch:   rtmp://live.twitch.tv/app/<YOUR_STREAM_KEY>")
    print(" - Local:    rtmp://localhost/live/stream")
    
    rtmp_target = input("\nEnter RTMP URL: ").strip()
    if not rtmp_target:
        print("[!] RTMP URL cannot be empty.")
        return

    transcode_input = input("Transcode video with x264? (y/N, recommend N for speed): ").strip().lower()
    transcode = transcode_input == 'y'

    start_restream(cid, rtmp_target, pm, use_local_proxy=False, transcode=transcode)


def main():
    banner()
    pm = PlaylistManager()
    print("Loading channels...")
    pm.load_playlist()

    while True:
        print("\nChoose an option:")
        print(" [1] Start Restream Proxy & Web Player Server (Recommended)")
        print(" [2] Restream a Channel to YouTube / Facebook / Twitch (RTMP)")
        print(" [3] Play a Channel in VLC")
        print(" [4] Search & List Channels")
        print(" [5] Export Proxied M3U Playlist to File")
        print(" [6] Refresh Playlist from GitHub")
        print(" [0] Exit")

        choice = input("\nEnter choice [0-6]: ").strip()

        if choice == "1":
            port_str = input("Enter port (default 8080): ").strip() or "8080"
            port = int(port_str) if port_str.isdigit() else 8080
            # Open browser automatically after launching
            try:
                import threading
                import time
                def open_b():
                    time.sleep(1.2)
                    webbrowser.open(f"http://localhost:{port}")
                threading.Thread(target=open_b, daemon=True).start()
            except Exception:
                pass
            run_server(port=port)
            break
        elif choice == "2":
            menu_rtmp_stream(pm)
        elif choice == "3":
            menu_play_channel_vlc(pm)
        elif choice == "4":
            menu_print_channels(pm)
        elif choice == "5":
            menu_export_m3u(pm)
        elif choice == "6":
            print("\nRefreshing playlist...")
            pm.load_playlist(force_refresh=True)
            print("[+] Refreshed successfully.")
        elif choice == "0":
            print("\nExiting. Goodbye!")
            sys.exit(0)
        else:
            print("[!] Invalid option. Please choose between 0 and 6.")


if __name__ == "__main__":
    main()
