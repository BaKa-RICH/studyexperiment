#!/bin/bash
# Cursor 多 Agent 协作模板 v2 — 一键部署脚本
#
# 用法：
#   方式 1（从解压目录安装）：
#     cd /path/to/your-project
#     bash /path/to/cursor-multi-agent/install.sh
#
#   方式 2（解压 + 安装一步到位）：
#     cd /path/to/your-project
#     tar -xzf cursor-multi-agent-v2.tar.gz && bash cursor-multi-agent/install.sh
#
#   方式 3（指定目标目录）：
#     bash install.sh /path/to/your-project
#
# 安装内容：
#   .cursor/agents/   4 个 Agent（Opus 主执行 / GPT·Sonnet·Gemini 审阅）
#   .cursor/rules/    协作规则（multi-agent-collaboration.mdc）
#   build_forum.py    JSON → HTML 讨论面板生成器
#   task_forum.json   讨论记录起始模板（已存在则跳过）
#   PROMPT_开场模板.txt 开场指令模板（已存在则跳过）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$(pwd)}"

if [ ! -d "$TARGET_DIR" ]; then
    echo "错误：目标目录 $TARGET_DIR 不存在"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Cursor 多 Agent 协作模板 v2 — 一键部署  ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  源目录: $SCRIPT_DIR"
echo "  目标:   $TARGET_DIR"
echo ""

# ──────────────────────────────────────────────
# 1. Agent 配置
# ──────────────────────────────────────────────
echo "[1/5] 安装 Agent 配置..."
mkdir -p "$TARGET_DIR/.cursor/agents"
for f in opus-executor.md gpt-reviewer.md sonnet-reviewer.md gemini-reviewer.md; do
    cp "$SCRIPT_DIR/.cursor/agents/$f" "$TARGET_DIR/.cursor/agents/"
done
echo "    ✓ opus-executor / gpt-reviewer / sonnet-reviewer / gemini-reviewer"

# ──────────────────────────────────────────────
# 2. 协作规则
# ──────────────────────────────────────────────
echo "[2/5] 安装协作规则..."
mkdir -p "$TARGET_DIR/.cursor/rules"
cp "$SCRIPT_DIR/.cursor/rules/multi-agent-collaboration.mdc" "$TARGET_DIR/.cursor/rules/"
echo "    ✓ multi-agent-collaboration.mdc"

# ──────────────────────────────────────────────
# 3. 讨论面板生成器
# ──────────────────────────────────────────────
echo "[3/5] 安装 build_forum.py..."
cp "$SCRIPT_DIR/build_forum.py" "$TARGET_DIR/"
echo "    ✓ build_forum.py"

# ──────────────────────────────────────────────
# 4. 起始模板（已存在则跳过，不覆盖用户数据）
# ──────────────────────────────────────────────
echo "[4/5] 安装起始模板..."

if [ ! -f "$TARGET_DIR/task_forum.json" ]; then
    cp "$SCRIPT_DIR/task_forum.json" "$TARGET_DIR/"
    echo "    ✓ task_forum.json（新建）"
else
    echo "    - task_forum.json 已存在，跳过"
fi

if [ ! -f "$TARGET_DIR/PROMPT_开场模板.txt" ]; then
    cp "$SCRIPT_DIR/PROMPT_开场模板.txt" "$TARGET_DIR/"
    echo "    ✓ PROMPT_开场模板.txt（新建）"
else
    echo "    - PROMPT_开场模板.txt 已存在，跳过"
fi

# ──────────────────────────────────────────────
# 5. 清理旧版文件（如果从 v1 升级）
# ──────────────────────────────────────────────
echo "[5/5] 清理旧版文件..."
CLEANED=0
for old_file in "$TARGET_DIR/.cursor/agents/sonnet-executor.md" "$TARGET_DIR/.cursor/agents/opus-reviewer.md"; do
    if [ -f "$old_file" ]; then
        rm "$old_file"
        echo "    ✓ 已删除旧文件 $(basename "$old_file")"
        CLEANED=1
    fi
done
if [ $CLEANED -eq 0 ]; then
    echo "    - 无旧版文件需要清理"
fi

# ──────────────────────────────────────────────
# 完成
# ──────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║             部署完成！                    ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "已安装文件："
echo "  .cursor/agents/opus-executor.md      主 Agent (claude-opus-4-6-fast-max)"
echo "  .cursor/agents/gpt-reviewer.md       代码审阅 (gpt-5.3-codex-high)"
echo "  .cursor/agents/sonnet-reviewer.md    架构审阅 (claude-sonnet-4-6)"
echo "  .cursor/agents/gemini-reviewer.md    综合审阅 (gemini-3.1-pro)"
echo "  .cursor/rules/multi-agent-collaboration.mdc"
echo "  build_forum.py"
echo ""
echo "使用方法："
echo "  1. 在 Cursor 中选择 Opus 4.6 作为主模型，开启 Max 模式"
echo "  2. 新建 Agent 对话"
echo "  3. 将 PROMPT_开场模板.txt 内容粘贴到对话框"
echo "  4. 修改 task_slug 和任务描述，发送即可"
echo ""
echo "提示：若子 Agent model 报错，改对应 .cursor/agents/*.md 的 model 为 inherit"
echo ""
