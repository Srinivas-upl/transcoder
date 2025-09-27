# HLS/DASH Video Transcoding Pipeline

A complete open-source solution for converting videos into adaptive bitrate HLS and DASH streams with automatic chunking and segmentation.

## 🚀 Features

- **Multi-format Support**: MP4, AVI, MOV, MKV, WMV, FLV, WebM, M4V
- **Adaptive Bitrate**: 5 quality levels (240p to 1080p)
- **HLS & DASH Output**: Industry-standard streaming formats
- **Automatic Chunking**: Configurable segment duration
- **Batch Processing**: Watch directory for new files
- **Docker Support**: Easy containerized deployment
- **Web Interface**: Monitor processing and test players
- **Self-hosted CDN**: NGINX-based content delivery

## 📁 Project Structure

```
hls-dash-transcoding-pipeline/
├── video_transcoder.py      # Main transcoding script
├── batch_processor.py       # Batch processing service
├── docker-compose.yml       # Docker orchestration
├── Dockerfile              # Container definition
├── requirements.txt        # Python dependencies
├── setup.sh               # Easy setup script
├── config/
│   └── nginx.conf         # NGINX configuration
├── web/
│   └── index.html         # Web monitoring interface
├── input/                 # Drop videos here for processing
├── output/               # Generated streams and players
├── logs/                 # Processing logs
├── scripts/              # Additional scripts
└── docs/                 # Documentation
```

## ⚡ Quick Start

### Option 1: Direct Python Usage

```bash
# Install FFmpeg (Ubuntu/Debian)
sudo apt update
sudo apt install ffmpeg python3-pip

# Install Python dependencies
pip3 install -r requirements.txt

# Process a single video
python3 video_transcoder.py input/your_video.mp4

# Start batch processor (watches input folder)
python3 batch_processor.py
```

### Option 2: Docker Deployment (Recommended)

```bash
# Start all services
docker-compose up --build

# Access web interface at http://localhost:8080/admin
```

### Option 3: Automated Setup

```bash
# Make setup script executable
chmod +x setup.sh

# Run setup
./setup.sh
```

## 🎯 Usage Examples

### Single Video Processing

```bash
# Basic usage
python3 video_transcoder.py input/sample_video.mp4

# Custom output directory
python3 video_transcoder.py input/video.mp4 -o output/custom_folder

# Custom segment duration (6 seconds)
python3 video_transcoder.py input/video.mp4 --segment-duration 6
```

### Batch Processing

```bash
# Start batch processor
python3 batch_processor.py

# Copy videos to input folder (processing starts automatically)
cp *.mp4 input/
```

## 📊 Output Structure

After processing, each video generates:

```
output/video_name/
├── hls/
│   ├── master.m3u8          # Master playlist
│   ├── 1080p/
│   │   ├── playlist.m3u8    # Quality-specific playlist
│   │   └── segment_*.ts     # Video chunks (10s each)
│   ├── 720p/
│   ├── 480p/
│   ├── 360p/
│   └── 240p/
├── dash/
│   ├── manifest.mpd         # DASH manifest
│   └── segments/            # DASH segments
├── hls_player.html          # Test HLS player
└── dash_player.html         # Test DASH player
```

## 🔧 Quality Profiles

| Profile | Resolution | Video Bitrate | Audio Bitrate | Use Case |
|---------|------------|---------------|---------------|----------|
| 1080p   | 1920×1080  | 5M           | 192k         | Full HD |
| 720p    | 1280×720   | 3M           | 128k         | HD streaming |
| 480p    | 854×480    | 1.5M         | 128k         | Standard quality |
| 360p    | 640×360    | 800k         | 96k          | Mobile standard |
| 240p    | 426×240    | 400k         | 64k          | Low bandwidth |

## 🐳 Docker Services

- **transcoder**: FFmpeg-based video processing
- **nginx**: Serves HLS/DASH content with CORS support
- **minio**: Optional S3-compatible object storage

## 🌐 Web Interface

Access the monitoring dashboard at:
- **Docker**: `http://localhost:8080/admin`
- **Local**: Open `web/index.html` in browser

Features:
- Upload progress tracking
- Processing status monitoring
- Video library with quality selection
- Real-time logs
- Direct player links

## ⚙️ Configuration

### Custom Transcoding Profiles

```python
# Add 4K profile
transcoder.profiles["4K"] = {
    "width": 3840, "height": 2160, 
    "bitrate": "15M", "audio_bitrate": "256k"
}

# Remove unnecessary quality
del transcoder.profiles["240p"]
```

### Segment Duration

- **2-6s**: Lower latency, more files
- **10-30s**: Better compression, fewer files
- **Recommended**: 6-10 seconds

### Hardware Acceleration

```bash
# NVIDIA GPU (if available)
ffmpeg -hwaccel cuda -c:v h264_nvenc ...

# Intel Quick Sync
ffmpeg -hwaccel qsv -c:v h264_qsv ...
```

## 📝 Testing Streams

### HLS Player
```html
<script src="https://vjs.zencdn.net/8.5.2/video.min.js"></script>
<video-js controls>
    <source src="output/video/hls/master.m3u8" type="application/x-mpegURL">
</video-js>
```

### DASH Player
```html
<script src="https://cdn.dashjs.org/latest/dash.all.min.js"></script>
<video id="player" controls></video>
<script>
    dashjs.MediaPlayer().create().initialize(
        document.querySelector("#player"), 
        "output/video/dash/manifest.mpd"
    );
</script>
```

## 🔍 Monitoring & Logs

- **Processing logs**: `logs/transcoding.log`
- **Batch processing**: `logs/batch_processing.log`
- **NGINX access**: Check Docker logs
- **Real-time**: Web interface dashboard

## 🛠️ System Requirements

- **CPU**: Multi-core recommended (transcoding is CPU-intensive)
- **RAM**: 4GB minimum, 8GB+ for concurrent processing
- **Storage**: SSD recommended for faster I/O
- **FFmpeg**: Version 4.0+ required

## 🔐 Production Deployment

### Security
- Use HTTPS for streaming endpoints
- Implement authentication for upload endpoints
- Add rate limiting
- Input validation

### Scaling
- Multiple transcoding workers
- Load balancers for API servers
- Database read replicas
- CDN edge nodes

### Monitoring
```yaml
# Add to docker-compose.yml
prometheus:
  image: prom/prometheus
  ports: ["9090:9090"]

grafana:
  image: grafana/grafana
  ports: ["3000:3000"]
```

## 🐛 Troubleshooting

### Common Issues

1. **FFmpeg not found**
   ```bash
   # Ubuntu/Debian
   sudo apt install ffmpeg

   # macOS
   brew install ffmpeg
   ```

2. **Permission denied**
   ```bash
   chmod +x *.py
   sudo chown -R $USER:$USER output/
   ```

3. **CORS errors**
   - Check NGINX CORS configuration
   - Serve from same domain

4. **Large file processing**
   - Increase segment duration
   - Use hardware acceleration
   - Process during off-peak hours

## 🚀 Performance Optimization

### Faster Encoding (Lower Quality)
```python
transcoder.profiles["720p"]["preset"] = "ultrafast"
```

### Better Quality (Slower)
```python
transcoder.profiles["720p"]["preset"] = "slow"
transcoder.profiles["720p"]["crf"] = "18"  # Lower = better
```

## 📄 License

Open source - modify and distribute freely.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Make improvements
4. Submit pull request

## 📞 Support

For issues and feature requests:
- Create detailed GitHub issues
- Include log files and system information
- Describe reproduction steps

---

**Ready to start streaming? Drop your videos in the `input/` folder and watch the magic happen! 🎬✨**
# transcoder
