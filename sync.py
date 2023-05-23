import argparse
import json
import requests
import os
import sys
import csv
import shutil
import taglib
import tempfile
from PIL import Image

def loginFeishu(app_id: str, app_secret: str) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
    payload = json.dumps({
        "app_id": app_id,
        "app_secret": app_secret
    })

    headers = {
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    response_json = response.json()

    if "tenant_access_token" not in response_json:
        raise Exception(f'连接飞书失败, 返回值: {response_json}')

    return response_json["tenant_access_token"]

def initFiles(database_path: str, audio_path: str, cover_path: str, thumb_path: str, lyric_path: str) -> dict:
    # 创建音频目录
    if not os.path.exists(audio_path):
        os.makedirs(audio_path)
    if not os.path.exists(cover_path):
        os.makedirs(cover_path)
    if not os.path.exists(thumb_path):
        os.makedirs(thumb_path)
    if not os.path.exists(lyric_path):
        os.makedirs(lyric_path)
    if not os.path.exists(database_path):
        return {}
    current_update_time_dict = {}
    with open(database_path, newline='', encoding="utf-8-sig") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            # 提取更新时间和歌曲时长
            current_update_time_dict[row[0]] = (int(row[1]), int(row[8]))
    shutil.copy(database_path, database_path+'.sync')
    return current_update_time_dict

def downloadFile(file_obj: dict, path: str, tenant_access_token: str):
    url = file_obj['tmp_url']
    headers = {
        'Authorization': f'Bearer {tenant_access_token}'
    }
    response = requests.request("GET", url, headers=headers)
    response_json = response.json()
    direct_url = response_json['data']['tmp_download_urls'][0]['tmp_download_url']
    file_response = requests.get(direct_url)
    open(path, "wb").write(file_response.content)

def getCropRegion(width, height):
    if width < height:
        left = 0
        upper = (height - width) / 2
        right = width
        lower = upper + width
    elif width > height:
        left = (width - height) / 2
        upper = 0
        right = left + height
        lower = height
    else:
        left = 0
        upper = 0
        right = width
        lower = height
    return (left, upper, right, lower)

def cutThumbnail(cover_path: str, thumb_path: str) -> None:
    im = Image.open(cover_path)
    copy = im.crop(getCropRegion(im.size[0], im.size[1]))
    copy.thumbnail((150, 150))
    copy.save(thumb_path, "PNG")

def convertLyric(lyric_tmp_file_path: str, lyric_file_path: str) -> str:
    f_in = open(lyric_tmp_file_path,"r", encoding="utf-8")
    f_out = open(lyric_file_path,"w+", encoding="utf-8")
    for line in f_in:
        if line.startswith("Dialogue:"):
            phrased = line.split(",")
            lrc_line = f'[{phrased[1]}]{phrased[9]}'
            f_out.write(lrc_line)
    f_out.close()
    f_in.close()

def syncRecord(record: dict, current_update_time_dict: dict,
               audio_path: str, cover_path: str, thumb_path: str, lyric_path: str,
               tenant_access_token: str, tag_editor_bin: str, ignore_local: bool) -> str:
    record_id = record['record_id']
    fields = record['fields']
    update_time = fields['最后更新时间'] if '最后更新时间' in fields and fields['最后更新时间'] else 0
    update_required = True
    csv_duration = 0
    if record_id in current_update_time_dict:
        (current_update_time, csv_duration) = current_update_time_dict[record_id]
        if update_time <= current_update_time:
            update_required = False
    prefix = fields['前缀'][0]['text']
    prefix = prefix.replace('合唱', 'EOE')
    prefix = prefix.replace('团舞', 'EOE')
    postfix = 'm4a'
    if '歌曲文件' in fields and fields['歌曲文件']:
        raw_file_name: str = fields['歌曲文件'][0]['name']
        if raw_file_name.endswith('m4a') or raw_file_name.endswith('M4a'):
            postfix = 'm4a'
        elif raw_file_name.endswith('mp3'):
            postfix = 'mp3'
        elif raw_file_name.endswith('flac'):
            postfix = 'flac'
        elif raw_file_name.endswith('wav'):
            postfix = 'wav'
        elif raw_file_name.endswith('mp4'):
            postfix = 'mp4'
        else:
            print(f'不支持的扩展名：{raw_file_name}')
            return ""
    print(prefix, end="", flush=True)

    audio_updated = False
    cover_updated = False
    lyric_updated = False
    audio_file_path = os.path.join(audio_path, f'{prefix}.{postfix}')
    cover_file_path = os.path.join(cover_path, f'{prefix}.png')
    thumb_file_path = os.path.join(thumb_path, f'{prefix}.png')
    lyric_tmp_file_path = os.path.join(tempfile.gettempdir(), f'{prefix}.ass')
    lyric_file_path = os.path.join(lyric_path, f'{prefix}.lrc')
    csv_has_cover = 0
    csv_has_lyric = 0
    if '歌曲文件' in fields and fields['歌曲文件']:
        if (not os.path.exists(audio_file_path) and not ignore_local) or update_required:
            audio_updated = True
            print(" 🎶", end="", flush=True)
            downloadFile(fields['歌曲文件'][0], audio_file_path, tenant_access_token)
    if '封面' in fields and fields['封面']:
        csv_has_cover = 1
        if (not os.path.exists(cover_file_path) and not ignore_local) or update_required:
            cover_updated = True
            print(" 🖼️", end="", flush=True)
            downloadFile(fields['封面'][0], cover_file_path, tenant_access_token)
        if os.path.exists(cover_file_path) and ((not os.path.exists(thumb_file_path) and not ignore_local) or update_required):
            print(" ✂️", end="", flush=True)
            cutThumbnail(cover_file_path, thumb_file_path)
    if 'ASS字幕文件' in fields and fields['ASS字幕文件']:
        csv_has_lyric = 1
        if (not os.path.exists(lyric_file_path) and not ignore_local) or update_required:
            lyric_updated = True
            print(" 🗒️", end="", flush=True)
            downloadFile(fields['ASS字幕文件'][0], lyric_tmp_file_path, tenant_access_token)
            convertLyric(lyric_tmp_file_path, lyric_file_path)

    live = fields['直播'][0]['text'].strip() if '直播' in fields and fields['直播'] else ''

    if audio_updated or lyric_updated:
        print(" 🔄", end="", flush=True)
        # 更新歌曲元数据
        song = taglib.File(audio_file_path)
        song.tags['ALBUMARTIST'] = 'EOE组合'
        if '原唱' in fields and fields['原唱']:
            song.tags['COMPOSER'] = fields['原唱']
        if '表演者' in fields and '全员' in fields['表演者']:
            song.tags['ARTIST'] = "莞儿/露早/米诺/虞莫/柚恩"
        elif '表演者' in fields and fields['表演者']:
            song.tags['ARTIST'] = "/".join(fields['表演者'])
        if '版本备注' in fields and fields['版本备注']:
            song.tags['COMMENT'] = fields['版本备注']
        if '语言' in fields and fields['语言']:
            song.tags['GENRE'] = fields['语言']
        song.tags['TITLE'] = fields['歌舞名称'] if '歌舞名称' in fields and fields['歌舞名称'] else ''
        song.tags['ALBUM'] = live
        if live.startswith('20'):
            song.tags['DATE'] = live[0:4]
        if os.path.exists(lyric_file_path):
            f_l = open(lyric_file_path,"r", encoding="utf-8")
            song.tags['©lyr'] = f_l.read()
            f_l.close()
        song.save()
        song.close()

    if tag_editor_bin:
        if audio_updated or cover_updated:
            if os.path.exists(audio_file_path) and os.path.exists(cover_file_path) and postfix == 'm4a':
                print(" 🔄", end="", flush=True)
                # 嵌入封面文件
                cmd = f'{os.path.abspath(tag_editor_bin)} -s cover="{cover_file_path}" --max-padding 10000000 -f "{audio_file_path}" -q'
                os.system(cmd)

    # 填充长度
    if audio_updated:
        if os.path.exists(audio_file_path):
            song = taglib.File(audio_file_path)
            csv_duration = song.length
            song.close()

    print(' ')

    # 在这里构建csv行
    csv_name = fields['歌舞名称'].replace(',','，') if '歌舞名称' in fields else ''
    csv_oname = fields['歌舞别名(可选)'].replace(',','，') if '歌舞别名(可选)' in fields and fields['歌舞别名(可选)'] else ''
    csv_singer = " ".join(fields['表演者']) if '表演者' in fields else ''
    if csv_singer == '全员':
        csv_singer = 'EOE'
    csv_date = prefix[0:10]
    csv_version = fields['版本备注'] if '版本备注' in fields else ''
    csv_lang = fields['语言'] if '语言' in fields else ''
    csv_quality = fields['完整度'] if '完整度' in fields else ''
    csv_live = live
    csv_bv = fields['官切BV号'] if '官切BV号' in fields and fields['官切BV号'].startswith('BV') else ''
    if not csv_bv:
        csv_bv = fields['录播组BV号'] if '录播组BV号' in fields  and fields['录播组BV号'].startswith('BV') else ''

    csv_line = f'{record_id},{update_time},{csv_name},{csv_oname},{csv_singer},{csv_date},{csv_version},{postfix},{csv_duration},{csv_lang},{csv_quality},{csv_has_cover},{csv_live},{csv_bv},{csv_has_lyric}'
    return csv_line

def syncDatabase(app_id: str, app_secret: str,
                 database_path: str, audio_path: str, cover_path: str, thumb_path: str, lyric_path: str,
                 tag_editor_bin: str, ignore_local: bool):
    # 连接飞书API
    tenant_access_token = loginFeishu(app_id, app_secret)
    current_update_time_dict = initFiles(database_path, audio_path, cover_path, thumb_path, lyric_path)
    # 连接数据表
    page_token = ""
    has_more = True
    idx = 0
    with open(database_path + '.sync',"w", encoding="utf-8-sig") as database_handler:
        while has_more:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/bascn9KmdMTdQYZNM84e8vSs4At/tables/tblG5ZSTrqwu22ql/records?page_size=20&view_id=vewhP0A7DP&page_token={page_token}"
            headers = {
                'Authorization': f'Bearer {tenant_access_token}'
            }
            response = requests.request("GET", url, headers=headers)
            response_json = response.json()
            for record in response_json['data']['items']:
                idx += 1
                print(f"正在同步 {idx}/{response_json['data']['total']}: ", end="")
                new_database_item = syncRecord(record, current_update_time_dict,
                                               audio_path, cover_path, thumb_path, lyric_path,
                                               tenant_access_token, tag_editor_bin, ignore_local)
                if new_database_item != '':
                    database_handler.write(new_database_item + '\n')
                    database_handler.flush()
            has_more = response_json['data']['has_more']
            page_token = response_json['data']['page_token']
    # finish
    if os.path.exists(database_path):
        shutil.copy(database_path, database_path+'.bak')
    shutil.move(database_path+'.sync', database_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app_id",
                        help="飞书数据库的APP_ID, 格式为cli_开头的20位字符串")
    parser.add_argument("app_secret",
                        help="飞书数据库的APP_SECRET, 格式为32位字符串")
    parser.add_argument("--database", default="./database.csv",
                        help="数据库csv文件")
    parser.add_argument("--audio", default="./audio",
                        help="音频文件存储路径")
    parser.add_argument("--cover", default="./cover",
                        help="封面文件存储路径")
    parser.add_argument("--thumbnail", default="./thumbnail",
                        help="封面缩略图文件存储路径")
    parser.add_argument("--lyric", default="./lyric",
                        help="歌词文件存储路径")
    parser.add_argument("--tag-editor-bin", default="./bin/tageditor.exe",
                        help="为音频文件嵌入封面, 请前往 https://github.com/Martchus/tageditor 下载可执行文件")
    parser.add_argument("--ignore-local-file", action="store_true",
                        help="忽略本地文件. 当设置此项时, 只有云端更新时才会触发下载; 本地文件缺失时不会触发下载")
    args = parser.parse_args()

    if not os.path.exists(args.tag_editor_bin):
        ans = input(f'\033[93m在"{args.tag_editor_bin}"找不到 tageditor 可执行文件.\n请前往 https://github.com/Martchus/tageditor/releases 下载最新发行版并置于指定路径, 否则歌曲嵌入封面功能将失效.\n是否继续? [Y/n]\033[0m')
        if ans.lower() == 'no' or ans.lower() == 'n':
            sys.exit(-1)
        args.tag_editor_bin = ""

    syncDatabase(args.app_id, args.app_secret,
                 args.database, args.audio, args.cover, args.thumbnail, args.lyric,
                 args.tag_editor_bin, args.ignore_local_file)
if __name__ == '__main__':
    main()
