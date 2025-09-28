import subprocess
from pathlib import Path
import ffmpeg


def transcode_to_multibitrate(input_file, output_dir):
    ladder = [
        {'name': '240p', 'width': 426, 'height': 240, 'bitrate': '400k', 'maxrate': '450k', 'bufsize': '600k'},
        {'name': '360p', 'width': 640, 'height': 360, 'bitrate': '800k', 'maxrate': '900k', 'bufsize': '1200k'},
        {'name': '480p', 'width': 854, 'height': 480, 'bitrate': '1500k', 'maxrate': '1650k', 'bufsize': '2100k'},
        {'name': '720p', 'width': 1280, 'height': 720, 'bitrate': '3000k', 'maxrate': '3300k', 'bufsize': '4200k'},
        {'name': '1080p', 'width': 1920, 'height': 1080, 'bitrate': '5000k', 'maxrate': '5500k', 'bufsize': '7500k'},
    ]

    input_stream = ffmpeg.input(str(input_file))

    # Probe the input file to check for audio streams
    try:
        probe = ffmpeg.probe(str(input_file))
        has_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])
    except Exception:
        has_audio = False

    # Create filter_complex for scaling video streams
    filter_parts = []
    for i, level in enumerate(ladder):
        filter_parts.append(f'[0:v]scale={level["width"]}:{level["height"]}[v{i}]')
    filter_complex = ';'.join(filter_parts)

    # var_stream_map pairs each video stream with audio (if available)
    if has_audio:
        # For HLS with audio, we need to map each video stream with a separate audio stream
        # But since we only have one audio input, we reference it multiple times
        var_stream_map = ' '.join(f'v:{i},a:{i}' for i in range(len(ladder)))
    else:
        var_stream_map = ' '.join(f'v:{i}' for i in range(len(ladder)))
        print("Warning: Input video has no audio stream. Creating video-only HLS streams.")

    # Prepare output paths and ensure directories exist
    output_dir = Path(output_dir)
    hls_dir = output_dir / 'hls'
    hls_dir.mkdir(parents=True, exist_ok=True)

    # For HLS master playlist, use just the filename (FFmpeg will create it in the same directory as variants)
    master_playlist_name = 'master.m3u8'
    variant_playlist_pattern = str(hls_dir / 'stream_%v.m3u8')
    segment_filename_pattern = str(hls_dir / 'segment_%v_%03d.ts')

    # Build the command manually using ffmpeg.run() to have better control
    args = [
        'ffmpeg',
        '-i', str(input_file),
        '-filter_complex', filter_complex,
        '-y'  # overwrite output
    ]

    # Add map arguments for each video stream
    for i in range(len(ladder)):
        args.extend(['-map', f'[v{i}]'])

    # Add audio map if present - map the same audio stream multiple times
    if has_audio:
        for i in range(len(ladder)):
            args.extend(['-map', '0:a'])

    # Add video encoding options for each stream
    for i, level in enumerate(ladder):
        args.extend([f'-c:v:{i}', 'libx264'])
        args.extend([f'-b:v:{i}', level['bitrate']])
        args.extend([f'-maxrate:{i}', level['maxrate']])
        args.extend([f'-bufsize:{i}', level['bufsize']])
        args.extend([f'-profile:v:{i}', 'main'])

    # Add common encoding options
    args.extend([
        '-preset', 'fast',
        '-g', '48',
        '-sc_threshold', '0'
    ])

    # Add audio options if present - apply to all audio streams
    if has_audio:
        for i in range(len(ladder)):
            args.extend([f'-c:a:{i}', 'aac'])
            args.extend([f'-b:a:{i}', '128k'])
            args.extend([f'-ac:{i}', '2'])
            args.extend([f'-ar:{i}', '48000'])

    # Add HLS options
    args.extend([
        '-f', 'hls',
        '-hls_time', '6',
        '-hls_playlist_type', 'vod',
        '-hls_segment_filename', segment_filename_pattern,
        '-var_stream_map', var_stream_map,
        '-master_pl_name', master_playlist_name,
        variant_playlist_pattern
    ])

    # Run the HLS transcoding command
    print("Running FFmpeg command for HLS...")
    print(f"Command: {' '.join(args)}")  # Debug: show the actual command
    try:
        import subprocess
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        print(f"HLS transcoding complete.\nMaster playlist location: {hls_dir / master_playlist_name}")

        # Verify master playlist was created
        master_playlist_path = hls_dir / master_playlist_name
        if master_playlist_path.exists():
            print(f"✓ Master playlist created successfully: {master_playlist_path}")
            # Show first few lines of master playlist for verification
            with open(master_playlist_path, 'r') as f:
                lines = f.readlines()[:10]
                print("Master playlist content preview:")
                for line in lines:
                    print(f"  {line.rstrip()}")
        else:
            print(f"⚠ Warning: Master playlist not found at {master_playlist_path}")
            # List what files were actually created
            print("Files created in HLS directory:")
            for file in sorted(hls_dir.glob('*')):
                print(f"  {file.name}")

    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error occurred during HLS transcoding:")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        raise

    # Generate DASH manifest
    print("Generating DASH manifest...")
    try:
        generate_dash_manifest(input_file, output_dir, ladder, has_audio)
        print(f"DASH transcoding complete.\nMPD manifest location: {output_dir / 'dash' / 'manifest.mpd'}")
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error occurred during DASH transcoding:")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        raise


def generate_dash_manifest(input_file, output_dir, ladder, has_audio):
    """Generate DASH manifest and segments"""

    # Create DASH output directory
    dash_dir = output_dir / 'dash'
    dash_dir.mkdir(parents=True, exist_ok=True)

    # Create filter_complex for scaling video streams
    filter_parts = []
    for i, level in enumerate(ladder):
        filter_parts.append(f'[0:v]scale={level["width"]}:{level["height"]}[v{i}]')
    filter_complex = ';'.join(filter_parts)

    # DASH output configuration - use simpler template names
    dash_manifest = dash_dir / 'manifest.mpd'

    # Build the DASH command manually
    args = [
        'ffmpeg',
        '-i', str(input_file),
        '-filter_complex', filter_complex,
        '-y'  # overwrite output
    ]

    # Add map arguments for each video stream
    for i in range(len(ladder)):
        args.extend(['-map', f'[v{i}]'])

    # Add audio map if present
    if has_audio:
        args.extend(['-map', '0:a'])

    # Add video encoding options for each stream
    for i, level in enumerate(ladder):
        args.extend([f'-c:v:{i}', 'libx264'])
        args.extend([f'-b:v:{i}', level['bitrate']])
        args.extend([f'-maxrate:{i}', level['maxrate']])
        args.extend([f'-bufsize:{i}', level['bufsize']])
        args.extend([f'-profile:v:{i}', 'main'])

    # Add common encoding options
    args.extend([
        '-preset', 'fast',
        '-g', '48',
        '-sc_threshold', '0'
    ])

    # Add audio options if present
    if has_audio:
        args.extend([
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ac', '2',
            '-ar', '48000'
        ])

    # Add DASH options with simpler configuration
    args.extend([
        '-f', 'dash',
        '-seg_duration', '6',
        str(dash_manifest)
    ])

    print(f"DASH Command: {' '.join(args)}")  # Debug: show the actual command
    import subprocess
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"DASH FFmpeg command failed with exit code {e.returncode}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")

        # Try a fallback approach with even simpler DASH options
        print("Trying fallback DASH configuration...")
        simple_args = [
            'ffmpeg',
            '-i', str(input_file),
            '-filter_complex', filter_parts[0],  # Just use one resolution for fallback
            '-map', '[v0]',
            '-c:v', 'libx264',
            '-b:v', ladder[0]['bitrate'],
            '-preset', 'fast',
            '-f', 'dash',
            '-y',
            str(dash_manifest)
        ]

        try:
            result = subprocess.run(simple_args, capture_output=True, text=True, check=True)
            print("Fallback DASH generation succeeded with single bitrate")
        except subprocess.CalledProcessError as e2:
            print(f"Fallback DASH also failed: {e2.stderr}")
            raise e  # Raise the original error


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Multi-bitrate HLS and DASH Transcoder Script")
    parser.add_argument('input_file', type=Path, help="Path to input video file")
    parser.add_argument('output_dir', type=Path, help="Output directory path for manifest and segments")
    parser.add_argument('--format', choices=['hls', 'dash', 'both'], default='both',
                        help="Output format: 'hls' for HLS only, 'dash' for DASH only, 'both' for both formats (default: both)")
    args = parser.parse_args()

    if args.format in ['hls', 'both']:
        transcode_to_multibitrate(args.input_file, args.output_dir)
    elif args.format == 'dash':
        # For DASH-only, we still need to probe for audio
        try:
            probe = ffmpeg.probe(str(args.input_file))
            has_audio = any(stream['codec_type'] == 'audio' for stream in probe['streams'])
        except Exception:
            has_audio = False

        ladder = [
            {'name': '240p', 'width': 426, 'height': 240, 'bitrate': '400k', 'maxrate': '450k', 'bufsize': '600k'},
            {'name': '360p', 'width': 640, 'height': 360, 'bitrate': '800k', 'maxrate': '900k', 'bufsize': '1200k'},
            {'name': '480p', 'width': 854, 'height': 480, 'bitrate': '1500k', 'maxrate': '1650k', 'bufsize': '2100k'},
            {'name': '720p', 'width': 1280, 'height': 720, 'bitrate': '3000k', 'maxrate': '3300k', 'bufsize': '4200k'},
            {'name': '1080p', 'width': 1920, 'height': 1080, 'bitrate': '5000k', 'maxrate': '5500k',
             'bufsize': '7500k'},
        ]

        if not has_audio:
            print("Warning: Input video has no audio stream. Creating video-only DASH streams.")

        args.output_dir.mkdir(parents=True, exist_ok=True)
        print("Generating DASH manifest...")
        try:
            generate_dash_manifest(args.input_file, args.output_dir, ladder, has_audio)
            print(f"DASH transcoding complete.\nMPD manifest location: {args.output_dir / 'dash' / 'manifest.mpd'}")
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error occurred during DASH transcoding:")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            raise