#!/bin/bash

# Video Transcoding Pipeline Setup Script
echo "🎥 Setting up HLS/DASH Video Transcoding Pipeline..."
echo ""

# Create directories
mkdir -p input output logs

# Check if FFmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg not found. Installing..."

    # Detect OS and install FFmpeg
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt &> /dev/null; then
            sudo apt update && sudo apt install -y ffmpeg
        elif command -v yum &> /dev/null; then
            sudo yum install -y ffmpeg
        elif command -v pacman &> /dev/null; then
            sudo pacman -S ffmpeg
        else
            echo "❌ Please install FFmpeg manually for your Linux distribution"
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install ffmpeg
        else
            echo "❌ Please install Homebrew first: https://brew.sh/"
            exit 1
        fi
    else
        echo "❌ Unsupported OS. Please install FFmpeg manually:"
        echo "   Windows: https://ffmpeg.org/download.html"
        echo "   Linux: sudo apt install ffmpeg (Ubuntu/Debian)"
        echo "   macOS: brew install ffmpeg"
        exit 1
    fi
fi

echo "✅ FFmpeg found: $(ffmpeg -version | head -n1)"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.6+"
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Install Python dependencies
echo "📦 Installing Python dependencies..."
if pip3 install -r requirements.txt; then
    echo "✅ Dependencies installed successfully"
else
    echo "⚠️  Some dependencies failed to install. Trying alternative method..."
    python3 -m pip install requests pathlib watchdog
fi

# Make scripts executable
chmod +x *.py
echo "✅ Scripts made executable"

# Test FFmpeg
echo "🧪 Testing FFmpeg..."
if ffmpeg -version &> /dev/null; then
    echo "✅ FFmpeg test passed"
else
    echo "❌ FFmpeg test failed"
    exit 1
fi

# Create sample directory structure
echo "📁 Creating sample structure..."
echo "# Sample video file" > input/README.txt
echo "Place your video files here for processing" >> input/README.txt

echo "# Processed videos appear here" > output/README.txt
echo "Each video gets its own folder with HLS/DASH streams" >> output/README.txt

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📋 Next steps:"
echo "  1. Copy video files to 'input/' directory"
echo "  2. Run single video: python3 video_transcoder.py input/video.mp4"
echo "  3. Run batch processor: python3 batch_processor.py"
echo "  4. Or use Docker: docker-compose up --build"
echo ""
echo "🌐 Access points:"
echo "  - Web interface: http://localhost:8080/admin (Docker)"
echo "  - Local web: Open web/index.html in browser"
echo ""
echo "📊 Monitor logs:"
echo "  - tail -f logs/transcoding.log"
echo "  - tail -f logs/batch_processing.log"
echo ""
echo "📚 Read README.md for detailed instructions"
echo ""
echo "🚀 Ready to transcode! Drop videos in input/ and start processing!"
