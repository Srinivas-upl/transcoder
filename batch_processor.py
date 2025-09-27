#!/usr/bin/env python3
"""
Batch Video Processing Service
Monitors input directory and processes new videos automatically
"""

import os
import time
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from video_transcoder import VideoTranscoder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/batch_processing.log'),
        logging.StreamHandler()
    ]
)

class VideoProcessingHandler(FileSystemEventHandler):
    def __init__(self, input_dir: str, output_base_dir: str):
        self.input_dir = Path(input_dir)
        self.output_base_dir = Path(output_base_dir)
        self.processing_queue = []
        self.processing_lock = threading.Lock()

        # Supported video formats
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}

        # Start processing thread
        self.processing_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.processing_thread.start()

    def on_created(self, event):
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.video_extensions:
                self.add_to_queue(file_path)

    def on_moved(self, event):
        if not event.is_directory:
            file_path = Path(event.dest_path)
            if file_path.suffix.lower() in self.video_extensions:
                self.add_to_queue(file_path)

    def add_to_queue(self, file_path: Path):
        """Add video file to processing queue"""
        with self.processing_lock:
            if file_path not in self.processing_queue:
                self.processing_queue.append(file_path)
                logging.info(f"Added to queue: {file_path.name}")

    def process_queue(self):
        """Process videos from queue"""
        while True:
            try:
                with self.processing_lock:
                    if not self.processing_queue:
                        time.sleep(5)
                        continue

                    video_file = self.processing_queue.pop(0)

                # Wait for file to be fully written (check file size stability)
                self.wait_for_stable_file(video_file)

                # Create output directory for this video
                video_name = video_file.stem
                video_output_dir = self.output_base_dir / video_name

                logging.info(f"Processing: {video_file.name} -> {video_output_dir}")

                # Process the video
                transcoder = VideoTranscoder(str(video_file), str(video_output_dir))
                transcoder.process()

                logging.info(f"✓ Completed processing: {video_file.name}")

            except Exception as e:
                logging.error(f"Error processing {video_file}: {e}")
                time.sleep(1)

    def wait_for_stable_file(self, file_path: Path, timeout: int = 300):
        """Wait for file to be completely written"""
        stable_duration = 0
        last_size = 0

        while stable_duration < 10:  # Wait for 10 seconds of stable size
            try:
                current_size = file_path.stat().st_size
                if current_size == last_size and current_size > 0:
                    stable_duration += 1
                else:
                    stable_duration = 0
                    last_size = current_size

                time.sleep(1)
                timeout -= 1

                if timeout <= 0:
                    logging.warning(f"Timeout waiting for stable file: {file_path}")
                    break

            except FileNotFoundError:
                logging.warning(f"File disappeared while waiting: {file_path}")
                return

class BatchProcessor:
    def __init__(self, input_dir: str = "input", output_dir: str = "output"):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)

        # Create directories
        self.input_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

        # Setup file watcher
        self.event_handler = VideoProcessingHandler(str(self.input_dir), str(self.output_dir))
        self.observer = Observer()
        self.observer.schedule(self.event_handler, str(self.input_dir), recursive=True)

    def start(self):
        """Start the batch processor"""
        logging.info(f"Starting batch processor...")
        logging.info(f"Watching directory: {self.input_dir.absolute()}")
        logging.info(f"Output directory: {self.output_dir.absolute()}")

        # Process any existing files
        self.process_existing_files()

        # Start watching for new files
        self.observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down batch processor...")
            self.observer.stop()

        self.observer.join()

    def process_existing_files(self):
        """Process any video files already in the input directory"""
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}

        for file_path in self.input_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                self.event_handler.add_to_queue(file_path)

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Batch Video Processing Service')
    parser.add_argument('-i', '--input', default='input', help='Input directory to watch (default: input)')
    parser.add_argument('-o', '--output', default='output', help='Output base directory (default: output)')

    args = parser.parse_args()

    processor = BatchProcessor(args.input, args.output)
    processor.start()

if __name__ == "__main__":
    main()
