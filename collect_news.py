#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, quote_plus, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

USER_AGENT = "insurance-news-collector/1.0"
TIMEOUT = 20


@dataclass
class SourceConfig:
    name: str
    type: str
    region: str
    url: Optional[str] = None
    query: Optional[str] = None
    lang: Optional[str] = None
    selectors: Optional[Dict[str, str]] = None


def load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)

    # Fallback: use system Ruby's built-in YAML parser (Psych), no pip needed.
    cmd = [
        "ruby",
        "-ryaml",
        "-rjson",
        "-e",
        "obj = YAML.safe_load(File.read(ARGV[0])); print(JSON.generate(obj))",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, text=True)
        return json.loads(out)
    except Exception as exc:
        raise SystemExit("Cannot parse YAML. Install PyYAML or ensure Ruby is available.") from exc


def fetch_text(url: str) -> str:
    safe_url = sanitize_url(url)
    req = Request(safe_url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def sanitize_url(url: str) -> str:
    u = (url or "").strip()
    if not u or not re.match(r"^https?://", u, re.IGNORECASE):
        raise ValueError(f"invalid http/https url: {url!r}")

    p = urlsplit(u)
    path = quote(p.path or "/", safe="/:@-._~%!$&'()*+,;=")
    query = quote(p.query or "", safe="=&/?:@-._~%!$'()*+,;")
    frag = quote(p.fragment or "", safe="")
    return urlunsplit((p.scheme, p.netloc, path, query, frag))


def normalize_datetime(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    v = value.strip()
    if not v:
        return None

    try:
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return v


def to_google_news_rss_url(query: str, lang: Optional[str], region: str) -> str:
    q = quote_plus(query)
    if (lang or "").lower().startswith("zh") or region.lower() == "cn":
        return (
            "https://news.google.com/rss/search"
            f"?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        )
    return (
        "https://news.google.com/rss/search"
        f"?q={q}&hl=en-US&gl=US&ceid=US:en"
    )


def text_of(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    t = "".join(el.itertext()).strip()
    return t or None


def parse_rss_or_atom(xml_text: str, source_name: str, region: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    root = ET.fromstring(xml_text)

    if root.tag.endswith("rss") or root.find("channel") is not None:
        channel = root.find("channel")
        if channel is None:
            return items
        for node in channel.findall("item"):
            title = text_of(node.find("title"))
            link = text_of(node.find("link"))
            pub = text_of(node.find("pubDate")) or text_of(node.find("date"))
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "link": link,
                    "published_at": normalize_datetime(pub),
                    "source": source_name,
                    "region": region,
                }
            )
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for node in root.findall("atom:entry", ns):
        title = text_of(node.find("atom:title", ns))
        link_el = node.find("atom:link", ns)
        href = link_el.attrib.get("href") if link_el is not None else None
        pub = text_of(node.find("atom:updated", ns)) or text_of(node.find("atom:published", ns))
        if not title or not href:
            continue
        items.append(
            {
                "title": title,
                "link": href,
                "published_at": normalize_datetime(pub),
                "source": source_name,
                "region": region,
            }
        )
    return items


def collect_from_rss(url: str, source_name: str, region: str) -> List[Dict[str, Any]]:
    xml_text = fetch_text(url)
    return parse_rss_or_atom(xml_text, source_name, region)


def collect_from_web_list(url: str, selectors: Optional[Dict[str, str]], source_name: str, region: str) -> List[Dict[str, Any]]:
    if not selectors or not selectors.get("item"):
        logging.warning("Skip web_list source '%s': missing selectors.item", source_name)
        return []

    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        logging.warning(
            "BeautifulSoup missing for '%s', using basic link fallback parser",
            source_name,
        )
        html = fetch_text(url)
        items: List[Dict[str, Any]] = []
        # Fallback parser: extract anchor text/href pairs from raw HTML.
        for m in re.finditer(
            r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            href = m.group(1).strip()
            text = re.sub(r"<[^>]+>", " ", m.group(2))
            title = re.sub(r"\s+", " ", text).strip()
            if not href or not title or len(title) < 6:
                continue
            link = urljoin(url, href)
            items.append(
                {
                    "title": title,
                    "link": link,
                    "published_at": None,
                    "source": source_name,
                    "region": region,
                }
            )
            if len(items) >= 80:
                break
        return items

    html = fetch_text(url)
    soup = BeautifulSoup(html, "html.parser")

    item_sel = selectors.get("item")
    title_sel = selectors.get("title")
    link_sel = selectors.get("link")
    date_sel = selectors.get("date")

    items: List[Dict[str, Any]] = []
    for block in soup.select(item_sel):
        title = None
        link = None
        date_text = None

        if title_sel:
            t = block.select_one(title_sel)
            title = t.get_text(strip=True) if t else None
        else:
            title = block.get_text(strip=True)

        if link_sel:
            l = block.select_one(link_sel)
            if l and l.has_attr("href"):
                link = urljoin(url, l["href"])
        else:
            a = block.find("a")
            if a and a.has_attr("href"):
                link = urljoin(url, a["href"])

        if date_sel:
            d = block.select_one(date_sel)
            date_text = d.get_text(strip=True) if d else None

        if not title or not link:
            continue

        items.append(
            {
                "title": re.sub(r"\s+", " ", title).strip(),
                "link": link.strip(),
                "published_at": normalize_datetime(date_text),
                "source": source_name,
                "region": region,
            }
        )

    return items


def load_sources(sources_path: Path) -> List[SourceConfig]:
    raw = load_yaml(sources_path) or {}
    source_list = raw.get("sources")
    if not isinstance(source_list, list):
        raise ValueError("config/sources.yaml must contain a top-level `sources` list")

    out: List[SourceConfig] = []
    for s in source_list:
        if not isinstance(s, dict):
            continue
        t = str(s.get("type", "")).strip()
        n = str(s.get("name", "")).strip() or "unknown_source"
        r = str(s.get("region", "global")).strip() or "global"
        out.append(SourceConfig(name=n, type=t, region=r, url=s.get("url"), query=s.get("query"), lang=s.get("lang"), selectors=s.get("selectors")))
    return out


def load_offline_items(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"offline file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("offline file must be a JSON list")

    out: List[Dict[str, Any]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        link = str(it.get("link", "")).strip()
        if not title or not link:
            continue
        out.append(
            {
                "title": title,
                "link": link,
                "published_at": it.get("published_at"),
                "source": str(it.get("source", "offline_import")).strip() or "offline_import",
                "region": str(it.get("region", "cn")).strip() or "cn",
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "source_type": str(it.get("source_type", "offline")).strip() or "offline",
            }
        )
    return out


def collect_all(sources: Iterable[SourceConfig]) -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    for src in sources:
        try:
            if src.type == "rss":
                if not src.url:
                    logging.warning("Skip source '%s': missing url", src.name)
                    continue
                items = collect_from_rss(src.url, src.name, src.region)
            elif src.type == "google_news_rss":
                if not src.query:
                    logging.warning("Skip source '%s': missing query", src.name)
                    continue
                url = to_google_news_rss_url(src.query, src.lang, src.region)
                items = collect_from_rss(url, src.name, src.region)
            elif src.type == "web_list":
                if not src.url:
                    logging.warning("Skip source '%s': missing url", src.name)
                    continue
                items = collect_from_web_list(src.url, src.selectors, src.name, src.region)
            else:
                logging.warning("Skip source '%s': unsupported type=%s", src.name, src.type)
                continue

            for i in items:
                i["collected_at"] = collected_at
                i["source_type"] = src.type
            all_items.extend(items)
            logging.info("Collected %d items from %s", len(items), src.name)
        except Exception as exc:
            logging.exception("Source failed: %s (%s)", src.name, exc)

    return all_items


def write_output(root: Path, date_str: str, items: List[Dict[str, Any]]) -> Path:
    out_dir = root / "runs" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "raw_items.json"
    out_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect insurance news from RSS and web list pages")
    parser.add_argument("--root", default=".", help="Project root containing config/ and runs/")
    parser.add_argument("--sources", default="config/sources.yaml", help="Sources YAML path")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Output date folder")
    parser.add_argument("--offline-from", default=None, help="Local JSON list path for offline mode (skip network)")
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

    root = Path(args.root).expanduser().resolve()
    sources_path = (root / args.sources).resolve()

    if not sources_path.exists():
        raise SystemExit(f"sources.yaml not found: {sources_path}")

    if args.offline_from:
        offline_path = Path(args.offline_from).expanduser().resolve()
        items = load_offline_items(offline_path)
        logging.info("Offline mode loaded %d items from %s", len(items), offline_path)
    else:
        sources = load_sources(sources_path)
        items = collect_all(sources)
    out_file = write_output(root, args.date, items)

    logging.info("Done. total_items=%d output=%s", len(items), out_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
