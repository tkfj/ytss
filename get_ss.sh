#!/bin/bash
set -x

. ./.env

curl -s "https://www.googleapis.com/youtube/v3/search?part=snippet&channelId=${CHANNEL_ID}&eventType=live&type=video&order=date&key=${YOUTUBE_API_KEY}" > ${OUTPUT_PATH}/youtube_api_json.txt
cat ${OUTPUT_PATH}/youtube_api_json.txt | jq -r '.items[0].id.videoId' > ${OUTPUT_PATH}/youtube_channel_id.txt
CHANNEL_ID=$(cat ${OUTPUT_PATH}/youtube_channel_id.txt)
YOUTUBE_URL="https://www.youtube.com/watch?v=${CHANNEL_ID}"
yt-dlp -g "${YOUTUBE_URL}" > ${OUTPUT_PATH}/streaming_url.txt
STREAMING_URL=$(cat ${OUTPUT_PATH}/streaming_url.txt)

# 最新の m3u8 を curl で取得（キャッシュ無効化）
curl -s -H "Cache-Control: no-cache" "$STREAMING_URL" -o ${OUTPUT_PATH}/live.m3u8

# 最新の.tsセグメントURLを取得
LATEST_TS=$(grep -oE 'https?://.*\.ts' ${OUTPUT_PATH}/live.m3u8 | tail -n 1)

echo "最新セグメント: $LATEST_TS"

# スクリーンショットを取得
ffmpeg -y -sseof -1.0 -i "$LATEST_TS" -frames:v 1 -q:v 2 "${OUTPUT_PATH}/snap.jpg"

# ffmpeg -y \
#   -fflags \
#   nobuffer \
#   -flags \
#   -low-delay \
#   -analyzeduration 0 \
#   -probesize 32 \
#   -i "${SEGMENT_URL}" \
#   -frames:v 1 \
#   -q:v 2 \
#   "${OUTPUT_PATH}/snap.jpg"

python src/ytss.py
