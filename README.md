# Insurance News Pipeline

面向寿险公司数字化渠道管理场景的行业情报流水线：  
按日完成「采集 -> 去重评分总结 -> 飞书推送」。

## 功能概览

- Task A `collect_news.py`
  - 读取 `config/sources.yaml`
  - 抓取 RSS / 网页列表页（`web_list`）
  - 产出 `runs/<date>/raw_items.json`
  - 支持 `--offline-from` 离线导入本地 JSON（无外网可跑通）

- Task B `build_report.py`
  - 读取 `raw_items.json`
  - URL 归一化 + `state/seen_urls.json` 去重
  - 标题去重（hash + 包含关系）
  - 关键词桶打标签与评分（监管加分、中国加分）
  - 生成结构化总结（模型可选，默认规则兜底）
  - 产出 `dedup_items.json` / `scored_items.json` / `summaries.json` / `report.md`
  - 更新 `state/seen_urls.json`、`state/seen_titles.json`

- Task C `push_feishu.py`
  - 读取当天 `summaries.json`
  - 按 `score` 取 Top N（默认 5）
  - 生成飞书文本消息（每条：结论 + 链接）
  - 附加本地报告路径
  - 推送到 `config/feishu.yaml` 的 webhook

## 目录结构

```text
.
├── collect_news.py
├── build_report.py
├── push_feishu.py
├── config/
│   ├── sources.yaml
│   ├── keywords.yaml
│   ├── report_template.md
│   └── feishu.yaml
├── runs/
│   └── YYYY-MM-DD/
│       ├── raw_items.json
│       ├── dedup_items.json
│       ├── scored_items.json
│       ├── summaries.json
│       └── report.md
├── state/
│   ├── seen_urls.json
│   └── seen_titles.json
└── logs/
    └── run.log
```

## 快速开始

在项目根目录运行：

```bash
cd /Users/yyhome/Documents/Insurance-news
```

### 1) Task A 采集

联网模式：

```bash
python3 collect_news.py --root /Users/yyhome/Documents/Insurance-news --date 2026-03-04 --log-level INFO
```

离线模式（推荐在无外网环境调试）：

```bash
python3 collect_news.py --root /Users/yyhome/Documents/Insurance-news --date 2026-03-04 --offline-from /Users/yyhome/Documents/Insurance-news/runs/2026-03-04/offline_seed.json --log-level INFO
```

### 2) Task B 成稿

```bash
python3 build_report.py --root /Users/yyhome/Documents/Insurance-news --date 2026-03-04 --log-level INFO
```

### 3) Task C 推送飞书

先预览不推送：

```bash
python3 push_feishu.py --root /Users/yyhome/Documents/Insurance-news --date 2026-03-04 --dry-run
```

实际推送：

```bash
python3 push_feishu.py --root /Users/yyhome/Documents/Insurance-news --date 2026-03-04
```

## 配置说明

- `config/sources.yaml`：新闻源配置（RSS / `web_list`）
- `config/keywords.yaml`：主题桶与评分参数（含 `min_score_to_include`、`cn_boost`）
- `config/report_template.md`：报告模板（当前为 Obsidian 风格）
- `config/feishu.yaml`：飞书 webhook 与推送参数

## 常见问题

- 无法抓取外网（DNS 报错）：
  - 使用 Task A 的 `--offline-from` 跑通流程
- `summaries.json` 有数据但报告为空：
  - 检查 `keywords.yaml` 的评分阈值是否过高
- 今天抓不到新内容：
  - 可能被 `state/seen_urls.json` / `seen_titles.json` 过滤，可用新日期运行或清理状态

## 安全建议

- 不要把真实 webhook、密钥提交到仓库
- `runs/`、`state/`、`logs/` 建议保持在 `.gitignore` 中
