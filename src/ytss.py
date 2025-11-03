import os
import stat
import time
import subprocess
import shutil
import requests
import json
import tempfile
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import suppress
import traceback

from pprint import pprint

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OUTPUT_PATH = os.getenv("OUTPUT_PATH")
CONFIG_PATH = os.getenv("CONFIG_PATH","./config/config.yml")

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

def get_current_epoch():
    return int(time.time())

def fetch_channel_info(channel_id):
    print(f'[INFO] fetch channel info: {channel_id}')
    url = (
        f"{YOUTUBE_API_BASE}/channels"
        f"?part=snippet"
        f"&id={channel_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    resp = requests.get(url).json()
    with open(f"{OUTPUT_PATH}/resp_api_channels.txt", "w") as f:
        json.dump(resp, f)
    return resp.get("items", [{}])[0].get("snippet")

def fetch_video_status(video_id):
    print(f'[INFO] fetch video status: {video_id}')
    url = (
        f"{YOUTUBE_API_BASE}/videos"
        f"?part=snippet,liveStreamingDetails"
        f"&id={video_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    resp = requests.get(url).json()
    with open(f"{OUTPUT_PATH}/resp_api_videos.txt", "w") as f:
        json.dump(resp, f)
    if "error" in resp:
        print(f'[ERROR] {resp}')
        raise ValueError('Error Response in youtube/v3/videos')
    items = resp.get('items',[])
    if len(items) > 0:
        return items[0].get("snippet", {}).get("liveBroadcastContent", "none")
    return "none"

def search_latest_live_video(chid:str, keywords=[]):
    print(f'[INFO] search latest live video: {chid} {keywords}')
    url = (
        f"{YOUTUBE_API_BASE}/search"
        f"?part=snippet"
        f"&channelId={chid}"
        "&eventType=live"
        "&type=video"
        "&order=date"
        f"&key={YOUTUBE_API_KEY}"
    )
    if keywords is not None and len(keywords)>0:
        url = f"{url}&q={keywords[0]}"
    resp = requests.get(url).json()
    with open(f"{OUTPUT_PATH}/resp_api_search.txt", "w") as f:
        json.dump(resp, f)
    if "error" in resp:
        print(f'[ERROR] {resp}')
        raise ValueError('Error Response in youtube/v3/search')
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

def snapshot(ts_url):
    with tempfile.NamedTemporaryFile(prefix="snap_", suffix=".jpg", dir=OUTPUT_PATH, delete=False) as tmpf:
        tmpfpath = tmpf.name
    subprocess.run([
        "ffmpeg", "-y", "-sseof", "-1.0", "-i", ts_url,
        "-frames:v", "1", "-q:v", "2", tmpfpath
    ], check=True)
    # 一時ファイルのパーミッションをディレクトリにそろえる(maybe 600->644)
    dir_mode = os.stat(OUTPUT_PATH).st_mode
    no_exec_mode = dir_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.chmod(tmpfpath, no_exec_mode)
    return tmpfpath

def main():
    with open(CONFIG_PATH,'rb') as yamlfile: #非ASCIIを含むのでバイナリ
        config_in1={'definitions':yaml.safe_load(yamlfile)}
    ctrlpath = Path(OUTPUT_PATH).resolve().joinpath("control.yml")
    with open(ctrlpath,'rb') as yamlfile: #非ASCIIを含むのでバイナリ
        config_in2=yaml.safe_load(yamlfile)
    config_in = config_in1 | config_in2

    channeldefs=config_in.get("definitions",{}).get("channels",[])
    exports=config_in.get("definitions",{}).get("exports",[])
    channelids=[_x['id'] for _x in channeldefs]
    channels = config_in.get('channels',{})
    control = config_in.get('control',{})

    config_out=dict()
    config_out['channels'] = channels
    config_out['control'] = control
    for i, chid in enumerate(channelids):
        ch = channels.get(chid)
        # 予約チェック
        reserved_epoch = ch.get('reservation')
        if reserved_epoch:
            now = get_current_epoch()
            jst_time = datetime.fromtimestamp(reserved_epoch, tz=timezone(timedelta(hours=9)))
            if now < reserved_epoch:
                print(f"[INFO] {chid} 予約時刻(JST): {jst_time} まではスキップします。")
                continue
            print(f"[INFO] {chid} 予約時刻(JST): {jst_time} 到来。")
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
            vinf = search_latest_live_video(chid, channeldefs[i].get("keywords",[]))
            if vinf:
                vid = vinf["id"]["videoId"]
                print(f"[INFO] {chid} 新しいライブ配信を検出: {vid}")
                ch['video_id'] = vid
                ch['video_title'] = vinf["snippet"]["title"]
            else:
                print(f"[INFO] {chid} ライブ配信が見つかりませんでした。")
                next_epoch = get_current_epoch() + 28 * 60
                jst = datetime.now(timezone(timedelta(hours=9))) + timedelta(minutes=30)
                ch['reservation'] = next_epoch
                ch['reservation_pretty'] = jst
                print(f"[INFO] {chid} 次回の実行予約時刻(JST): {jst.strftime('%Y-%m-%d %H:%M:%S')}")
                continue
        if vid:
            print(f"[INFO] {chid} 対象を確定しました: {vid}")
            ch_snippet = fetch_channel_info(chid)
            ch["id"]=chid
            ch["title"] = ch_snippet['title']
            if "customUrl" in ch_snippet:
                ch["customUrl"] = ch_snippet['customUrl']
            else:
                if "customUrl" in ch:
                    del ch["customUrl"]
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
                print(f'[INFO] removing file: {control["capture_file"]}')
                os.remove(control["capture_file"])
            del control["capture_file"]
        with open(ctrlpath,'wb') as yamlfile: #非ASCIIを含むのでバイナリ
            yaml.safe_dump(config_out, yamlfile, encoding='utf-8', allow_unicode=True)
        for exp in exports:
            exp_path=Path(exp["path"]).resolve()
            exp_delete=exp.get("delete_if_offline", False)
            if exp_delete:
                with suppress(FileNotFoundError):# なくてもエラーにしない
                    print(f'[INFO] removing expport file: {exp_path}')
                    os.remove(exp_path)
        return

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
    snap_path = snapshot(latest_ts)
    if "snap_file" in control:
        with suppress(FileNotFoundError):# なくてもエラーにしない
            print(f'[INFO] removing file: {control["snap_file"]}')
            os.remove(Path(OUTPUT_PATH).joinpath(control["snap_file"]).resolve())
    control["snap_file"] = Path(snap_path).name

    with open(ctrlpath,'wb') as yamlfile: #非ASCIIを含むのでバイナリ
        yaml.safe_dump(config_out, yamlfile, encoding='utf-8', allow_unicode=True)

    # エクスポート(指定があった場合)
    # 既存の場合はアトミックに置換
    for exp in exports:
        exp_path=Path(exp["path"]).resolve()
        exp_dir=exp_path.joinpath("..").resolve()
        with tempfile.NamedTemporaryFile(dir=exp_dir, delete=False) as tmpf:
            exp_tmpf = tmpf.name
        try:
            shutil.copy(snap_path, exp_tmpf) # エクスポート先dirの一時ファイルにコピー
            shutil.copymode(snap_path, exp_tmpf) # パーミッションをそろえる(maybe 600->644)
            os.replace(exp_tmpf, exp_path) # エクスポート先をアトミックに置換
        except:
            os.remove(exp_tmpf)
            raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exception(e)
        exit(1)
