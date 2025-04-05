#!/bin/bash
set -x

. ./.env

curl -s "https://www.googleapis.com/youtube/v3/search?part=snippet&channelId=${CHANNEL_ID}&eventType=live&type=video&order=date&key=${YOUTUBE_API_KEY}" > ${OUTPUT_PATH}/youtube_api_json.txt
cat ${OUTPUT_PATH}/youtube_api_json.txt | jq -r '.items[0].id.videoId' > ${OUTPUT_PATH}/youtube_channel_id.txt
CHANNEL_ID=$(cat ${OUTPUT_PATH}/youtube_channel_id.txt)
YOUTUBE_URL="https://www.youtube.com/watch?v=${CHANNEL_ID}"
yt-dlp -g "${YOUTUBE_URL}" > ${OUTPUT_PATH}/streaming_url.txt
STREAMING_URL=$(cat ${OUTPUT_PATH}/streaming_url.txt)

ffmpeg -y \
  -analyzeduration 10M \
  -probesize 100M \
  -i "${STREAMING_URL}" \
  -frames:v 1 \
  -q:v 2 \
  "${OUTPUT_PATH}/snap.jpg"

python src/ytss.py
