#!/usr/bin/env python3
"""推送保险新闻到飞书"""
import json
import urllib.request
from datetime import datetime

# 飞书配置
APP_ID = "cli_a92d5522aa7cdbb4"
APP_SECRET = "8DyCfvLvSyaNT5U2kqFUZJ7RKPJMQ7Rs"
USER_OPEN_ID = "ou_5cb00399133e3b40ee593932170c745a"

# 读取新闻数据
with open('/Users/yyhome/Documents/Insurance-news/runs/2026-03-04/raw_items.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

# 过滤有效新闻
valid_items = [
    item for item in items 
    if item.get('title') and len(item.get('title', '')) > 5 
    and not item.get('title', '').startswith('{{')
    and not item.get('title', '').startswith('>')
]

# 取前 10 条
top_items = valid_items[:10]

# 构建消息
today = datetime.now().strftime("%Y年%m月%d日")
message = f"📰 保险新闻汇总 - {today}\n\n"
message += f"共收集 {len(valid_items)} 条新闻，精选 Top 10：\n\n"

for i, item in enumerate(top_items, 1):
    title = item.get('title', '无标题')[:50]
    link = item.get('link', '#')
    source = item.get('source', '未知')
    message += f"{i}. {title}\n"
    message += f"   来源：{source}\n"
    if link and link.startswith('http'):
        message += f"   🔗 {link[:60]}...\n"
    message += "\n"

message += f"\n---\n*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M GMT+8')}*"
message += f"\n*完整报告：/Users/yyhome/Documents/Insurance-news/runs/2026-03-04/report.md*"

# 获取飞书 token
token_req = urllib.request.Request(
    "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal",
    data=json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(token_req, timeout=10) as resp:
    token_data = json.loads(resp.read().decode())
    TOKEN = token_data.get('app_access_token')

# 发送消息
msg_payload = {
    "receive_id": USER_OPEN_ID,
    "receive_id_type": "open_id",
    "msg_type": "text",
    "content": json.dumps({"text": message}, ensure_ascii=False)
}

msg_req = urllib.request.Request(
    f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id={USER_OPEN_ID}&receive_id_type=open_id&msg_type=text",
    data=json.dumps(msg_payload, ensure_ascii=False).encode(),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
)

with urllib.request.urlopen(msg_req, timeout=10) as resp:
    result = json.loads(resp.read().decode())
    print(f"发送成功！消息 ID: {result.get('data', {}).get('message_id')}")
    print(f"共推送 {len(top_items)} 条新闻")
