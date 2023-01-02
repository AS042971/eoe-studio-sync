import argparse
import json
import requests
import os
import csv
import taglib

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

def initFiles(database_path: str, audio_path: str, cover_path: str) -> dict:
    # 创建音频目录
    if not os.path.exists(audio_path):
        os.makedirs(audio_path)
    if not os.path.exists(cover_path):
        os.makedirs(cover_path)
    if not os.path.exists(database_path):
        return {}
    current_update_time_dict = {}
    with open(database_path, newline='', encoding="utf-8-sig") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            current_update_time_dict[row[0]] = int(row[1])
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

def syncRecord(record: dict, current_update_time_dict: dict, audio_path: str, cover_path: str, tenant_access_token: str) -> str:
    record_id = record['record_id']
    update_time = record['fields']['最后更新时间']
    update_required = True
    if record_id in current_update_time_dict:
        if update_time <= current_update_time_dict[record_id]:
            update_required = False
    prefix = record['fields']['前缀'][0]['text']
    print(prefix, end="", flush=True)

    audio_updated = False
    if '歌曲文件' in record['fields']:
        audio_file_path = os.path.join(audio_path, f'{prefix}.m4a')
        if not os.path.exists(audio_file_path) or update_required:
            audio_updated = True
            print(" 🎶", end="", flush=True)
            downloadFile(record['fields']['歌曲文件'][0], audio_file_path, tenant_access_token)
    if '封面' in record['fields']:
        cover_file_path = os.path.join(cover_path, f'{prefix}.png')
        if not os.path.exists(cover_file_path) or update_required:
            print(" 🖼️", end="", flush=True)
            downloadFile(record['fields']['封面'][0], cover_file_path, tenant_access_token)
    print('')

    if audio_updated:
        # 更新歌曲元数据
        song = taglib.File(audio_file_path)
        song.tags['ARTIST'] = record['fields']['表演者']
        song.tags['TITLE'] = record['fields']['歌舞名称']
        song.tags['ALBUM'] = record['fields']['直播'][0]['text']

        song.save()

    # 在这里构建csv行
    name = ''
    if '歌舞名称' in record['fields']:
        name = record['fields']['歌舞名称']

    csv_line = f'{record_id},{update_time},{prefix},{name}'
    return csv_line

def syncDatabase(app_id: str, app_secret: str,
                 database_path: str, audio_path: str, cover_path: str):
    # 连接飞书API
    tenant_access_token = loginFeishu(app_id, app_secret)
    current_update_time_dict = initFiles(database_path, audio_path, cover_path)
    # 连接数据表
    page_token = ""
    has_more = True
    idx = 0
    with open(database_path,"w", encoding="utf-8-sig") as database_handler:
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
                new_database_item = syncRecord(record, current_update_time_dict, audio_path, cover_path, tenant_access_token)
                database_handler.write(new_database_item + '\n')
                database_handler.flush()
            has_more = response_json['data']['has_more']
            page_token = response_json['data']['page_token']

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
    args = parser.parse_args()
    syncDatabase(args.app_id, args.app_secret, args.database, args.audio, args.cover)

if __name__ == '__main__':
    main()
