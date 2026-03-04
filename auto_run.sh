#!/bin/bash
# 保险新闻自动采集推送脚本
# 按顺序执行：collect_news -> build_report -> push_feishu
# 每个任务完成后才执行下一个

set -e  # 任何命令失败则停止

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
LOG_DIR="$SCRIPT_DIR/logs"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 日志文件
LOG_FILE="$LOG_DIR/auto_run_${DATE}.log"

# 日志函数
log() {
    echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "保险新闻自动采集推送开始"
log "=========================================="

# 检查虚拟环境
if [ ! -f "$VENV_PYTHON" ]; then
    log "❌ 错误：虚拟环境不存在：$VENV_PYTHON"
    exit 1
fi

log "✅ 虚拟环境检查通过"

# 任务 1: 收集新闻
log ""
log "📥 任务 1/3: 开始收集新闻..."
if "$VENV_PYTHON" "$SCRIPT_DIR/collect_news.py" --log-level INFO >> "$LOG_FILE" 2>&1; then
    log "✅ 任务 1 完成：新闻收集成功"
else
    log "❌ 任务 1 失败：新闻收集失败"
    exit 1
fi

# 任务 2: 生成报告
log ""
log "📝 任务 2/3: 开始生成报告..."
if "$VENV_PYTHON" "$SCRIPT_DIR/build_report.py" --log-level INFO >> "$LOG_FILE" 2>&1; then
    log "✅ 任务 2 完成：报告生成成功"
else
    log "❌ 任务 2 失败：报告生成失败"
    exit 1
fi

# 任务 3: 推送到飞书
log ""
log "📤 任务 3/3: 开始推送到飞书..."
if "$VENV_PYTHON" "$SCRIPT_DIR/push_feishu.py" --log-level INFO >> "$LOG_FILE" 2>&1; then
    log "✅ 任务 3 完成：飞书推送成功"
else
    log "❌ 任务 3 失败：飞书推送失败"
    exit 1
fi

log ""
log "=========================================="
log "✅ 所有任务执行完成！"
log "=========================================="
log ""

# 显示摘要
log "执行摘要："
log "- 日期：$DATE"
log "- 日志文件：$LOG_FILE"
log "- 报告路径：$SCRIPT_DIR/runs/$DATE/report.md"

exit 0
