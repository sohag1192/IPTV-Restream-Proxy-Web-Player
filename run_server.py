#!/usr/bin/env python3
"""
Direct Server Runner
Quickly launch the Restream Proxy Server and Web Player.
Usage:
  python run_server.py
  python run_server.py --port 8080
"""

import sys
import argparse
from restream_proxy import run_server

def main():
    parser = argparse.ArgumentParser(description="Run Restream Proxy Server and Web Player")
    parser.add_argument("--port", type=int, default=8080, help="Port to run server on (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--playlist", type=str, default=None, help="Custom M3U playlist URL or file path")
    args = parser.parse_args()

    run_server(port=args.port, host=args.host, playlist_url=args.playlist)

if __name__ == "__main__":
    main()
