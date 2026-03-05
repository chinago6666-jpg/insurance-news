#!/usr/bin/env python3
"""测试阈值优化效果"""

import sys
sys.path.insert(0, '/Users/yyhome/Documents/Insurance-news')

from build_report import score_item, load_keywords
from pathlib import Path

# 加载配置
keywords_path = Path('/Users/yyhome/Documents/Insurance-news/config/keywords.yaml')
buckets, sc = load_keywords(keywords_path)

print("=" * 60)
print("阈值优化测试")
print("=" * 60)
print(f"当前入库阈值：min_score_to_include = {sc.min_score_to_include}")
print()

# 测试用例
test_cases = [
    {
        "title": "金融监管总局发布《保险资金运用管理办法》",
        "source": "NFRA 监管动态",
        "region": "cn",
        "expected": "✅ 应该入库（监管政策）"
    },
    {
        "title": "中国人寿寿险公司推出新款重疾险产品",
        "source": "新浪财经 保险",
        "region": "cn",
        "expected": "✅ 应该入库（产品新闻）"
    },
    {
        "title": "平安保险代理人规模突破 100 万",
        "source": "证券时报",
        "region": "cn",
        "expected": "✅ 应该入库（渠道动态）"
    },
    {
        "title": "某保险公司召开年度工作会议",
        "source": "证券时报",
        "region": "cn",
        "expected": "⚪ 可入库可不入库（一般资讯）"
    },
    {
        "title": "公告精选：法尔胜称不涉及特种光纤业务",
        "source": "证券时报",
        "region": "cn",
        "expected": "❌ 应该过滤（公告噪音）"
    },
]

for i, case in enumerate(test_cases, 1):
    item = {
        "title": case["title"],
        "source": case["source"],
        "region": case["region"],
    }
    
    # 关键词匹配
    from build_report import bucket_match
    matched = bucket_match(case["title"], buckets)
    
    # 评分
    score, reasons = score_item(item, matched, sc)
    
    # 判断
    status = "✅ 入库" if score >= sc.min_score_to_include else "❌ 过滤"
    
    print(f"测试 {i}: {case['title'][:40]}...")
    print(f"  得分：{score} 分 | {status}")
    print(f"  原因：{reasons}")
    print(f"  预期：{case['expected']}")
    print()

print("=" * 60)
