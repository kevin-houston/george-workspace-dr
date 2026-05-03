#!/bin/bash
# Create file list
for f in segment_*.wav; do
    echo "file '$f'" >> list.txt
done

# Merge all segments
ffmpeg -y -f concat -safe 0 -i list.txt -c copy /workspace/group/podcast_feb25.wav

# Check result
ls -lh /workspace/group/podcast_feb25.wav
ffmpeg -i /workspace/group/podcast_feb25.wav 2>&1 | grep Duration

# Compress to MP3
ffmpeg -y -i /workspace/group/podcast_feb25.wav -codec:a libmp3lame -b:a 64k /workspace/group/podcast_feb25.mp3

ls -lh /workspace/group/podcast_feb25.mp3
