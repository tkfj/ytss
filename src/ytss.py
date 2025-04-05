import os
import json

from typing import List, Tuple, Dict, Set, Any
from pprint import pprint
from collections import defaultdict

import requests
import datetime
import dotenv
import slack_sdk
import decimal
import math

from PIL import Image
from io import BytesIO
def prepare_slack():
    global slack_cli
    global slack_bot_user_id
    global slack_ch_id
    if slack_cli is None:
        slack_cli = slack_sdk.WebClient(token=slack_token)
    if slack_bot_user_id is None:
        resp_a = slack_cli.auth_test()
        slack_bot_user_id = resp_a["user_id"]
    print(f'BotのユーザーID: {slack_bot_user_id}')

    if slack_ch_id is None:
        resp_C=slack_cli.conversations_list()
        for channel in resp_C["channels"]:
            if f'#{channel["name"]}'==slack_ch_nm:
                slack_ch_id = channel['id']
                break
        else:
            raise ValueError('チャンネルIDを特定できない')
    print(f'チャンネルID: {slack_ch_id}')

def send_slack_text(text: str, blocks:List[Dict[str,any]] = None, event_type: str = None, event_payload: any = None) -> float:
    msgjson={
        'channel': slack_ch_id,
        'text': text,
    }
    if blocks is not None:
        msgjson['blocks']=blocks
        pprint(blocks)
    if event_type is not None:
        assert event_payload is not None, "event_typeを指定する場合event_payloadは必須です"
        msgjson['metadata']={'event_type': event_type}
    if event_payload is not None:
        assert event_type is not None, "event_payloadを指定する場合event_typeは必須です"
        msgjson['metadata']['event_payload']=event_payload

    resp_p = slack_cli.chat_postMessage(**msgjson)
    post_ts=resp_p["ts"]
    print(f'送信成功: {post_ts}')
    return post_ts

def send_slack_images(
        files:List[bytes],
        file_names:List[str] = None,
        file_mimetypes:List[str] = None,
        file_titles:List[str] = None,
        file_alts:List[str] = None,
    ) -> Tuple[str, str]: #(file_id, url_private)
        slack_up_files:List[str, str]=list()
        for i, file in enumerate(files):
            slack_get_up_params={
                'filename': upload_fname,
                'length': len(bytes_img_up),
            }
            if file_names is not None:
                slack_get_up_params['filename'] = file_names[i]
            if file_alts is not None:
                slack_get_up_params['alt_text'] = file_alts[i]

            resp_up_info = slack_cli.files_getUploadURLExternal(**slack_get_up_params)
            print(resp_up_info)
            print(f'{resp_up_info.status_code} {resp_up_info["ok"]}')
            print(resp_up_info['upload_url'], resp_up_info['file_id'])
            slack_up_files.append({'id':resp_up_info['file_id']})
            if file_titles is not None:
                slack_up_files[i]['title'] = file_titles[i]
            slack_post_headers={
                'Content-Length': str(len(file)),
            }
            if file_mimetypes is not None:
                slack_post_headers['Content-Type'] = file_mimetypes[i]
            resp_put = requests.post(
                resp_up_info['upload_url'],
                headers = slack_post_headers,
                data = file,
            )
            print(resp_put)
            print(f'{resp_put.status_code} {resp_put.reason}')
            resp_put.raise_for_status()
        resp_compl = slack_cli.files_completeUploadExternal(
            files = slack_up_files,
            # channel_id = slack_ch_id,
        )
        print(resp_compl)
        return [(x['id'],x['url_private'],) for x in resp_compl['files']]

def delete_slack_same_titles(event_type: str, post_ts: float=None, check_limit:int = 10):
    resp_h = slack_cli.conversations_history(
        channel=slack_ch_id,
        limit=check_limit, # 直近N件以内に同じタイトルがあれば削除
        include_all_metadata=True,
    ) #TODO post_tsがあるばあい、それをlatestとして指定する
    past_messages = resp_h["messages"]

    for past_msg in past_messages:
        # print(past_msg)
        past_user = past_msg.get("user", "system/unknown")
        past_ts = past_msg.get("ts")
        # print(f"{i}. ユーザー: {user}, 時間: {ts}, メッセージ: {text}")
        #消さない条件
        if past_user != slack_bot_user_id: #ユーザーが異なる
            # print("skip: user")
            continue
        if post_ts is not None and past_ts >= post_ts: #tsが指定されていて、それと同じか新しい
            # print("skip: ts")
            continue
        if event_type is not None and past_msg.get('metadata',{}).get('event_type') != event_type: #posttypeが異なる
            # print(f"skip: event_type me: {event_type}   you: {past_msg.get('metadata',{}).get('event_type')}")
            continue
        #ここに到達したら削除対象
        #ユーザーが同一
        #ぽstTypeが一致
        #TSがあった場合、それより古い

        resp_d = slack_cli.chat_delete(
            channel=slack_ch_id,
            ts=past_ts
        )
        if resp_d["ok"]:
            print(f'メッセージ削除成功: {past_ts}')
        else:
            print(f'メッセージ削除失敗??: {past_ts}')


def send_slack(
        text:str,
        blocks:List[Dict[str,any]] = None,
        header:str = None,
        footer:str|List[Dict[str,any]] = None,
        event_type:str = None,
        event_payload:any = None,
        remove_past:int = 0,
    )->None:
    prepare_slack()
    blocks_fix:List[any] = None
    if blocks is not None and len(blocks)>0:
        blocks_fix=blocks.copy()
    else:
        blocks_fix=[
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": text,
                    "emoji": True
                }
            }
        ]
    if header is not None:
        blocks_fix.insert(0, {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header,
                "emoji": True
            }
        })
    if footer is not None:
        if isinstance(footer, str):
            blocks_fix.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": footer,
                }]
            })
        elif isinstance(footer, dict):
            blocks_fix.append({
                "type": "context",
                "elements": [footer]
            })
        else:
            raise ValueError(f'invalid footer type: {type(footer)}')
    try:
        post_ts = send_slack_text(text, blocks_fix, event_type=event_type, event_payload=event_payload)
        if remove_past > 0:
            delete_slack_same_titles(event_type, post_ts=post_ts, check_limit=remove_past)

    except slack_sdk.errors.SlackApiError as e:
        print("APIエラー:", e.response["error"])
        raise e
    return post_ts

dotenv.load_dotenv()

slack_token = os.environ['SLACK_TOKEN']
slack_ch_nm = os.environ['SLACK_CH_NM']
slack_footer = os.environ['SLACK_FOOTER']
slack_cli = None
slack_bot_user_id = None
slack_ch_id = None

slack_meta_event_type_lvcm = 'fjworks_livecamera'

prepare_slack()
slack_past_msgs_ts=f'{datetime.datetime.now(datetime.timezone.utc).timestamp() - 24 * 60 * 60: .6f}'
# print('past' , past_msgs_ts)
past_msgs_resp=slack_cli.conversations_history(
    channel=slack_ch_id,
    include_all_metadata=True,
    inclusive=True,
    limit=999, #ページングしない最大は999らしい?
    oldest=slack_past_msgs_ts,
)

ssimg:Image = Image.open("/app/shared/snap.jpg")

img_mimetype_out='image/jpg'
upload_fname=f'livecam.jpg'

buf_img_up=BytesIO()
img_up=ssimg.save(buf_img_up, format='JPEG')
buf_img_up.seek(0)
bytes_img_up=buf_img_up.read()

prepare_slack()

uploaded_files=send_slack_images(
    [bytes_img_up],
    [upload_fname],
    [img_mimetype_out],
    ['ライブカメラ'],
    ['ライブカメラ'],
)
slack_blocks:List[Dict[str,any]] = list()
slack_blocks.extend([{
    "type": "image",
    "slack_file": {'id': fid},
    "alt_text":'ライブカメラ',
} for (fid, furl) in uploaded_files])
slack_header=None
slack_footerz={
    "type": "mrkdwn",
    "text": slack_footer,
}
slack_text="ライブカメラ"
slack_meta={
     'basetime':f'xxxx',
}
import time
for fid, furl in uploaded_files:
    waittime=2.5
    while True:
        # print(fid,furl)
        resp_fs=slack_cli.files_info(file=fid)
        if 'original_w' in resp_fs['file'] and 'original_h' in resp_fs['file']: #非同期アップロードが完了した時に設定されると思われる属性ができるまで待つ
            break
        time.sleep(waittime)
        # waittime=waittime*2
post_ts=send_slack(slack_text, slack_blocks, slack_header, slack_footerz, slack_meta_event_type_lvcm, slack_meta, 10)
