import os
import time
import subprocess
import requests
import json
import tempfile
import yaml
from datetime import datetime, timedelta, timezone
# from pathlib import Path
import dotenv
from contextlib import suppress
import traceback

from pprint import pprint

# 環境変数を読み込み
dotenv.load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OUTPUT_PATH = os.getenv("OUTPUT_PATH")

def get_current_epoch():
    return int(time.time())

def fetch_channel_info(channel_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/channels"
        f"?part=snippet&id={channel_id}&key={YOUTUBE_API_KEY}"
    )
    resp = requests.get(url).json()
    with open(f"{OUTPUT_PATH}/resp_api_videos.txt", "w") as f:
        json.dump(resp, f)
    return resp.get("items", [{}])[0].get("snippet")

def fetch_video_status(video_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,liveStreamingDetails&id={video_id}&key={YOUTUBE_API_KEY}"
    )
    resp = requests.get(url).json()
    with open(f"{OUTPUT_PATH}/resp_api_videos.txt", "w") as f:
        json.dump(resp, f)
    return resp.get("items", [{}])[0].get("snippet", {}).get("liveBroadcastContent", "none")

def search_latest_live_video(chid:str, keywords=[]):
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&channelId={chid}&eventType=live&type=video&order=date&key={YOUTUBE_API_KEY}"
    )
    if keywords is not None and len(keywords)>0:
        url = f"{url}&q={keywords[0]}"
    resp = requests.get(url).json()
    with open(f"{OUTPUT_PATH}/resp_api_search.txt", "w") as f:
        json.dump(resp, f)
    items = resp.get("items", [])
    if len(items)<=0:
        return None
    for item in items:
        title = item["snippet"]["title"].lower()
        if all(keyword.lower() in title for keyword in keywords):
            return item
    return None

def get_streaming_url(youtube_url):
    result = subprocess.run(["yt-dlp", "-g", youtube_url], capture_output=True, text=True)
    streaming_url = result.stdout.strip()
    return streaming_url

def get_latest_ts_url(m3u8_url):
    resp = requests.get(m3u8_url, headers={"Cache-Control": "no-cache"})
    m3u8_path = f"{OUTPUT_PATH}/live.m3u8"
    with open(m3u8_path, "w") as f:
        f.write(resp.text)
    lines = resp.text.splitlines()
    ts_urls = [line for line in lines if line.endswith(".ts")]
    return ts_urls[-1] if ts_urls else None

def capture_screenshot(ts_url):
    tf = tempfile.mkstemp(prefix="snap_", suffix=".jpg", dir=OUTPUT_PATH, text=False)
    tfname = tf[-1]
    subprocess.run([
        "ffmpeg", "-y", "-sseof", "-1.0", "-i", ts_url,
        "-frames:v", "1", "-q:v", "2", tfname
    ], check=True)
    return tfname

def main():
    with open("./config.yml",'rb') as yamlfile: #非ASCIIを含むのでバイナリ
        config_in=yaml.safe_load(yamlfile)

    channelids=[_x['id'] for _x in config_in.get("channels",[])]

    channels=dict()
    config_out=dict()
    config_out['channels'] = channels
    for chid in channelids:
        ch=dict()
        channels[chid]=ch
        ch["id"]=chid
        snippet = fetch_channel_info(chid)
        if "customUrl" in snippet:
            ch["customUrl"] = snippet['customUrl']
        ch["title"] = snippet['title']

    control = config_out.get('control',{})
    config_out['control']=control
    for i, chid in enumerate(channelids):
        ch = channels.get(chid)
        # 予約チェック
        reserved_epoch = ch.get('reservation')
        if reserved_epoch:
            now = get_current_epoch()
            if now < reserved_epoch:
                jst_time = datetime.fromtimestamp(reserved_epoch, tz=timezone(timedelta(hours=9)))
                print(f"[INFO] {chid} 予約時刻(JST): {jst_time} まではスキップします。")
                continue
            del ch["reservation"]
        vid = None
        last_video_id = ch.get('video_id')
        if last_video_id:
            print(f"[INFO] {chid} 前回の videoId: {last_video_id}")
            if fetch_video_status(last_video_id) == "live":
                print(f"[INFO] {chid} 前回の配信は継続中: {last_video_id}")
                vid = last_video_id
            else:
                print(f"[INFO] {chid} 前回の配信は終了済: {last_video_id}")
                del ch['video_id']

        if not vid:
            vinf = search_latest_live_video(chid, config_in["channels"][i].get("keywords",[]))
            if vinf:
                vid = vinf["id"]["videoId"]
                print(f"[INFO] {chid} 新しいライブ配信を検出: {vid}")
                ch['video_id'] = vid
                ch['video_title'] = vinf["snippet"]["title"]
            else:
                print(f"[INFO] {chid} ライブ配信が見つかりませんでした。")
                next_epoch = get_current_epoch() + 28 * 60
                reserved_epoch = ch['reservation'] = next_epoch
                jst = datetime.now(timezone(timedelta(hours=9))) + timedelta(minutes=30)
                print(f"[INFO] {chid} 次回の実行予約時刻(JST): {jst.strftime('%Y-%m-%d %H:%M:%S')}")
                continue
        if vid:
            print(f"[INFO] {chid} 対象を確定しました: {vid}")
            break
    else:
        print(f"[INFO] 対象が見つかりませんでした")
        if "video_id" in control:
            del control["video_id"]
        if "video_url" in control:
            del control["video_url"]
        if "channel_id" in control:
            del control["channel_id"]
        if "channel_url" in control:
            del control["channel_url"]
        if "channel_name" in control:
            del control["channel_name"]
        if "stream_url" in control:
            del control["stream_url"]
        if "ts_url" in control:
            del control["ts_url"]
        if "channel_name" in control:
            del control["channel_name"]
        if "capture_file" in control:
            with suppress(FileNotFoundError):# なくてもエラーにしない
                os.remove(control["capture_file"])
            del control["capture_file"]

    control["video_id"] = vid
    control["video_title"] = ch["video_title"]
    control["video_url"] = f"https://youtube.com/watch?v={vid}"
    control["channel_id"] = chid
    control["channel_url"] = f'https://www.youtube.com/{ch["customUrl"] if "customUrl" in ch else "channel/"+ch["id"]}'
    control["channel_name"] = ch['title']
    control["stream_url"] = get_streaming_url(control['video_url'])
    latest_ts = get_latest_ts_url(control["stream_url"])
    if not latest_ts:
        print("[ERROR] .ts セグメントが取得できません")
        return
    control["ts_url"] = latest_ts

    print(f"[INFO] 最新セグメント: {latest_ts}")
    cap_filename = capture_screenshot(latest_ts)
    if "capture_file" in control:
        with suppress(FileNotFoundError):# なくてもエラーにしない
            os.remove(control["capture_file"])
    control["capture_file"] = cap_filename

    with open("./control.yml",'wb') as yamlfile: #非ASCIIを含むのでバイナリ
        yaml.safe_dump(config_out, yamlfile, encoding='utf-8', allow_unicode=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exception(e)
        exit(1)
