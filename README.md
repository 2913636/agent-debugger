# Agent 全链路调试平台

> Agent 版 Chrome DevTools —— 记录、回放、分析每一步执行。

## 架构

```
你的 Agent 代码
    |-- @trace 装饰器（自动追踪函数调用）
    |-- tracer.span() 上下文管理器（追踪代码块/LLM调用）
    ↓
SQLite 追踪数据库（本地，零外部依赖）
    ↓
┌─────────────────┬──────────────────┬─────────────────┐
│ dashboard.py    │ replay.py        │ export          │
│ Streamlit 面板  │ 逐步回放执行过程  │ JSON/CSV 导出   │
└─────────────────┴──────────────────┴─────────────────┘
```

## 快速开始

```bash
# 1. 安装
pip install streamlit

# 2. 生成测试数据
py demo.py

# 3. 打开可视化面板
streamlit run dashboard.py

# 4. 回放执行过程
py replay.py
```

## 核心能力

| 功能 | 说明 |
|------|------|
| `@trace` 装饰器 | 一行代码追踪任何函数的输入/输出/耗时 |
| `tracer.span()` | 上下文管理器，追踪 LLM 调用、工具调用等代码块 |
| Token 追踪 | 记录每次 LLM 调用的 token 消耗 |
| 错误捕获 | 异常自动捕获，包含完整 traceback |
| 可视化面板 | 时间线、步骤详情、耗时排行、错误分析 |
| 回放引擎 | 逐步重现 Agent 执行过程，支持自动播放/手动步进 |
| 会话对比 | 对比两个会话的执行差异（步骤数/耗时/错误率） |
| 搜索 | 跨会话搜索追踪数据 |
| 导出 | JSON/CSV 导出，可外部分析 |

## 集成到你的 Agent

```python
from tracer import trace, start_session, end_session, tracer

start_session("run-001", "customer-support", agent_name="support-bot")

# 模式 1：装饰器
@trace("search_knowledge_base", session_id="run-001", step_type="tool_call")
def search(query): ...

# 模式 2：上下文管理器
with tracer.span("call_llm", "run-001", "llm_call") as span:
    span.input_data = prompt[:200]
    response = client.chat(prompt)
    span.output_data = response[:500]
    span.tokens = response.usage.total_tokens

end_session("run-001")
```

## 项目结构

```
agent-debugger/
├── tracer.py       # 核心追踪引擎（@trace + span + 查询 + 导出）
├── dashboard.py    # Streamlit 可视化面板
├── replay.py       # 回放引擎（逐步重现 + 会话对比）
├── demo.py         # 演示：模拟 Agent 工作流
└── README.md
```

## 面试价值

- 系统设计能力：追踪架构设计（装饰器 + 上下文管理器 + SQLite + 可视化）
- 工程化思维：可观测性、错误定位、性能分析
- 可演示：现场跑 demo → 面板展示 → 回放执行过程
