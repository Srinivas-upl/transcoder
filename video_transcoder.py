#!/usr/bin/env python3
"""
HLS/DASH Video Transcoding Pipeline
Creates adaptive bitrate streams with chunking and segmentation
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
import argparse
import logging
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/transcoding.log'),
        logging.StreamHandler()
    ]
)

class VideoTranscoder:
    def __init__(self, input_file: str, output_dir: str = "output"):
        self.input_file = input_file
        self.output_dir = Path(output_dir)
        self.video_info = None

        # Create output directory
        self.output_dir.mkdir(exist_ok=True)

        # Transcoding profiles for adaptive bitrate
        self.profiles = {
            "1080p": {"width": 1920, "height": 1080, "bitrate": "5M", "audio_bitrate": "192k"},
            "720p": {"width": 1280, "height": 720, "bitrate": "3M", "audio_bitrate": "128k"},
            "480p": {"width": 854, "height": 480, "bitrate": "1.5M", "audio_bitrate": "128k"},
            "360p": {"width": 640, "height": 360, "bitrate": "800k", "audio_bitrate": "96k"},
            "240p": {"width": 426, "height": 240, "bitrate": "400k", "audio_bitrate": "64k"}
        }

        # Segment duration in seconds
        self.segment_duration = 10

    def get_video_info(self) -> Dict:
        """Extract video information using ffprobe"""
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

            self.video_info = {
                'duration': float(info['format']['duration']),
                'width': int(video_stream['width']) if video_stream else 0,
                'height': int(video_stream['height']) if video_stream else 0,
                'fps': eval(video_stream['r_frame_rate']) if video_stream else 0
            }

            logging.info(f"Video info: {self.video_info}")
            return self.video_info

        except subprocess.CalledProcessError as e:
            logging.error(f"Error getting video info: {e}")
            raise

    def create_hls_streams(self) -> Dict[str, str]:
        """Create HLS streams for all profiles"""
        if not self.video_info:
            self.get_video_info()

        hls_outputs = {}

        for profile_name, profile in self.profiles.items():
            # Skip profiles larger than source resolution
            if (profile['width'] > self.video_info['width'] or 
                profile['height'] > self.video_info['height']):
                logging.info(f"Skipping {profile_name} - larger than source")
                continue

            output_dir = self.output_dir / "hls" / profile_name
            output_dir.mkdir(parents=True, exist_ok=True)

            playlist_file = output_dir / "playlist.m3u8"
            segment_pattern = output_dir / "segment_%03d.ts"

            cmd = [
                'ffmpeg', '-i', self.input_file,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:v', profile['bitrate'],
                '-b:a', profile['audio_bitrate'],
                '-vf', f"scale={profile['width']}:{profile['height']}",
                '-hls_time', str(self.segment_duration),
                '-hls_list_size', '0',
                '-hls_segment_type', 'mpegts',
                '-hls_segment_filename', str(segment_pattern),
                '-f', 'hls',
                str(playlist_file),
                '-y'
            ]

            logging.info(f"Creating HLS stream for {profile_name}...")
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                hls_outputs[profile_name] = str(playlist_file)
                logging.info(f"✓ HLS {profile_name} created successfully")
            except subprocess.CalledProcessError as e:
                logging.error(f"Error creating HLS {profile_name}: {e}")

        return hls_outputs

    def create_dash_streams(self) -> str:
        """Create DASH stream with multiple representations"""
        if not self.video_info:
            self.get_video_info()

        dash_dir = self.output_dir / "dash"
        dash_dir.mkdir(parents=True, exist_ok=True)

        # Build complex filter for multiple outputs
        filter_complex = []
        map_args = []
        output_args = []

        valid_profiles = []
        for i, (profile_name, profile) in enumerate(self.profiles.items()):
            if (profile['width'] <= self.video_info['width'] and 
                profile['height'] <= self.video_info['height']):
                valid_profiles.append((i, profile_name, profile))

        # Video scaling filters
        if len(valid_profiles) > 1:
            filter_complex.append(f"[0:v]split={len(valid_profiles)}" + 
                                "".join(f"[v{i}]" for i, _, _ in valid_profiles))
        else:
            filter_complex.append("[0:v]copy[v0]")

        # Scale each output
        for i, profile_name, profile in valid_profiles:
            if len(valid_profiles) > 1:
                filter_complex.append(
                    f"[v{i}]scale={profile['width']}:{profile['height']}[v{i}out]"
                )
                map_args.extend(['-map', f'[v{i}out]'])
            else:
                filter_complex.append(
                    f"[v0]scale={profile['width']}:{profile['height']}[v0out]"
                )
                map_args.extend(['-map', f'[v0out]'])

            # Video encoding settings
            output_args.extend([
                f'-c:v:{i}', 'libx264',
                f'-b:v:{i}', profile['bitrate'],
                f'-preset:v:{i}', 'medium'
            ])

        # Audio mapping
        map_args.extend(['-map', '0:a'])
        output_args.extend(['-c:a', 'aac', '-b:a', '128k'])

        cmd = [
            'ffmpeg', '-i', self.input_file,
            '-filter_complex', ';'.join(filter_complex)
        ] + map_args + output_args + [
            '-f', 'dash',
            '-seg_duration', str(self.segment_duration),
            '-adaptation_sets', 'id=0,streams=v id=1,streams=a',
            '-use_template', '1',
            '-use_timeline', '1',
            str(dash_dir / 'manifest.mpd'),
            '-y'
        ]

        logging.info("Creating DASH stream...")
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logging.info("✓ DASH stream created successfully")
            return str(dash_dir / 'manifest.mpd')
        except subprocess.CalledProcessError as e:
            logging.error(f"Error creating DASH stream: {e}")
            return None

    def create_master_hls_playlist(self, hls_outputs: Dict[str, str]) -> str:
        """Create master HLS playlist for adaptive streaming"""
        master_playlist_path = self.output_dir / "hls" / "master.m3u8"

        with open(master_playlist_path, 'w') as f:
            f.write("#EXTM3U\n")
            f.write("#EXT-X-VERSION:6\n")

            for profile_name, playlist_file in hls_outputs.items():
                profile = self.profiles[profile_name]
                # Calculate bandwidth (bitrate + audio bitrate)
                video_bw = int(profile['bitrate'].replace('M', '000000').replace('k', '000'))
                audio_bw = int(profile['audio_bitrate'].replace('k', '000'))
                total_bw = video_bw + audio_bw

                f.write(f"#EXT-X-STREAM-INF:BANDWIDTH={total_bw},"
                       f"RESOLUTION={profile['width']}x{profile['height']}\n")
                f.write(f"{profile_name}/playlist.m3u8\n")

        logging.info(f"✓ Master HLS playlist created: {master_playlist_path}")
        return str(master_playlist_path)

    def generate_html_players(self) -> None:
        """Generate HTML test players for HLS and DASH"""
        # HLS Player
        hls_player = f"""<!DOCTYPE html>
<html>
<head>
    <title>HLS Player Test</title>
    <script src="https://vjs.zencdn.net/8.5.2/video.min.js"></script>
    <link href="https://vjs.zencdn.net/8.5.2/video-js.css" rel="stylesheet">
</head>
<body>
    <h1>HLS Adaptive Streaming Test</h1>
    <video-js id="hls-player" class="vjs-default-skin" controls preload="auto" 
              width="800" height="450" data-setup="{{}}">
        <source src="hls/master.m3u8" type="application/x-mpegURL">
        <p class="vjs-no-js">
            To view this video please enable JavaScript, and consider upgrading to a web browser that
            <a href="https://videojs.com/html5-video-support/" target="_blank">supports HTML5 video</a>.
        </p>
    </video-js>
    <script>
        var player = videojs('hls-player');
    </script>
</body>
</html>"""

        # DASH Player  
        dash_player = f"""<!DOCTYPE html>
<html>
<head>
    <title>DASH Player Test</title>
    <script src="https://cdn.dashjs.org/latest/dash.all.min.js"></script>
</head>
<body>
    <h1>DASH Adaptive Streaming Test</h1>
    <video id="dash-player" controls width="800" height="450"></video>
    <script>
        var url = "dash/manifest.mpd";
        var player = dashjs.MediaPlayer().create();
        player.initialize(document.querySelector("#dash-player"), url, true);
    </script>
</body>
</html>"""

        with open(self.output_dir / "hls_player.html", 'w') as f:
            f.write(hls_player)

        with open(self.output_dir / "dash_player.html", 'w') as f:
            f.write(dash_player)

        logging.info("✓ HTML test players generated")

    def process(self) -> None:
        """Run complete transcoding pipeline"""
        logging.info(f"Starting transcoding pipeline for: {self.input_file}")

        # Get video information
        self.get_video_info()

        # Create HLS streams
        hls_outputs = self.create_hls_streams()

        if hls_outputs:
            # Create master playlist
            self.create_master_hls_playlist(hls_outputs)

        # Create DASH stream
        dash_manifest = self.create_dash_streams()

        # Generate test players
        self.generate_html_players()

        # Print summary
        logging.info("\n" + "="*50)
        logging.info("TRANSCODING COMPLETE")
        logging.info("="*50)
        logging.info(f"Input file: {self.input_file}")
        logging.info(f"Output directory: {self.output_dir}")
        logging.info(f"HLS streams created: {len(hls_outputs)}")
        logging.info(f"DASH stream: {'✓' if dash_manifest else '✗'}")
        logging.info(f"Segment duration: {self.segment_duration}s")

        if hls_outputs:
            logging.info("\nHLS Profiles:")
            for profile_name in hls_outputs.keys():
                profile = self.profiles[profile_name]
                logging.info(f"  - {profile_name}: {profile['width']}x{profile['height']} @ {profile['bitrate']}")

        logging.info(f"\nTest players:")
        logging.info(f"  - HLS: {self.output_dir}/hls_player.html")
        logging.info(f"  - DASH: {self.output_dir}/dash_player.html")
        logging.info("="*50)

def main():
    parser = argparse.ArgumentParser(description='HLS/DASH Video Transcoding Pipeline')
    parser.add_argument('input_file', help='Input video file path')
    parser.add_argument('-o', '--output', default='output', help='Output directory (default: output)')
    parser.add_argument('--segment-duration', type=int, default=10, help='Segment duration in seconds (default: 10)')

    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        logging.error(f"Input file not found: {args.input_file}")
        sys.exit(1)

    try:
        transcoder = VideoTranscoder(args.input_file, args.output)
        transcoder.segment_duration = args.segment_duration
        transcoder.process()
    except Exception as e:
        logging.error(f"Transcoding failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
