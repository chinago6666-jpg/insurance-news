#!/usr/bin/env python3
"""
推送保险新闻到飞书
使用 App ID/App Secret 方式（不需要 webhook）
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:
    yaml = None


def load_yaml(path: Path) -> Any:
    """加载 YAML 配置文件"""
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    # Fallback: 使用 Ruby 解析
    import subprocess
    cmd = ["ruby", "-ryaml", "-rjson", "-e", 
           "obj = YAML.safe_load(File.read(ARGV[0])); print(JSON.generate(obj))", 
           str(path)]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def load_feishu_config(path: Path) -> Dict[str, Any]:
    """加载飞书配置"""
    if not path.exists():
        return {}
    raw = load_yaml(path) or {}
    return raw if isinstance(raw, dict) else {}


def load_json(path: Path, default: Any) -> Any:
    """加载 JSON 文件"""
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logging.warning("Invalid JSON: %s", path)
        return default


def get_feishu_token(app_id: str, app_secret: str) -> str:
    """获取飞书访问令牌"""
    url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        if data.get("code") == 0:
            return data.get("app_access_token")
        else:
            raise Exception(f"获取飞书 token 失败：{data}")


def pick_conclusion(item: Dict[str, Any]) -> str:
    """提取新闻结论"""
    summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
    conclusion = (
        str(summary.get("impact") or "").strip() or 
        str(summary.get("event") or "").strip() or 
        str(item.get("title") or "").strip() or 
        "无结论"
    )
    return conclusion.replace("\n", " ")


def read_report_content(report_path: Path, max_lines: int = 50) -> str:
    """读取报告文件内容"""
    if not report_path.exists():
        return ""
    
    content = report_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    # 限制行数，避免消息过长
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append("\n... (报告过长，已截断)")
    
    return "\n".join(lines)


def build_message(date_str: str, top_items: List[Dict[str, Any]], report_path: Path, include_path: bool, include_report: bool = False) -> str:
    """构建飞书消息"""
    lines: List[str] = [f"📰 保险日报 Top{len(top_items)}（{date_str}）", ""]

    if not top_items:
        lines.append("- 今日无可推送条目")
    else:
        for idx, item in enumerate(top_items, start=1):
            title = item.get("title", "无标题")
            link = str(item.get("link") or "").strip() or "(无链接)"
            score = item.get("score", 0)
            # 缩短链接显示
            short_link = link[:50] + "..." if len(link) > 50 else link
            lines.append(f"{idx}. {title}")
            lines.append(f"   🔗 {short_link} | ⭐{score}分")
            lines.append("")

    # 附加报告内容
    if include_report and report_path.exists():
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📄 完整报告内容")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        report_content = read_report_content(report_path)
        lines.append(report_content)
        lines.append("")

    if include_path:
        lines.append("")
        lines.append(f"📁 本地报告：{report_path}")

    lines.append("")
    lines.append(f"---")
    lines.append(f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M GMT+8')}*")

    return "\n".join(lines)


def send_feishu_message(token: str, user_open_id: str, text: str) -> Dict[str, Any]:
    """发送飞书消息（使用 open_id）"""
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id={user_open_id}&receive_id_type=open_id&msg_type=text"
    
    payload = json.dumps({
        "receive_id": user_open_id,
        "receive_id_type": "open_id",
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False)
    }, ensure_ascii=False).encode("utf-8")
    
    req = Request(url, data=payload, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    
    with urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    
    return json.loads(body)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Push insurance news to Feishu")
    p.add_argument("--root", default=".", help="project root path")
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="run date YYYY-MM-DD")
    p.add_argument("--feishu-config", default="config/feishu.yaml", help="feishu config path")
    p.add_argument("--top-n", type=int, default=None, help="override top N")
    p.add_argument("--no-local-path", action="store_true", help="do not append local report path")
    p.add_argument("--include-report", action="store_true", help="include full report content in message")
    p.add_argument("--dry-run", action="store_true", help="only print message, do not post")
    p.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s"
    )

    root = Path(args.root).expanduser().resolve()
    run_dir = root / "runs" / args.date
    summaries_path = run_dir / "summaries.json"
    report_path = run_dir / "report.md"

    # 加载飞书配置
    cfg = load_feishu_config(root / args.feishu_config)
    push_cfg = cfg.get("push", {}) if isinstance(cfg.get("push"), dict) else {}

    # 获取飞书凭证
    app_id = push_cfg.get("app_id")
    app_secret = push_cfg.get("app_secret")
    user_open_id = push_cfg.get("user_open_id")

    if not all([app_id, app_secret, user_open_id]):
        raise SystemExit(
            "Missing Feishu config. Set in config/feishu.yaml:\n"
            "push:\n"
            "  app_id: xxx\n"
            "  app_secret: xxx\n"
            "  user_open_id: xxx"
        )

    top_n = args.top_n if args.top_n is not None else int(push_cfg.get("top_n", 5))
    include_path = (not args.no_local_path) and bool(push_cfg.get("include_local_path", True))
    include_report = args.include_report or bool(push_cfg.get("include_report", False))

    # 加载新闻数据
    summaries = load_json(summaries_path, default=[])
    if not isinstance(summaries, list):
        raise SystemExit(f"summaries.json should be a list: {summaries_path}")

    # 按评分排序
    ranked = sorted(summaries, key=lambda x: int(x.get("score", 0)), reverse=True)
    top_items = ranked[: max(0, top_n)]

    # 构建消息
    message = build_message(args.date, top_items, report_path, include_path, include_report)

    if args.dry_run:
        print(message)
        return 0

    # 获取 token 并发送消息
    try:
        logging.info("获取飞书访问令牌...")
        token = get_feishu_token(app_id, app_secret)
        
        logging.info("发送飞书消息...")
        resp = send_feishu_message(token, user_open_id, message)
        
        if resp.get("code") == 0:
            msg_id = resp.get("data", {}).get("message_id", "unknown")
            logging.info("飞书推送成功！消息 ID: %s", msg_id)
            print(message)
            print(f"\n✅ 推送成功！消息 ID: {msg_id}")
        else:
            logging.error("飞书推送失败：%s", resp)
            print(f"❌ 推送失败：{resp}")
            return 1
            
    except Exception as e:
        logging.exception("推送异常：%s", e)
        raise SystemExit(f"推送失败：{e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
