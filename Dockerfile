# Use a base image that already has both FFmpeg and Python
FROM linuxserver/ffmpeg:latest

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Install Python and pip
RUN apt-get update && apt install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy scripts
COPY video_transcoder.py .
COPY batch_processor.py .

# Create directories
RUN mkdir -p input output logs

# Make scripts executable
RUN chmod +x *.py

CMD ["python3", "-u", "batch_processor.py"]
