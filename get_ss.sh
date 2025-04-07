#!/bin/bash
set -x

. ./.env

VIDEOIDFILE="./youtube_video_id.txt"

VIDEO_ID=""
LAST_VIDEO_ID=""

# 1. 前回保存された ID を読み込む
if [[ -f "${VIDEOIDFILE}" ]]; then
  LAST_VIDEO_ID=$(cat "${VIDEOIDFILE}")
  echo "[INFO] 前回の videoId: ${LAST_VIDEO_ID}"
fi

# 2. そのIDが現在もライブ中か確認 消費クオータ=1
if [[ -n "${LAST_VIDEO_ID}" ]]; then
  RSP_API_VIDEOS=$(curl -s "https://www.googleapis.com/youtube/v3/videos?part=snippet,liveStreamingDetails&id=${LAST_VIDEO_ID}&key=${YOUTUBE_API_KEY}")
  echo "${RSP_API_VIDEOS}" > "${OUTPUT_PATH}/resp_api_videos.txt"
  IS_LIVE=$(cat "${OUTPUT_PATH}/resp_api_videos.txt" | jq -r '.items[0].snippet.liveBroadcastContent // "none"')

  if [[ "$IS_LIVE" == "live" ]]; then
    VIDEO_ID="${LAST_VIDEO_ID}"
    echo "[INFO] 継続中のライブ配信を検出: ${VIDEO_ID}"
  else
    echo "[INFO] 前回の配信は終了しています"
  fi
fi

# 3. それでもVIDEO_IDが空なら search APIで最新ライブを検索 消費クオータ=100
if [[ -z "${VIDEO_ID}" ]]; then
  RSP_API_SEARCH=$(curl -s "https://www.googleapis.com/youtube/v3/search?part=snippet&channelId=${CHANNEL_ID}&eventType=live&type=video&order=date&key=${YOUTUBE_API_KEY}")
  echo "${RSP_API_SEARCH}" > "${OUTPUT_PATH}/resp_api_search.txt"
  VIDEO_ID=$(cat  "${OUTPUT_PATH}/resp_api_search.txt" | jq -r '.items[0].id.videoId // empty')

  if [[ -n "${VIDEO_ID}" ]]; then
    echo "[INFO] 新しいライブ配信を検出: ${VIDEO_ID}"
  else
    echo "[ERROR] ライブ配信が見つかりませんでした。" >&2
    exit 1
  fi
fi

# 4. VIDEO_ID を保存
echo "${VIDEO_ID}" > "${VIDEOIDFILE}"
echo "[INFO] videoId を ${VIDEOIDFILE} に保存しました: ${VIDEO_ID}"




YOUTUBE_URL="https://www.youtube.com/watch?v=${VIDEO_ID}"
yt-dlp -g "${YOUTUBE_URL}" > "${OUTPUT_PATH}/streaming_url.txt"
STREAMING_URL=$(cat "${OUTPUT_PATH}/streaming_url.txt")

# 最新の m3u8 を curl で取得（キャッシュ無効化）
curl -s -H "Cache-Control: no-cache" "$STREAMING_URL" -o "${OUTPUT_PATH}/live.m3u8"

# 最新の.tsセグメントURLを取得
LATEST_TS=$(grep -oE 'https?://.*\.ts' "${OUTPUT_PATH}/live.m3u8" | tail -n 1)

echo "最新セグメント: $LATEST_TS"

# スクリーンショットを取得
ffmpeg -y -sseof -1.0 -i "$LATEST_TS" -frames:v 1 -q:v 2 "${OUTPUT_PATH}/snap.jpg"

python src/ytss.py
