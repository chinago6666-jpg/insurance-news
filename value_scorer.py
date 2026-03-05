#!/usr/bin/env python3
"""
保险新闻价值评分模块
5 维价值评估模型：主题分 + 来源分 + 影响分 + 时效分 + 行动分
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


class ValueScorer:
    """保险新闻价值评分器"""
    
    def __init__(self):
        # 1. 来源权威性权重
        self.source_weights = {
            "nfra.gov.cn": 1.5,           # 国家金融监督管理总局
            "cbirc.gov.cn": 1.5,          # 银保监会（历史）
            "gov.cn": 1.5,                # 中央政府
            "pbc.gov.cn": 1.5,            # 中国人民银行
            "xinhuanet.com": 1.2,         # 新华社
            "people.com.cn": 1.2,         # 人民网
            "cninsurance.com": 1.2,       # 中国银行保险报
            "insurance.cn": 1.2,          # 中国保险网
            "10000.com": 1.0,             # 网易保险
            "sina.com.cn": 1.0,           # 新浪财经
            "stcn.com": 1.0,              # 证券时报
            "cs.com.cn": 1.0,             # 中国证券报
            "zqrb.cn": 1.0,               # 证券日报
        }
        
        # 2. 主题重要性评分
        self.topic_scores = {
            "regulatory": {  # 监管政策（最高优先级）
                "score": 10,
                "keywords": [
                    "监管办法", "监管规定", "监管要求", "监管通知", "监管指引",
                    "征求意见", "处罚决定", "行政处罚", "合规要求", "合规管理",
                    "偿付能力", "资金运用", "公司治理", "关联交易", "信息披露",
                    "反洗钱", "反欺诈", "消费者权益保护", "消保",
                ]
            },
            "product": {  # 产品规范
                "score": 8,
                "keywords": [
                    "产品停售", "产品备案", "产品审批", "费率调整", "费率改革",
                    "精算规定", "责任准备金", "保险责任", "条款变更",
                    "健康险", "重疾险", "年金险", "寿险", "财险",
                ]
            },
            "channel": {  # 渠道改革
                "score": 6,
                "keywords": [
                    "个险改革", "银保新规", "数字化渠道", "线上化", "中介渠道",
                    "代理人", "营销员", "增员", "活动率", "人均产能",
                    "网点", "客户经理", "财富管理",
                ]
            },
            "market": {  # 市场动态
                "score": 4,
                "keywords": [
                    "并购", "收购", "重组", "合作", "战略合作", "业绩",
                    "保费收入", "市场份额", "排名", "增资", "发债",
                    "投资收益", "偿付能力", "资产配置",
                ]
            },
            "tech": {  # 科技与创新
                "score": 5,
                "keywords": [
                    "AI", "人工智能", "大模型", "数字化", "科技", "创新",
                    "核保", "理赔", "智能客服", "RPA", "区块链",
                    "数据治理", "数据安全", "隐私保护",
                ]
            },
        }
        
        # 3. 行动紧迫性模式
        self.urgency_patterns = [
            (r"自发布 (?:之 | 起 | 后 | 日)", 5),
            (r"自 (?:\d{4}年\d{1,2}月\d{1,2}日|即日起)", 5),
            (r"于\d{4}年\d{1,2}月\d{1,2}日 (?:前 | 起 | 内)", 4),
            (r"征求意见 (?:截止 | 至 | 于)", 3),
            (r"即日起", 3),
            (r"立即 | 马上 | 即刻 | 从速", 3),
            (r"拟 | 计划 | 考虑 | 准备", 1),
        ]
        
        # 4. 影响范围关键词
        self.impact_keywords = {
            "全行业": 5,
            "保险行业": 4,
            "保险公司": 3,
            "寿险公司": 4,
            "财险公司": 4,
            "保险中介": 3,
            "中介机构": 2,
            "保险集团": 4,
            "分支机构": 2,
        }
    
    def calculate_value(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算新闻价值总分
        
        Args:
            item: 新闻条目（包含 title, link, published_at, source, content 等）
        
        Returns:
            {
                "score": 总分,
                "level": 等级（重要/关注/参考/一般）,
                "reasons": [评分原因列表],
                "breakdown": {各维度得分}
            }
        """
        score = 0
        reasons = []
        breakdown = {}
        
        # 1. 主题分
        topic_score, topic_reason = self._score_topic(item)
        score += topic_score
        breakdown["topic"] = topic_score
        if topic_reason:
            reasons.append(f"主题分：{topic_reason}")
        
        # 2. 来源权重（后续作为乘数）
        source_weight = self._get_source_weight(item.get("link", ""), item.get("source", ""))
        breakdown["source_weight"] = source_weight
        reasons.append(f"来源权重：×{source_weight}")
        
        # 3. 影响范围分
        impact_score = self._score_impact(item)
        score += impact_score
        breakdown["impact"] = impact_score
        if impact_score > 0:
            reasons.append(f"影响分：{impact_score}")
        
        # 4. 时效性分
        time_score = self._score_timeliness(item.get("published_at"))
        score += time_score
        breakdown["timeliness"] = time_score
        if time_score > 0:
            reasons.append(f"时效分：{time_score}")
        
        # 5. 行动紧迫性分
        urgency_score = self._score_urgency(item)
        score += urgency_score
        breakdown["urgency"] = urgency_score
        if urgency_score > 0:
            reasons.append(f"紧迫分：{urgency_score}")
        
        # 应用来源权重
        final_score = score * source_weight
        breakdown["raw_score"] = score
        breakdown["final_score"] = round(final_score, 1)
        
        return {
            "score": round(final_score, 1),
            "level": self._get_level(final_score),
            "reasons": reasons,
            "breakdown": breakdown
        }
    
    def _score_topic(self, item: Dict[str, Any]) -> Tuple[int, str]:
        """评分主题重要性"""
        title = (item.get("title", "") or "").lower()
        content = (item.get("content", "") or "").lower()
        text = title + " " + content
        
        best_score = 0
        best_topic = ""
        
        for topic_name, topic_config in self.topic_scores.items():
            for keyword in topic_config["keywords"]:
                if keyword.lower() in text:
                    if topic_config["score"] > best_score:
                        best_score = topic_config["score"]
                        best_topic = topic_name
        
        reason = f"{best_topic} (+{best_score})" if best_topic else "一般资讯 (+0)"
        return best_score, reason
    
    def _get_source_weight(self, link: str, source: str = "") -> float:
        """获取来源权重"""
        # 优先从链接解析域名
        if link:
            try:
                domain = urlparse(link).netloc.lower()
                # 检查精确匹配
                if domain in self.source_weights:
                    return self.source_weights[domain]
                # 检查域名后缀匹配
                for domain_pattern, weight in self.source_weights.items():
                    if domain.endswith(domain_pattern):
                        return weight
            except Exception:
                pass
        
        # 从来源名称判断
        source_lower = (source or "").lower()
        if "监管" in source_lower or "金融" in source_lower:
            return 1.5
        if "保险报" in source_lower or "官方" in source_lower:
            return 1.2
        
        # 默认权重
        return 1.0
    
    def _score_impact(self, item: Dict[str, Any]) -> int:
        """评分业务影响范围"""
        title = (item.get("title", "") or "").lower()
        content = (item.get("content", "") or "").lower()
        text = title + " " + content
        
        for keyword, score in self.impact_keywords.items():
            if keyword.lower() in text:
                return score
        
        return 0
    
    def _score_timeliness(self, published_at: Optional[str]) -> int:
        """评分时效性"""
        if not published_at:
            return 0  # 没有时间信息，默认 0 分
        
        try:
            # 解析时间
            if isinstance(published_at, str):
                # 尝试多种格式
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                ]:
                    try:
                        pub_time = datetime.strptime(published_at[:19], fmt)
                        pub_time = pub_time.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                else:
                    return 0
            else:
                return 0
            
            # 计算时间差（小时）
            now = datetime.now(timezone.utc)
            hours_diff = (now - pub_time).total_seconds() / 3600
            
            if hours_diff < 24:
                return 3
            elif hours_diff < 72:
                return 2
            elif hours_diff < 168:  # 7 天
                return 1
            else:
                return 0
                
        except Exception:
            return 0
    
    def _score_urgency(self, item: Dict[str, Any]) -> int:
        """评分行动紧迫性"""
        title = item.get("title", "") or ""
        content = item.get("content", "") or ""
        text = title + " " + content
        
        for pattern, score in self.urgency_patterns:
            if re.search(pattern, text):
                return score
        
        return 0
    
    def _get_level(self, score: float) -> str:
        """获取价值等级"""
        if score >= 15:
            return "🔴 重要"
        elif score >= 10:
            return "🟠 关注"
        elif score >= 5:
            return "🟡 参考"
        else:
            return "⚪ 一般"


def test_scorer():
    """测试评分器"""
    scorer = ValueScorer()
    
    # 测试用例 1：监管政策
    item1 = {
        "title": "金融监管总局发布《保险资金运用管理办法》征求意见",
        "link": "https://www.nfra.gov.cn/cn/view/pages/itemDetail.html?docId=xxx",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source": "NFRA 监管动态",
        "content": "自发布之日起施行，各保险公司应立即执行..."
    }
    result1 = scorer.calculate_value(item1)
    print(f"测试 1（监管政策）: {result1['score']}分 - {result1['level']}")
    print(f"  原因：{result1['reasons']}")
    
    # 测试用例 2：市场动态
    item2 = {
        "title": "中国人寿与某银行签署战略合作协议",
        "link": "https://finance.sina.com.cn/money/insurance/xxx",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source": "新浪财经 保险",
        "content": "双方将在银保渠道开展深度合作..."
    }
    result2 = scorer.calculate_value(item2)
    print(f"测试 2（市场动态）: {result2['score']}分 - {result2['level']}")
    print(f"  原因：{result2['reasons']}")
    
    # 测试用例 3：一般资讯
    item3 = {
        "title": "某保险公司召开年度工作会议",
        "link": "https://www.stcn.com/article/xxx",
        "published_at": "2026-02-01T10:00:00Z",
        "source": "证券时报",
        "content": "会议总结了去年工作，部署了今年任务..."
    }
    result3 = scorer.calculate_value(item3)
    print(f"测试 3（一般资讯）: {result3['score']}分 - {result3['level']}")
    print(f"  原因：{result3['reasons']}")


if __name__ == "__main__":
    test_scorer()
