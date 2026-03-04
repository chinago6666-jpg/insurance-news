#!/usr/bin/env python3
"""
发送告警消息到飞书
用于采集失败、推送失败等异常情况
"""
import json
import urllib.request
from datetime import datetime

# 飞书配置
APP_ID = "cli_a92d5522aa7cdbb4"
APP_SECRET = "8DyCfvLvSyaNT5U2kqFUZJ7RKPJMQ7Rs"
USER_OPEN_ID = "ou_5cb00399133e3b40ee593932170c745a"


def get_feishu_token():
    """获取飞书访问令牌"""
    url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
    payload = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        if data.get("code") == 0:
            return data.get("app_access_token")
        else:
            raise Exception(f"获取飞书 token 失败：{data}")


def send_alert(title: str, message: str, level: str = "warning"):
    """
    发送告警消息
    
    Args:
        title: 告警标题
        message: 告警内容
        level: 告警级别 (info, warning, error, critical)
    """
    # 表情符号
    emojis = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "❌",
        "critical": "🚨"
    }
    
    emoji = emojis.get(level, "⚠️")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    text = f"{emoji} *系统告警 - {title}*\n\n{message}\n\n---\n*时间：{timestamp}*"
    
    # 获取 token
    token = get_feishu_token()
    
    # 发送消息
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id={USER_OPEN_ID}&receive_id_type=open_id&msg_type=text"
    payload = json.dumps({
        "receive_id": USER_OPEN_ID,
        "receive_id_type": "open_id",
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False)
    }, ensure_ascii=False).encode()
    
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode())
        if result.get("code") == 0:
            print(f"✅ 告警消息已发送：{title}")
            return True
        else:
            print(f"❌ 告警消息发送失败：{result}")
            return False


if __name__ == "__main__":
    # 测试
    send_alert(
        title="系统测试",
        message="这是一条测试告警消息，确认告警功能正常工作。",
        level="info"
    )
