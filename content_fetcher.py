#!/usr/bin/env python3
"""
新闻正文抓取模块
从网页中提取新闻正文内容，用于价值评分
"""

import re
import logging
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.parse import urljoin
import time

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None

USER_AGENT = "insurance-news-content-fetcher/1.0"
TIMEOUT = 15
MAX_CONTENT_LENGTH = 10000  # 最大内容长度（字符）


def fetch_content(item: Dict[str, Any]) -> Optional[str]:
    """
    抓取新闻正文内容
    
    Args:
        item: 新闻条目（包含 link 字段）
    
    Returns:
        正文字符串，失败返回 None
    """
    link = item.get("link", "")
    if not link:
        return None
    
    try:
        # 添加延迟，避免请求过快
        time.sleep(0.5)
        
        req = Request(link, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=TIMEOUT) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read().decode(charset, errors="replace")
            
            # 提取正文
            content = extract_article_content(html, link)
            
            # 限制长度
            if content and len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "..."
            
            return content
            
    except Exception as e:
        logging.warning("Failed to fetch content from %s: %s", link, e)
        return None


def extract_article_content(html: str, url: str = "") -> Optional[str]:
    """
    从 HTML 中提取文章正文
    
    使用多种策略：
    1. BeautifulSoup 解析（如果有）
    2. 基于标签密度和文本长度的启发式算法
    3. 移除导航、广告等噪音
    """
    if not html or not html.strip():
        return None
    
    # 策略 1：使用 BeautifulSoup（推荐）
    if BeautifulSoup is not None:
        return extract_with_bs4(html, url)
    
    # 策略 2：简单文本提取（无 BS4 时）
    return extract_simple(html)


def extract_with_bs4(html: str, url: str = "") -> Optional[str]:
    """使用 BeautifulSoup 提取正文"""
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # 移除不需要的元素
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        
        # 尝试查找文章容器
        article_containers = [
            "article",
            ".article-content",
            ".post-content",
            ".news-content",
            ".article-body",
            ".content",
            "#content",
        ]
        
        content_div = None
        for selector in article_containers:
            if selector.startswith("."):
                content_div = soup.find("div", class_=selector[1:])
            elif selector.startswith("#"):
                content_div = soup.find(id=selector[1:])
            else:
                content_div = soup.find(selector)
            
            if content_div:
                break
        
        # 如果没找到容器，使用整个 body
        if not content_div:
            content_div = soup.find("body")
        
        if not content_div:
            content_div = soup
        
        # 提取文本
        paragraphs = []
        for p in content_div.find_all(["p", "div"]):
            text = p.get_text(strip=True)
            # 过滤短文本和噪音
            if len(text) > 20 and not is_noise(text):
                paragraphs.append(text)
        
        # 合并段落
        if paragraphs:
            content = "\n\n".join(paragraphs)
            # 去重（移除重复段落）
            content = remove_duplicates(content)
            return content
        
        return None
        
    except Exception as e:
        logging.warning("BS4 extraction failed: %s", e)
        return None


def extract_simple(html: str) -> Optional[str]:
    """简单文本提取（无 BS4 备用方案）"""
    try:
        # 移除脚本和样式
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        
        # 提取段落
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.DOTALL | re.IGNORECASE)
        
        # 清理 HTML 标签
        cleaned = []
        for p in paragraphs:
            text = re.sub(r"<[^>]+>", " ", p)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 20 and not is_noise(text):
                cleaned.append(text)
        
        if cleaned:
            return "\n\n".join(cleaned[:20])  # 限制段落数
        
        return None
        
    except Exception as e:
        logging.warning("Simple extraction failed: %s", e)
        return None


def is_noise(text: str) -> bool:
    """判断文本是否为噪音"""
    text_lower = text.lower()
    
    # 常见噪音模式
    noise_patterns = [
        "首页", "导航", "菜单", "广告", "推荐", "热门",
        "相关阅读", "猜你喜欢", "分享到", "复制链接",
        "copyright", "all rights reserved",
        "设为首页", "加入收藏", "关于我们",
    ]
    
    for pattern in noise_patterns:
        if pattern in text_lower:
            return True
    
    # 文本过短或过长
    if len(text) < 10 or len(text) > 500:
        return True
    
    # 链接过多
    link_count = text.count("http")
    if link_count > 3:
        return True
    
    return False


def remove_duplicates(text: str) -> str:
    """移除重复段落"""
    paragraphs = text.split("\n\n")
    seen = set()
    unique = []
    
    for p in paragraphs:
        p_clean = p.strip()
        if p_clean and p_clean not in seen:
            seen.add(p_clean)
            unique.append(p)
    
    return "\n\n".join(unique)


def fetch_contents_batch(items: List[Dict[str, Any]], batch_size: int = 10) -> List[Dict[str, Any]]:
    """
    批量抓取正文内容
    
    Args:
        items: 新闻条目列表
        batch_size: 批次大小
    
    Returns:
        添加了 content 字段的新闻条目列表
    """
    results = []
    
    for i, item in enumerate(items):
        logging.info("Fetching content %d/%d: %s", i + 1, len(items), item.get("title", "")[:50])
        
        # 抓取内容
        content = fetch_content(item)
        
        # 添加到条目
        item_with_content = item.copy()
        item_with_content["content"] = content or ""
        item_with_content["has_content"] = bool(content)
        results.append(item_with_content)
        
        # 延迟避免被封
        if (i + 1) % batch_size == 0:
            logging.info("Batch %d completed, pausing...", (i + 1) // batch_size)
            time.sleep(2)
    
    return results


def test_fetcher():
    """测试抓取器"""
    # 测试用例
    test_items = [
        {
            "title": "金融监管总局发布新规",
            "link": "https://www.nfra.gov.cn/cn/view/pages/itemDetail.html?docId=xxx",
            "source": "NFRA"
        }
    ]
    
    results = fetch_contents_batch(test_items)
    for r in results:
        print(f"标题：{r['title']}")
        print(f"内容长度：{len(r.get('content', ''))}")
        print(f"前 100 字：{r.get('content', '')[:100]}")
        print("-" * 50)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_fetcher()
