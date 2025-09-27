#!/usr/bin/env python3
"""
Simple Web Server for Testing DASH/HLS Streams
Automatically serves streaming files with proper CORS headers
"""

import http.server
import socketserver
import argparse
import os
from pathlib import Path

class StreamingHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler with CORS and streaming optimizations"""

    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Range')

        # Add caching headers based on file type
        if self.path.endswith('.m3u8') or self.path.endswith('.mpd'):
            # No caching for manifests/playlists
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        elif self.path.endswith('.ts') or self.path.endswith('.m4s'):
            # Cache segments for 1 hour
            self.send_header('Cache-Control', 'public, max-age=3600')

        # Content type headers
        if self.path.endswith('.m3u8'):
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
        elif self.path.endswith('.mpd'):
            self.send_header('Content-Type', 'application/dash+xml')
        elif self.path.endswith('.ts'):
            self.send_header('Content-Type', 'video/mp2t')

        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight requests"""
        self.send_response(204)
        self.end_headers()

def find_streaming_directories():
    """Find all streaming output directories"""
    current_dir = Path.cwd()
    streaming_dirs = []

    # Look for directories ending with _streaming
    for item in current_dir.iterdir():
        if item.is_dir() and item.name.endswith('_streaming'):
            streaming_dirs.append(item)

    return streaming_dirs

def main():
    parser = argparse.ArgumentParser(description='Streaming Web Server for DASH/HLS')
    parser.add_argument('-p', '--port', type=int, default=8000, help='Port number (default: 8000)')
    parser.add_argument('-d', '--directory', help='Directory to serve (default: current directory)')

    args = parser.parse_args()

    # Change to specified directory
    if args.directory:
        os.chdir(args.directory)

    # Find streaming directories
    streaming_dirs = find_streaming_directories()

    print(f"🌐 Starting Streaming Web Server")
    print(f"═══════════════════════════════")
    print(f"🏠 Directory: {Path.cwd()}")
    print(f"🔗 Port: {args.port}")
    print(f"📡 URL: http://localhost:{args.port}")

    if streaming_dirs:
        print(f"\n📂 Found {len(streaming_dirs)} streaming directories:")
        for stream_dir in streaming_dirs:
            print(f"   📺 {stream_dir.name}/")
            print(f"      🎬 HLS: http://localhost:{args.port}/{stream_dir.name}/hls_player.html")
            print(f"      📡 DASH: http://localhost:{args.port}/{stream_dir.name}/dash_player.html")
    else:
        print("\n⚠️  No streaming directories found (looking for *_streaming/)")

    print(f"\n🎯 Features:")
    print(f"   ✅ CORS headers enabled")
    print(f"   ✅ Proper MIME types for streaming")
    print(f"   ✅ Optimized caching headers")
    print(f"   ✅ Range request support")

    print(f"\n🛑 Press Ctrl+C to stop the server")
    print("═══════════════════════════════")

    # Start server
    try:
        with socketserver.TCPServer(("", args.port), StreamingHTTPRequestHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n❌ Port {args.port} is already in use")
            print(f"   Try a different port: python3 {__file__} -p 8001")
        else:
            print(f"\n❌ Server error: {e}")

if __name__ == "__main__":
    main()
