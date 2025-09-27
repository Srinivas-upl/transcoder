#!/usr/bin/env python3
"""
Simple DASH/HLS Video Transcoder and Segmenter
Uses FFmpeg to convert videos to multiple resolutions and create streaming segments
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional

class VideoTranscoder:

    def __init__(self, input_file: str, output_dir: str = None):
        self.input_file = input_file
        # self.output_dir = Path(output_dir + "_streaming") if output_dir else Path(input_file).stem + "_streaming"
        self.output_dir = Path("sample_streaming")

        # Quality profiles for different resolutions
        self.profiles = {
            "240p": {"width": 426, "height": 240, "bitrate": "400k", "audio_bitrate": "64k"},
            "360p": {"width": 640, "height": 360, "bitrate": "800k", "audio_bitrate": "96k"},
            "480p": {"width": 854, "height": 480, "bitrate": "1200k", "audio_bitrate": "128k"},
            "720p": {"width": 1280, "height": 720, "bitrate": "2500k", "audio_bitrate": "128k"},
            "1080p": {"width": 1920, "height": 1080, "bitrate": "4500k", "audio_bitrate": "192k"}
        }

        # Segment duration in seconds
        self.segment_duration = 6

        # Video information
        self.video_info = None

    def check_ffmpeg(self):
        """Check if FFmpeg is available"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ FFmpeg not found. Please install FFmpeg first.")
            print("   macOS: brew install ffmpeg")
            print("   Ubuntu/Debian: sudo apt install ffmpeg")
            print("   Windows: Download from https://ffmpeg.org/")
            return False

    def get_video_info(self) -> Dict:
        """Get video information using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', self.input_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)

            # Find video stream
            video_stream = next(
                (stream for stream in info['streams'] if stream['codec_type'] == 'video'),
                None
            )

            if not video_stream:
                raise ValueError("No video stream found")

            self.video_info = {
                'duration': float(info['format'].get('duration', 0)),
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'fps': self._parse_fps(video_stream.get('r_frame_rate', '25/1')),
                'bitrate': int(info['format'].get('bit_rate', 0))
            }

            print(f"📹 Video Info: {self.video_info['width']}x{self.video_info['height']} @ {self.video_info['fps']:.1f}fps")
            print(f"⏱️  Duration: {self.video_info['duration']:.1f} seconds")

            return self.video_info

        except subprocess.CalledProcessError as e:
            print(f"❌ Error getting video info: {e}")
            sys.exit(1)
        except json.JSONDecodeError:
            print("❌ Error parsing video information")
            sys.exit(1)

    def _parse_fps(self, fps_str: str) -> float:
        """Parse frame rate from fraction string like '25/1'"""
        try:
            if '/' in fps_str:
                num, den = fps_str.split('/')
                return float(num) / float(den)
            return float(fps_str)
        except:
            return 25.0  # default

    def filter_profiles(self) -> Dict:
        """Filter profiles based on source video resolution"""
        if not self.video_info:
            self.get_video_info()

        filtered_profiles = {}
        source_width = self.video_info['width']
        source_height = self.video_info['height']

        for name, profile in self.profiles.items():
            # Only include profiles that don't upscale
            if profile['width'] <= source_width and profile['height'] <= source_height:
                filtered_profiles[name] = profile

        if not filtered_profiles:
            # If source is very small, include the smallest profile
            smallest_profile = min(self.profiles.items(), key=lambda x: x[1]['width'])
            filtered_profiles[smallest_profile[0]] = smallest_profile[1]

        print(f"📊 Will create {len(filtered_profiles)} quality levels: {', '.join(filtered_profiles.keys())}")
        return filtered_profiles

    def create_hls_streams(self) -> Dict[str, str]:
        """Create HLS streams for all valid profiles"""
        profiles = self.filter_profiles()
        hls_dir = self.output_dir / "hls"
        hls_dir.mkdir(parents=True, exist_ok=True)

        hls_outputs = {}

        for profile_name, profile in profiles.items():
            print(f"🎬 Creating HLS stream: {profile_name} ({profile['width']}x{profile['height']})")

            # Create directory for this profile
            profile_dir = hls_dir / profile_name
            profile_dir.mkdir(exist_ok=True)

            playlist_file = profile_dir / "playlist.m3u8"
            segment_pattern = profile_dir / "segment_%03d.ts"

            # FFmpeg command for HLS
            cmd = [
                'ffmpeg', '-i', self.input_file,
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                '-c:a', 'aac',
                '-b:v', profile['bitrate'],
                '-b:a', profile['audio_bitrate'],
                '-vf', f"scale={profile['width']}:{profile['height']}",
                '-f', 'hls',
                '-hls_time', str(self.segment_duration),
                '-hls_list_size', '0',
                '-hls_segment_filename', str(segment_pattern),
                str(playlist_file),
                '-y'  # Overwrite output files
            ]

            try:
                # Run FFmpeg with progress
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                hls_outputs[profile_name] = str(playlist_file)
                print(f"   ✅ Created: {playlist_file}")

            except subprocess.CalledProcessError as e:
                print(f"   ❌ Error creating HLS {profile_name}: {e}")
                if e.stderr:
                    print(f"      FFmpeg error: {e.stderr[-200:]}")  # Last 200 chars

        return hls_outputs

    def create_dash_stream(self) -> Optional[str]:
        """Create DASH stream with multiple representations"""
        profiles = self.filter_profiles()
        dash_dir = self.output_dir / "dash"
        dash_dir.mkdir(parents=True, exist_ok=True)

        print(f"🎬 Creating DASH stream with {len(profiles)} representations")

        # Build FFmpeg command for DASH
        cmd = ['ffmpeg', '-i', self.input_file]

        # Add video streams
        map_args = []
        output_args = []

        for i, (profile_name, profile) in enumerate(profiles.items()):
            # Map video stream
            map_args.extend(['-map', f'0:v:0'])

            # Video encoding settings for this representation
            output_args.extend([
                f'-c:v:{i}', 'libx264',
                f'-preset:v:{i}', 'medium',
                f'-b:v:{i}', profile['bitrate'],
                f'-s:v:{i}', f"{profile['width']}x{profile['height']}"
            ])

        # Add audio stream (single audio for all)
        map_args.extend(['-map', '0:a:0'])
        output_args.extend(['-c:a', 'aac', '-b:a', '128k'])

        # DASH-specific settings
        dash_args = [
            '-f', 'dash',
            '-seg_duration', str(self.segment_duration),
            '-adaptation_sets', 'id=0,streams=v id=1,streams=a',
            '-use_template', '1',
            '-use_timeline', '1'
        ]

        manifest_file = dash_dir / "manifest.mpd"

        # Complete command
        full_cmd = cmd + map_args + output_args + dash_args + [str(manifest_file), '-y']

        try:
            result = subprocess.run(full_cmd, capture_output=True, text=True, check=True)
            print(f"   ✅ Created: {manifest_file}")
            return str(manifest_file)

        except subprocess.CalledProcessError as e:
            print(f"   ❌ Error creating DASH stream: {e}")
            if e.stderr:
                print(f"      FFmpeg error: {e.stderr[-200:]}")
            return None

    def create_master_hls_playlist(self, hls_outputs: Dict[str, str]) -> str:
        """Create master HLS playlist for adaptive streaming"""
        master_playlist = self.output_dir / "hls" / "master.m3u8"

        with open(master_playlist, 'w') as f:
            f.write("#EXTM3U\n#EXT-X-VERSION:6\n\n")

            # Sort profiles by bitrate (highest first)
            sorted_profiles = sorted(
                hls_outputs.items(),
                key=lambda x: int(self.profiles[x[0]]['bitrate'].replace('k', '000')),
                reverse=True
            )

            for profile_name, playlist_path in sorted_profiles:
                profile = self.profiles[profile_name]

                # Calculate total bandwidth
                video_bw = int(profile['bitrate'].replace('k', '000'))
                audio_bw = int(profile['audio_bitrate'].replace('k', '000'))
                total_bw = video_bw + audio_bw

                f.write(f"#EXT-X-STREAM-INF:BANDWIDTH={total_bw},")
                f.write(f"RESOLUTION={profile['width']}x{profile['height']}\n")
                f.write(f"{profile_name}/playlist.m3u8\n\n")

        print(f"✅ Master playlist: {master_playlist}")
        return str(master_playlist)

    def create_test_players(self):
        """Create simple HTML test players"""

        # HLS Player
        hls_player = f"""<!DOCTYPE html>
<html>
<head>
    <title>HLS Player - {Path(self.input_file).stem}</title>
    <script src="https://vjs.zencdn.net/8.5.2/video.min.js"></script>
    <link href="https://vjs.zencdn.net/8.5.2/video-js.css" rel="stylesheet">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
        h1 {{ color: #333; }}
        .video-js {{ margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎥 HLS Player</h1>
        <p>Video: <strong>{Path(self.input_file).name}</strong></p>

        <video-js id="hls-player" class="vjs-default-skin" 
                  controls preload="auto" width="800" height="450" 
                  data-setup="{{}}">
            <source src="hls/master.m3u8" type="application/x-mpegURL">
            <p class="vjs-no-js">
                To view this video please enable JavaScript, and consider upgrading to a web browser that
                <a href="https://videojs.com/html5-video-support/" target="_blank">supports HTML5 video</a>.
            </p>
        </video-js>

        <div style="margin-top: 20px;">
            <h3>Available Streams:</h3>
            <ul>
                <li><a href="hls/master.m3u8">Master Playlist (Adaptive)</a></li>
                <li><a href="dash/manifest.mpd">DASH Manifest</a></li>
                <li><a href="dash_player.html">DASH Player</a></li>
            </ul>
        </div>
    </div>

    <script>
        var player = videojs('hls-player');
        console.log('HLS player initialized');
    </script>
</body>
</html>"""

        # DASH Player
        dash_player = f"""<!DOCTYPE html>
<html>
<head>
    <title>DASH Player - {Path(self.input_file).stem}</title>
    <script src="https://cdn.dashjs.org/latest/dash.all.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
        h1 {{ color: #333; }}
        video {{ margin: 20px 0; width: 100%; max-width: 800px; height: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📺 DASH Player</h1>
        <p>Video: <strong>{Path(self.input_file).name}</strong></p>

        <video id="dash-player" controls width="800" height="450"></video>

        <div style="margin-top: 20px;">
            <h3>Stream Information:</h3>
            <ul>
                <li><strong>Format:</strong> DASH (Dynamic Adaptive Streaming)</li>
                <li><strong>Segments:</strong> {self.segment_duration} second chunks</li>
                <li><strong>Adaptive Bitrate:</strong> Automatically adjusts quality</li>
            </ul>

            <h3>Available Streams:</h3>
            <ul>
                <li><a href="dash/manifest.mpd">DASH Manifest</a></li>
                <li><a href="hls/master.m3u8">HLS Master Playlist</a></li>
                <li><a href="hls_player.html">HLS Player</a></li>
            </ul>
        </div>
    </div>

    <script>
        var url = "dash/manifest.mpd";
        var player = dashjs.MediaPlayer().create();
        player.initialize(document.querySelector("#dash-player"), url, true);
        console.log('DASH player initialized with:', url);
    </script>
</body>
</html>"""

        # Write test players
        hls_player_file = self.output_dir / "hls_player.html"
        dash_player_file = self.output_dir / "dash_player.html"

        with open(hls_player_file, 'w') as f:
            f.write(hls_player)

        with open(dash_player_file, 'w') as f:
            f.write(dash_player)

        print(f"🌐 Test players created:")
        print(f"   HLS: {hls_player_file}")
        print(f"   DASH: {dash_player_file}")

    def create_summary(self):
        """Create a summary file with information about the streams"""
        summary_file = self.output_dir / "README.md"

        content = f"""# Streaming Files for {Path(self.input_file).name}

## 📹 Source Video Information
- **File**: {Path(self.input_file).name}
- **Resolution**: {self.video_info['width']}x{self.video_info['height']}
- **Duration**: {self.video_info['duration']:.1f} seconds
- **Frame Rate**: {self.video_info['fps']:.1f} fps

## 📂 Generated Files

### HLS (HTTP Live Streaming)
- **Master Playlist**: `hls/master.m3u8`
- **Test Player**: `hls_player.html`

### DASH (Dynamic Adaptive Streaming over HTTP)  
- **Manifest**: `dash/manifest.mpd`
- **Test Player**: `dash_player.html`

## 🎚️ Quality Profiles
"""

        profiles = self.filter_profiles()
        for name, profile in profiles.items():
            content += f"- **{name}**: {profile['width']}x{profile['height']} @ {profile['bitrate']} video, {profile['audio_bitrate']} audio\n"

        content += f"""
## 🚀 How to Use

### Local Testing
1. Start a local web server in this directory:
   ```bash
   python3 -m http.server 8000
   ```
2. Open test players:
   - HLS: http://localhost:8000/hls_player.html
   - DASH: http://localhost:8000/dash_player.html

### Integration
- **HLS URL**: `hls/master.m3u8`
- **DASH URL**: `dash/manifest.mpd`
- **Segment Duration**: {self.segment_duration} seconds

## 📊 Directory Structure
```
{self.output_dir.name}/
├── hls/
│   ├── master.m3u8        # Master playlist
│   ├── 240p/              # Low quality
│   ├── 360p/              # Mobile quality  
│   ├── 480p/              # Standard quality
│   ├── 720p/              # HD quality
│   └── 1080p/             # Full HD quality
├── dash/
│   ├── manifest.mpd       # DASH manifest
│   └── segments/          # Video/audio segments
├── hls_player.html        # HLS test player
├── dash_player.html       # DASH test player
└── README.md             # This file
```

Generated by Simple DASH/HLS Transcoder 🎬
"""

        with open(summary_file, 'w') as f:
            f.write(content)

        print(f"📄 Summary created: {summary_file}")

    def process(self):
        """Main processing function"""
        print(f"🎬 Simple DASH/HLS Transcoder")
        print(f"═══════════════════════════════")
        print(f"📁 Input: {self.input_file}")
        print(f"📁 Output: {self.output_dir}")
        print()

        # Check prerequisites
        if not self.check_ffmpeg():
            return False

        if not os.path.exists(self.input_file):
            print(f"❌ Input file not found: {self.input_file}")
            return False

        # Create output directory
        self.output_dir.mkdir(exist_ok=True)

        # Get video information
        self.get_video_info()
        print()

        # Create HLS streams
        print("🎬 Creating HLS streams...")
        hls_outputs = self.create_hls_streams()
        print()

        if hls_outputs:
            # Create master playlist
            self.create_master_hls_playlist(hls_outputs)

        # Create DASH stream
        print("📺 Creating DASH stream...")
        dash_manifest = self.create_dash_stream()
        print()

        # Create test players
        self.create_test_players()

        # Create summary
        self.create_summary()

        # Final summary
        print("═══════════════════════════════")
        print("🎉 TRANSCODING COMPLETE!")
        print("═══════════════════════════════")
        print(f"📁 Output directory: {self.output_dir.absolute()}")
        print(f"🎬 HLS streams: {len(hls_outputs)} quality levels")
        print(f"📺 DASH stream: {'✅' if dash_manifest else '❌'}")
        print()
        print("🚀 Next steps:")
        print(f"   1. cd {self.output_dir}")
        print("   2. python3 -m http.server 8000")
        print("   3. Open http://localhost:8000/hls_player.html")
        print("   4. Or http://localhost:8000/dash_player.html")
        print()
        return True

def main():
    parser = argparse.ArgumentParser(
        description='Simple DASH/HLS Video Transcoder using FFmpeg',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s video.mp4                    # Basic usage
  %(prog)s video.mp4 -o my_stream       # Custom output directory
  %(prog)s video.mp4 -s 4               # 4-second segments
  %(prog)s video.mp4 --profiles 720p 480p 360p  # Specific quality levels
        """
    )

    parser.add_argument('input', help='Input video file')
    parser.add_argument('-o', '--output', help='Output directory (default: input_name_streaming)')
    parser.add_argument('-s', '--segment-duration', type=int, default=6,
                       help='Segment duration in seconds (default: 6)')
    parser.add_argument('-p','--profiles', nargs='*',
                       choices=['240p', '360p', '480p', '720p', '1080p'],
                       help='Specific quality profiles to generate')

    args = parser.parse_args()

    # Create transcoder
    transcoder = VideoTranscoder(args.input, args.output)
    transcoder.segment_duration = args.segment_duration

    # Filter profiles if specified
    if args.profiles:
        transcoder.profiles = {
            name: profile for name, profile in transcoder.profiles.items()
            if name in args.profiles
        }
        print(f"🎯 Using specified profiles: {', '.join(args.profiles)}")

    # Process video
    success = transcoder.process()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
