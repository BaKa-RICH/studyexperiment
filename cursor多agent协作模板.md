主 Agent（Opus）+ 审阅 Agent（GPT / Sonnet / Gemini）协作工作流，可一键部署到任意 Cursor 项目。
一键部署

# 解压 + 安装，一行搞定
cd /path/to/your-project
tar -xzf cursor-multi-agent-v2.tar.gz && bash cursor-multi-agent/install.sh

或者指定目标目录：

bash cursor-multi-agent/install.sh /path/to/your-project

安装脚本会自动：
- 复制 4 个 Agent 配置到 .cursor/agents/
- 复制协作规则到 .cursor/rules/
- 复制 build_forum.py 讨论面板生成器
- 复制起始模板（已存在则跳过，不覆盖用户数据）
- 清理旧版 v1 文件（sonnet-executor.md、opus-reviewer.md）
  

---

使用方法

1. 选择模型：在 Cursor 中选择 Opus 4.6 作为主模型
2. 开启 Max 模式：否则子 Agent 会退化为 Composer
3. 新建 Agent 对话，将 PROMPT_开场模板.txt 内容粘贴进去
4. 修改两处 <<<...>>> 标记：task_slug 和任务描述
5. 发送，Opus 会自动协调三个审阅者协作执行
6. 查看讨论面板：python build_forum.py <task_slug>，浏览器打开 <task_slug>.html
  

---

核心特性

v1 基础功能
- 每个 step/action 执行前必须讨论（PROPOSAL → REVIEW → VOTE）
- 任一 Agent 意见须被其余 3 个充分审核
- 意见不一致时 4 方投票，少数服从多数
- 平票或无法统一时，Question Board 争取用户意见
  
v2 新增功能
- 共享 Context：搜索/分析阶段随时追加 CONTEXT_SHARE，不等结论才同步；Agent 间主动 @tag 传递跨任务线索
- 并行子任务：Opus 将复杂任务拆分为子任务表分配给三位审阅者并行执行
- SUBTASK_RESULT：各 Agent 完成子任务后汇报结果，Opus 汇总后发起全员投票
- 实时 HTML 面板：每次写入 JSON 后自动刷新 HTML，随时可查看讨论进展
  

---

工作流

Opus（主 Agent）
  │
  │ 1. 发布 CONTEXT_SHARE（搜集到的初始信息）
  │ 2. 发布 PROPOSAL（方案或子任务分配表）
  │
  ├─→ GPT    REVIEW + 执行 SUB-A（并行）
  ├─→ Sonnet REVIEW + 执行 SUB-B（并行）
  └─→ Gemini REVIEW + 执行 SUB-C（并行）
        │
        │ 任意 Agent 发现跨任务线索 → CONTEXT_SHARE + @tag
        │ 各自完成后追加 SUBTASK_RESULT
        │ 每次更新 JSON 后立即刷新 HTML
        │
        ▼
  Opus 汇总 → VOTE（4方）→ EXECUTION 或 QA（用户参与）

消息类型

type
发送者
说明
CONTEXT_SHARE
任意
共享重要 context，其他 Agent 可 REPLY
PROPOSAL
Opus
提出方案或子任务分配
REVIEW
审阅者
审阅 PROPOSAL
SUBTASK_RESULT
被分配者
子任务执行结果
REPLY
任意
回复他人消息，补充关联知识
VOTE
任意
投票表态
EXECUTION
Opus
执行已通过的方案
QA
Opus
需要用户参与决策


---

打包内容

cursor-multi-agent/
├── .cursor/
│   ├── agents/
│   │   ├── opus-executor.md       主 Agent（执行 + 分发子任务）
│   │   ├── gpt-reviewer.md        代码正确性 & 边界情况审阅
│   │   ├── sonnet-reviewer.md     架构 & 逻辑审阅
│   │   └── gemini-reviewer.md     依赖 & 性能 & 测试审阅
│   └── rules/
│       └── multi-agent-collaboration.mdc
├── build_forum.py                 JSON → HTML 讨论面板生成器
├── task_forum.json                起始模板
├── PROMPT_开场模板.txt             开场指令（带使用说明）
├── install.sh                     一键部署脚本
└── README.md


---

模型配置

Agent
模型 ID
厂商
价格（输入/输出 per 1M）
Opus（主）
claude-opus-4-6-fast-max
Anthropic
$30 / $150
GPT
gpt-5.3-codex-high
OpenAI
$1.75 / $14
Sonnet
claude-sonnet-4-6
Anthropic
$3 / $15
Gemini
gemini-3.1-pro
Google
$2 / $12

模型 ID 若在 Cursor 中不可用，将对应 .cursor/agents/*.md 的 model 改为 inherit 即可兜底使用主对话模型。


---

前置条件

- Cursor 2.0+（开启 Max 模式）
- Python 3.6+（用于 build_forum.py）