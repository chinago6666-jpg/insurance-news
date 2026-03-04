# 保险新闻自动采集推送系统

自动采集保险行业新闻，智能评分筛选，生成结构化报告，并推送到飞书。

## 功能特点

- 📥 **自动采集**：从多个源（监管机构、财经媒体）采集保险新闻
- 🎯 **智能过滤**：基于关键词和规则评分，自动过滤低质量内容
- 📊 **评分系统**：可配置的评分阈值，筛选高价值新闻
- 📝 **报告生成**：Obsidian 风格的 Markdown 报告，支持 Callouts
- 📤 **飞书推送**：自动推送到指定飞书用户，支持完整报告
- ⏰ **定时任务**：支持 cron 定时自动执行
- 🚨 **错误告警**：失败时自动发送告警消息到飞书
- 📈 **日志记录**：详细的执行日志和统计信息

## 项目结构

```
Insurance-news/
├── auto_run.sh          # 自动执行脚本（顺序执行所有任务）
├── collect_news.py      # 新闻采集脚本
├── build_report.py      # 报告生成脚本
├── push_feishu.py       # 飞书推送脚本
├── send_alert.py        # 错误告警脚本
├── config/
│   ├── sources.yaml     # 新闻源配置（支持过滤器）
│   ├── keywords.yaml    # 关键词和评分配置
│   ├── feishu.yaml      # 飞书配置
│   └── report_template.md  # 报告模板
├── runs/                # 运行输出（git 忽略）
├── logs/                # 日志文件（git 忽略）
└── state/               # 状态数据（git 忽略）
```

## 快速开始

### 1. 安装依赖

```bash
# 克隆项目
git clone https://github.com/chinago6666-jpg/insurance-news.git
cd insurance-news

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install beautifulsoup4 pyyaml
```

### 2. 配置飞书

编辑 `config/feishu.yaml`：

```yaml
push:
  top_n: 5
  include_local_path: true
  include_report: true  # 在消息中包含完整报告
  app_id: "你的飞书 App ID"
  app_secret: "你的飞书 App Secret"
  user_open_id: "你的飞书用户 Open ID"
```

### 3. 配置新闻源

编辑 `config/sources.yaml` 添加或修改新闻源：

```yaml
sources:
  - name: "NFRA 监管动态"
    type: "web_list"
    region: "cn"
    url: "https://www.nfra.gov.cn/..."
    selectors:
      item: ".rightList li"
      title: "a"
      link: "a"
      date: "span"
    filters:
      title_min_length: 10  # 标题至少 10 个字符
      exclude_keywords: ["首页", "栏目", "导航"]
```

### 4. 配置评分规则

编辑 `config/keywords.yaml`：

```yaml
buckets:
  regulatory:
    zh: ["监管", "征求意见", "处罚", "合规"]
  company_market:
    zh: ["并购", "合作", "业绩", "战略"]

scoring:
  min_score_to_include: 2  # 入库阈值（>=2 分的新闻）
  cn_boost: 1              # 中文新闻加分
```

### 5. 运行

```bash
# 手动执行一次（推荐）
./auto_run.sh

# 或分步执行
.venv/bin/python collect_news.py
.venv/bin/python build_report.py
.venv/bin/python push_feishu.py
```

### 6. 配置定时任务（可选）

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天早上 8 点自动执行）
0 8 * * * /path/to/Insurance-news/auto_run.sh
```

## 输出示例

### 飞书消息

```
📰 保险日报 Top5（2026-03-05）

1. 监管动态标题
   🔗 https://... | ⭐4 分

━━━━━━━━━━━━━━━━━━━━━━━━
📄 完整报告内容
━━━━━━━━━━━━━━━━━━━━━━━━

# 保险行业日报（2026-03-05）
...
```

### 报告格式

```markdown
# 寿险数字化渠道管理简报（2026-03-05）

`#insurance` `#daily-brief` `#digital-channel`

> [!info] 简报信息
> - 日期：2026-03-05
> - 视角：数字化渠道总经理

> [!summary] 今日要点（Top 5）

## 中国监管快讯
> [!warning] 监管影响

## 72 小时行动清单
- [ ] 明确负责人
- [ ] 明确动作
- [ ] 明确截止时间
```

### 执行日志

```
[2026-03-05 08:00:00] ==========================================
[2026-03-05 08:00:00] 保险新闻自动采集推送开始
[2026-03-05 08:00:00] ==========================================
[2026-03-05 08:00:00] ✅ 虚拟环境检查通过
[2026-03-05 08:00:00] 
[2026-03-05 08:00:00] 📥 任务 1/3: 开始收集新闻...
[2026-03-05 08:00:01] ✅ 任务 1 完成：新闻收集成功
[2026-03-05 08:00:01] 
[2026-03-05 08:00:01] 📝 任务 2/3: 开始生成报告...
[2026-03-05 08:00:02] ✅ 任务 2 完成：报告生成成功
[2026-03-05 08:00:02] 
[2026-03-05 08:00:02] 📤 任务 3/3: 开始推送到飞书...
[2026-03-05 08:00:03] ✅ 任务 3 完成：飞书推送成功
[2026-03-05 08:00:03] 
[2026-03-05 08:00:03] 📊 执行摘要：
[2026-03-05 08:00:03]    - 日期：2026-03-05
[2026-03-05 08:00:03]    - 开始时间：08:00:00
[2026-03-05 08:00:03]    - 结束时间：08:00:03
[2026-03-05 08:00:03]    - 入库新闻数量：5 条
```

## 配置说明

### 新闻源配置（sources.yaml）

```yaml
sources:
  - name: "新闻源名称"
    type: "web_list"  # 或 "rss"
    region: "cn"
    url: "https://..."
    selectors:
      item: ".news-item"
      title: "h2 a"
      link: "a"
      date: "span.time"
    filters:
      title_min_length: 10
      exclude_keywords: ["首页", "专题"]
```

### 关键词配置（keywords.yaml）

```yaml
buckets:
  regulatory:  # 监管类
    zh: ["监管", "处罚", "合规"]
  company_market:  # 公司市场类
    zh: ["并购", "业绩", "战略"]

scoring:
  min_score_to_include: 2  # 入库阈值
  cn_boost: 1  # 中文新闻加分
```

### 飞书配置（feishu.yaml）

```yaml
push:
  top_n: 5  # 推送 Top N 条新闻
  include_local_path: true  # 包含本地报告路径
  include_report: true  # 包含完整报告内容
  app_id: "cli_xxx"
  app_secret: "xxx"
  user_open_id: "ou_xxx"
```

## 错误告警

系统会自动检测以下错误并发送飞书告警：

- ❌ 虚拟环境缺失（critical）
- ❌ 新闻采集失败（error）
- ❌ 报告生成失败（error）
- ❌ 飞书推送失败（error）

告警消息包含错误信息和日志文件路径。

## 日志查看

```bash
# 查看今日日志
cat logs/auto_run_2026-03-05.log

# 查看最新报告
cat runs/2026-03-05/report.md

# 查看历史报告
ls -la runs/
```

## 常见问题

### 1. 飞书推送失败

检查 `config/feishu.yaml` 中的凭证是否正确，确保飞书应用有发送消息权限。

### 2. 新闻采集太少

- 检查 `config/sources.yaml` 中的选择器是否正确
- 降低 `config/keywords.yaml` 中的 `min_score_to_include` 阈值
- 添加更多新闻源

### 3. 定时任务不执行

检查 cron 日志（macOS）：
```bash
log show --predicate 'process == "cron"' --last 1h
```

### 4. 告警消息收不到

检查 `send_alert.py` 中的飞书配置是否正确。

## 更新日志

### v1.1.0 (2026-03-04)
- ✅ 添加错误告警功能（send_alert.py）
- ✅ 优化日志格式（执行摘要、新闻统计）
- ✅ 调整评分阈值（从 3 分降到 2 分）
- ✅ 添加新闻源过滤器（标题长度、关键词排除）
- ✅ 优化日志输出格式

### v1.0.0 (2026-03-04)
- ✅ 初始版本
- ✅ 支持新闻采集、报告生成、飞书推送
- ✅ 支持 cron 定时任务

## License

MIT

## 作者

林志鹏（Boss）

## GitHub

https://github.com/chinago6666-jpg/insurance-news
