import argparse
import json
import requests
import os
import re

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

def getAuthor(bv: str) -> str:
    url = f"http://api.bilibili.com/x/web-interface/view?bvid={bv}"
    response = requests.request("GET", url)
    response_json = response.json()
    cover = re.findall(r"（cover：(.+?)）", response_json['data']['title'])
    if cover:
        return cover[0]
    else:
        print(response_json['data']['title'])
    return ""

def insertAuthor(record_id: str, author_name: str, tenant_access_token: str):
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/bascn9KmdMTdQYZNM84e8vSs4At/tables/tblG5ZSTrqwu22ql/records/{record_id}"
    payload = json.dumps({
        "fields": {
            "原唱": author_name
        }
    })
    headers = {
        'Authorization': f'Bearer {tenant_access_token}'
    }
    response = requests.request("PUT", url, headers=headers, data=payload)

def syncRecord(record: dict, tenant_access_token: str):
    prefix = record['fields']['前缀'][0]['text']
    print(prefix, end="", flush=True)

    has_cover = '原唱' in record['fields'] and record['fields']['原唱']
    if not has_cover:
        has_bv = '录播组BV号' in record['fields'] and record['fields']['录播组BV号'] and record['fields']['录播组BV号'].startswith('BV')
        if has_bv:
            print(" 🧑‍🎤", end="", flush=True)
            author = getAuthor(record['fields']['录播组BV号'])
            if author:
                insertAuthor(record['record_id'], author, tenant_access_token)
    print("")
    # raise ""

def syncDatabase(app_id: str, app_secret: str):
    # 连接飞书API
    tenant_access_token = loginFeishu(app_id, app_secret)
    # 连接数据表
    page_token = ""
    has_more = True
    idx = 0
    while has_more:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/bascn9KmdMTdQYZNM84e8vSs4At/tables/tblG5ZSTrqwu22ql/records?page_size=20&page_token={page_token}"
        headers = {
            'Authorization': f'Bearer {tenant_access_token}'
        }
        response = requests.request("GET", url, headers=headers)
        response_json = response.json()
        for record in response_json['data']['items']:
            idx += 1
            print(f"正在填充原唱 {idx}/{response_json['data']['total']}: ", end="")
            syncRecord(record, tenant_access_token)
        has_more = response_json['data']['has_more']
        page_token = response_json['data']['page_token']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app_id",
                        help="飞书数据库的APP_ID, 格式为cli_开头的20位字符串")
    parser.add_argument("app_secret",
                        help="飞书数据库的APP_SECRET, 格式为32位字符串")
    args = parser.parse_args()
    syncDatabase(args.app_id, args.app_secret)

if __name__ == '__main__':
    main()
