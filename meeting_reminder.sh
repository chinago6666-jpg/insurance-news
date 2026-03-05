#!/bin/bash
# 会议提醒脚本

APP_ID="cli_a92d5522aa7cdbb4"
APP_SECRET="8DyCfvLvSyaNT5U2kqFUZJ7RKPJMQ7Rs"
USER_OPEN_ID="ou_5cb00399133e3b40ee593932170c745a"

# 获取飞书 token
TOKEN=$(curl -s -X POST "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal" \
    -H "Content-Type: application/json" \
    -d "{\"app_id\":\"$APP_ID\",\"app_secret\":\"$APP_SECRET\"}" | \
    grep -o '"app_access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo "获取飞书 token 失败"
    exit 1
fi

# 发送提醒消息
curl -s -X POST "https://open.feishu.cn/open-apis/im/v1/messages?receive_id=${USER_OPEN_ID}&receive_id_type=open_id&msg_type=text" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"content\":\"{\\\"text\\\":\\\"⏰ 会议提醒\\\\n\\\\n您有一个会议安排：\\\\n\\\\n📍 地点：集团\\\\n🕐 时间：今天早上 9:00\\\\n\\\\n请准时参加！\\\"}\"}" > /dev/null

echo "会议提醒已发送"
