#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse

# 阶段 1&2 优化：导入价值评分模块
try:
    from value_scorer import ValueScorer  # type: ignore
    VALUE_SCORER_ENABLED = True
except ImportError:
    VALUE_SCORER_ENABLED = False
    logging.warning("ValueScorer not available, using basic scoring only")

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


@dataclass
class ScoreConfig:
    min_score_to_include: int = 3
    cn_boost: int = 1
    negative_keywords: List[str] = None  # P0 优化：负面关键词列表
    negative_score: int = -3  # P0 优化：负面关键词扣分


def load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    cmd = ["ruby", "-ryaml", "-rjson", "-e", "obj = YAML.safe_load(File.read(ARGV[0])); print(JSON.generate(obj))", str(path)]
    try:
        out = subprocess.check_output(cmd, text=True)
        return json.loads(out)
    except Exception as exc:
        raise SystemExit("Cannot parse YAML. Install PyYAML or ensure Ruby is available.") from exc


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logging.warning("Invalid JSON at %s, using default", path)
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    p = urlparse(url)
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = re.sub(r"/+", "/", p.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", "", ""))


def normalize_title(title: str) -> str:
    t = (title or "").strip().lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[\-_|【】\[\]（）()，。,:：;；!！?？'\"`~·]", "", t)
    return t


def title_hash(norm_title: str) -> str:
    return hashlib.sha1(norm_title.encode("utf-8")).hexdigest()[:16]


def contains_duplicate(norm_title: str, existing_norm_titles: Set[str]) -> bool:
    for ex in existing_norm_titles:
        if norm_title in ex or ex in norm_title:
            return True
    return False


def parse_datetime_for_filter(value: str) -> Optional[datetime]:
    """
    阶段 3 优化：解析时间用于过滤（返回 datetime 对象）
    
    Args:
        value: 时间字符串（ISO 格式或其他常见格式）
    
    Returns:
        datetime 对象（带时区），解析失败返回 None
    """
    if not value:
        return None
    
    v = str(value).strip()
    if not v:
        return None
    
    # 尝试多种格式
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",      # 2026-03-05T10:00:00+08:00
        "%Y-%m-%dT%H:%M:%SZ",       # 2026-03-05T10:00:00Z
        "%Y-%m-%dT%H:%M:%S",        # 2026-03-05T10:00:00
        "%Y-%m-%d %H:%M:%S",        # 2026-03-05 10:00:00
        "%Y-%m-%d",                 # 2026-03-05
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(v[:19], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    
    # 尝试使用 email 解析器
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    
    return None


def load_keywords(path: Path) -> Tuple[Dict[str, Dict[str, List[str]]], ScoreConfig]:
    raw = load_yaml(path) or {}
    buckets = raw.get("buckets", {}) or {}
    scoring_raw = raw.get("scoring", {}) or {}
    sc = ScoreConfig(
        min_score_to_include=int(scoring_raw.get("min_score_to_include", 3)),
        cn_boost=int(scoring_raw.get("cn_boost", 1)),
        negative_keywords=list(scoring_raw.get("negative_keywords", [])),
        negative_score=int(scoring_raw.get("negative_score", -3))
    )
    return buckets, sc


def bucket_match(title: str, buckets: Dict[str, Dict[str, List[str]]]) -> Dict[str, List[str]]:
    low = title.lower()
    matched: Dict[str, List[str]] = {}
    for bucket, langs in buckets.items():
        hits: List[str] = []
        for _, kws in (langs or {}).items():
            for kw in kws or []:
                if kw and kw.lower() in low:
                    hits.append(kw)
        if hits:
            uniq = []
            seen = set()
            for h in hits:
                if h not in seen:
                    seen.add(h)
                    uniq.append(h)
            matched[bucket] = uniq
    return matched


def score_item(item: Dict[str, Any], matched: Dict[str, List[str]], sc: ScoreConfig) -> Tuple[int, List[str]]:
    """
    基础评分（兼容旧版）
    阶段 3 优化：优化评分规则，让有价值新闻更容易达到阈值
    """
    title = str(item.get("title", ""))
    region = str(item.get("region", "")).lower()
    source = str(item.get("source", "")).lower()
    reasons: List[str] = []
    score = 0

    # 正面评分：关键词桶命中
    score += len(matched)
    if matched:
        reasons.append(f"关键词桶命中 {len(matched)}")

    # 阶段 3 优化：细分主题加分
    if "regulatory" in matched:
        score += 3  # 监管主题 +3（从 +2 提高）
        reasons.append("监管主题 +3")
    elif "product_operation" in matched:
        score += 2  # 产品主题 +2
        reasons.append("产品主题 +2")
    elif "channel_growth" in matched or "agency_channel" in matched or "bancassurance_channel" in matched:
        score += 2  # 渠道主题 +2
        reasons.append("渠道主题 +2")
    elif "tech_data" in matched:
        score += 2  # 科技主题 +2
        reasons.append("科技主题 +2")

    # 中国相关
    if region == "cn" or "china" in title.lower() or "中国" in title:
        score += sc.cn_boost
        reasons.append(f"中国相关 +{sc.cn_boost}")

    # 阶段 3 优化：来源加分（权威来源额外 +1-2 分）
    if "nfra" in source or "监管" in source:
        score += 2
        reasons.append("权威来源 +2")
    elif "政府" in source or "gov" in source:
        score += 2
        reasons.append("政府来源 +2")
    elif "保险报" in source or "官方" in source:
        score += 1
        reasons.append("官方媒体 +1")

    # P0 优化：负面关键词扣分（排除股市公告、快讯等噪音）
    title_low = title.lower()
    negative_hits = []
    for neg_kw in (sc.negative_keywords or []):
        if neg_kw in title or neg_kw.lower() in title_low:
            negative_hits.append(neg_kw)
    
    if negative_hits:
        score += sc.negative_score  # 通常是 -3 分
        reasons.append(f"负面关键词 [{','.join(negative_hits)}] {sc.negative_score}分")

    return score, reasons


def calculate_value_score(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    阶段 1&2 优化：计算新闻价值分（5 维模型）
    
    返回：
        {
            "score": 总分，
            "level": 等级，
            "reasons": [原因],
            "breakdown": {维度得分}
        }
    """
    if not VALUE_SCORER_ENABLED:
        # 降级处理：使用基础评分
        return {"score": 0, "level": "⚪ 一般", "reasons": ["价值评分未启用"], "breakdown": {}}
    
    try:
        scorer = ValueScorer()
        return scorer.calculate_value(item)
    except Exception as e:
        logging.warning("Value scoring failed: %s", e)
        return {"score": 0, "level": "⚪ 一般", "reasons": [f"评分失败：{e}"], "breakdown": {}}


def format_fallback_summary(item: Dict[str, Any]) -> Dict[str, str]:
    tags = item.get("tags", [])
    tag_text = "、".join(tags) if tags else "未命中关键词桶"
    published = item.get("published_at") or "时间未标注"
    src = item.get("source") or "未知来源"
    title = item.get("title") or ""
    return {
        "event": f"{title}（来源：{src}，时间：{published}）",
        "impact": f"该条新闻与{tag_text}相关，可能影响保险机构的经营与策略判断。",
        "action": "建议关注监管口径与同业动作，必要时更新产品、渠道和风控策略。",
    }


def summarize_with_model(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    model = os.getenv("NEWS_SUMMARY_MODEL", "gpt-4o-mini")
    prompt = (
        "请用中文输出 JSON，不要额外文本。字段必须是 event, impact, action。基于以下新闻条目生成结构化总结：\n"
        f"标题: {item.get('title', '')}\n链接: {item.get('link', '')}\n时间: {item.get('published_at', '')}\n"
        f"来源: {item.get('source', '')}\n地区: {item.get('region', '')}\n标签: {', '.join(item.get('tags', []))}\n"
    )

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "你是保险行业研究员，擅长中文业务摘要。"},
                {"role": "user", "content": prompt},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
        if all(k in data for k in ("event", "impact", "action")):
            return {"event": str(data["event"]), "impact": str(data["impact"]), "action": str(data["action"])}
    except Exception as exc:
        logging.warning("Model summarization failed: %s", exc)
    return None


def summarize_item(item: Dict[str, Any]) -> Dict[str, str]:
    return summarize_with_model(item) or format_fallback_summary(item)


def infer_impact_channel(item: Dict[str, Any]) -> str:
    tags = set(item.get("tags", []))
    title = str(item.get("title", ""))

    if "agency_channel" in tags or ("代理人" in title) or ("个险" in title):
        return "个险代理人渠道"
    if "bancassurance_channel" in tags or ("银保" in title):
        return "银保渠道"
    if "channel_growth" in tags or ("线上" in title) or ("小程序" in title) or ("APP" in title):
        return "线上直销与私域渠道"
    if "regulatory" in tags:
        return "全渠道合规运营"
    if "risk_claims" in tags:
        return "理赔与客户经营渠道"
    return "数字化渠道整体经营"


def infer_priority(item: Dict[str, Any]) -> str:
    score = int(item.get("score", 0))
    tags = set(item.get("tags", []))
    title = str(item.get("title", ""))

    if "regulatory" in tags and (score >= 4 or ("处罚" in title) or ("通报" in title)):
        return "P1"
    if score >= 4:
        return "P2"
    return "P3"


def infer_owner_suggestion(item: Dict[str, Any], impact_channel: str) -> str:
    tags = set(item.get("tags", []))
    if "regulatory" in tags:
        return "合规负责人 + 渠道运营负责人"
    if impact_channel == "个险代理人渠道":
        return "个险渠道负责人"
    if impact_channel == "银保渠道":
        return "银保渠道负责人"
    if impact_channel == "线上直销与私域渠道":
        return "数字化渠道负责人"
    if "product_operation" in tags:
        return "产品负责人 + 渠道负责人"
    if "risk_claims" in tags:
        return "客服理赔负责人 + 运营负责人"
    if "tech_data" in tags:
        return "科技中台负责人 + 业务负责人"
    return "数字化渠道负责人"


def infer_action_72h(item: Dict[str, Any], impact_channel: str) -> str:
    tags = set(item.get("tags", []))

    if "regulatory" in tags:
        return "T+1完成政策解读，T+2完成渠道影响清单，T+3形成整改或落地方案并明确责任人。"
    if impact_channel == "个险代理人渠道":
        return "72小时内同步一线队伍口径，更新展业话术并检查活动率与转化率变化。"
    if impact_channel == "银保渠道":
        return "72小时内与重点银行渠道复盘，明确产品策略调整和网点执行节奏。"
    if impact_channel == "线上直销与私域渠道":
        return "72小时内上线小流量实验，验证获客成本、转化率和留资质量变化。"
    if "risk_claims" in tags:
        return "72小时内检查投诉与理赔异常波动，必要时启动专项风控排查。"
    return "72小时内完成影响评估、动作拆解和负责人确认，并在例会上追踪进度。"


def render_report(template: str, date_str: str, generated_at: str, included: List[Dict[str, Any]]) -> str:
    top = sorted(included, key=lambda x: x.get("score", 0), reverse=True)[:5]
    top5_lines = [
        f"- [{i.get('title','')}]({i.get('link','')})｜{i.get('priority','P3')}｜影响渠道：{i.get('impact_channel','未知')}｜评分 {i.get('score',0)}\n"
        f"  - 72小时动作：{i.get('action_72h','')}\n"
        f"  - 建议负责人：{i.get('owner_suggestion','')}"
        for i in top
    ] or ["- 今日无满足阈值的条目"]

    cn_reg = [i for i in included if i.get("region") == "cn" and "regulatory" in i.get("tags", [])]
    cn_lines = [
        f"- {i.get('title','')}（{i.get('priority','P3')}）\n"
        f"  - 摘要：{i.get('summary',{}).get('event','')}\n"
        f"  - 影响渠道：{i.get('impact_channel','未知')}\n"
        f"  - 72小时动作：{i.get('action_72h','')}\n"
        f"  - 建议负责人：{i.get('owner_suggestion','')}"
        for i in cn_reg[:10]
    ] or ["- 今日暂无中国监管高相关条目"]

    glb = [i for i in included if i.get("region") != "cn"]
    glb_lines = [
        f"- {i.get('title','')}（{i.get('source','')}）\n"
        f"  - 影响渠道：{i.get('impact_channel','未知')}\n"
        f"  - 72小时动作：{i.get('action_72h','')}"
        for i in glb[:10]
    ] or ["- 今日暂无全球高相关条目"]

    risk_related = []
    for i in included:
        tags = set(i.get("tags", []))
        if tags.intersection({"risk_claims", "capital_investment", "tech_data"}):
            risk_related.append(i)
    risk_lines = [
        f"- {i.get('title','')}（{i.get('priority','P3')}）\n"
        f"  - 建议动作：{i.get('action_72h','')}\n"
        f"  - 责任人：{i.get('owner_suggestion','')}"
        for i in risk_related[:10]
    ] or ["- 今日暂无显著风险/机会条目"]

    appendix = [f"- [{i.get('title','')}]({i.get('link','')})" for i in included] or ["- 无"]

    out = template
    out = out.replace("{{date}}", date_str)
    out = out.replace("{{generated_at}}", generated_at)
    out = out.replace("{{top5_bullets}}", "\n".join(top5_lines))
    out = out.replace("{{cn_regulatory_section}}", "\n".join(cn_lines))
    out = out.replace("{{global_section}}", "\n".join(glb_lines))
    out = out.replace("{{risk_opportunity_section}}", "\n".join(risk_lines))
    out = out.replace("{{appendix_links}}", "\n".join(appendix))
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build insurance daily report from raw_items.json")
    p.add_argument("--root", default=".", help="project root path")
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="run date YYYY-MM-DD")
    p.add_argument("--keywords", default="config/keywords.yaml", help="keywords config path")
    p.add_argument("--template", default="config/report_template.md", help="report template path")
    p.add_argument("--raw", default=None, help="custom raw_items.json path")
    p.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

    root = Path(args.root).expanduser().resolve()
    run_dir = root / "runs" / args.date
    raw_path = Path(args.raw).expanduser().resolve() if args.raw else run_dir / "raw_items.json"

    dedup_path = run_dir / "dedup_items.json"
    scored_path = run_dir / "scored_items.json"
    summaries_path = run_dir / "summaries.json"
    report_path = run_dir / "report.md"

    seen_urls_path = root / "state" / "seen_urls.json"
    seen_titles_path = root / "state" / "seen_titles.json"
    keywords_path = root / args.keywords
    template_path = root / args.template

    raw_items = load_json_file(raw_path, default=[])
    if not isinstance(raw_items, list):
        raise SystemExit(f"raw items should be list: {raw_path}")

    buckets, sc = load_keywords(keywords_path)
    template = template_path.read_text(encoding="utf-8")

    seen_urls = set(load_json_file(seen_urls_path, default=[]))
    seen_title_hashes = set(load_json_file(seen_titles_path, default=[]))

    # 阶段 3 优化：时间窗口配置（只抓取最近 N 天的新闻）
    TIME_WINDOW_DAYS = 7  # 7 天时间窗口
    
    deduped: List[Dict[str, Any]] = []
    current_norm_titles: Set[str] = set()
    new_seen_urls: Set[str] = set()
    new_seen_title_hashes: Set[str] = set()
    
    # 统计信息
    stats = {
        "total": 0,
        "missing_time": 0,
        "out_of_window": 0,
        "duplicate_url": 0,
        "duplicate_title": 0,
        "included": 0
    }

    for it in raw_items:
        stats["total"] += 1
        
        title = str(it.get("title", "")).strip()
        link = str(it.get("link", "")).strip()
        region = str(it.get("region", "global")).strip().lower() or "global"
        source = str(it.get("source", "unknown")).strip() or "unknown"
        published_at = it.get("published_at")

        if not title or not link:
            continue

        # 阶段 3 优化：时间窗口检查
        if published_at:
            try:
                pub_time = parse_datetime_for_filter(published_at)
                if pub_time:
                    age_days = (datetime.now(timezone.utc) - pub_time).days
                    if age_days > TIME_WINDOW_DAYS:
                        stats["out_of_window"] += 1
                        continue  # 超过时间窗口，跳过
                    elif age_days < 0:
                        # 未来时间，可能是时区问题，仍然接受
                        pass
            except Exception as e:
                logging.debug("Time parse failed for %s: %s", title[:50], e)
                stats["missing_time"] += 1
        else:
            stats["missing_time"] += 1
            # 没有时间戳的新闻，降低可信度，但仍然接受（如果其他条件满足）

        # URL 去重
        norm_url = normalize_url(link)
        if not norm_url or norm_url in seen_urls:
            stats["duplicate_url"] += 1
            continue

        # 标题去重
        norm_title = normalize_title(title)
        th = title_hash(norm_title)
        if th in seen_title_hashes:
            stats["duplicate_title"] += 1
            continue

        if norm_title in current_norm_titles or contains_duplicate(norm_title, current_norm_titles):
            continue

        item = {
            "title": title,
            "link": link,
            "normalized_url": norm_url,
            "published_at": published_at,
            "source": source,
            "region": region,
        }
        deduped.append(item)
        current_norm_titles.add(norm_title)
        new_seen_urls.add(norm_url)
        new_seen_title_hashes.add(th)

    save_json(dedup_path, deduped)

    scored_items: List[Dict[str, Any]] = []
    for item in deduped:
        matched = bucket_match(item["title"], buckets)
        tags = sorted(matched.keys())
        score, reasons = score_item(item, matched, sc)
        scored = dict(item)
        scored["tags"] = tags
        scored["matched_keywords"] = matched
        scored["score"] = score
        scored["score_reasons"] = reasons
        scored_items.append(scored)

    save_json(scored_path, scored_items)

    # 阶段 1&2 优化：添加价值评分
    summaries: List[Dict[str, Any]] = []
    for it in scored_items:
        obj = dict(it)
        obj["summary"] = summarize_item(it)
        impact_channel = infer_impact_channel(obj)
        obj["impact_channel"] = impact_channel
        obj["priority"] = infer_priority(obj)
        obj["owner_suggestion"] = infer_owner_suggestion(obj, impact_channel)
        obj["action_72h"] = infer_action_72h(obj, impact_channel)
        
        # 阶段 1&2 优化：计算价值分
        if VALUE_SCORER_ENABLED and obj.get("content"):
            value_result = calculate_value_score(obj)
            obj["value_score"] = value_result["score"]
            obj["value_level"] = value_result["level"]
            obj["value_reasons"] = value_result["reasons"]
            obj["value_breakdown"] = value_result["breakdown"]
            # 综合分数：基础分 + 价值分
            obj["final_score"] = int(obj.get("score", 0)) + obj["value_score"]
        else:
            obj["value_score"] = 0
            obj["value_level"] = "⚪ 一般"
            obj["value_reasons"] = []
            obj["value_breakdown"] = {}
            obj["final_score"] = int(obj.get("score", 0))
        
        summaries.append(obj)
    save_json(summaries_path, summaries)

    # 阶段 1&2 优化：使用综合分数筛选
    included = [x for x in summaries if x.get("final_score", 0) >= sc.min_score_to_include]
    # 按综合分数排序
    included.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    report = render_report(template, args.date, generated_at, included)
    report_path.write_text(report, encoding="utf-8")

    save_json(seen_urls_path, sorted(seen_urls.union(new_seen_urls)))
    save_json(seen_titles_path, sorted(seen_title_hashes.union(new_seen_title_hashes)))

    # 阶段 3 优化：输出详细统计
    logging.info("Done: raw=%d dedup=%d included=%d", len(raw_items), len(deduped), len(included))
    if stats["out_of_window"] > 0 or stats["missing_time"] > 0:
        logging.info("Time filter stats: out_of_window=%d missing_time=%d duplicate_url=%d duplicate_title=%d",
                     stats.get("out_of_window", 0), stats.get("missing_time", 0),
                     stats.get("duplicate_url", 0), stats.get("duplicate_title", 0))
    logging.info("Wrote: %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
