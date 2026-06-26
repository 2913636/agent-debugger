# Agent 全链路调试平台

> Agent 版 Chrome DevTools——记录、回放、分析每一步执行。

## 架构

```
你的 Agent 代码
    ↓ @trace 装饰器
SQLite 追踪数据库
    ↓
Streamlit 可视化面板
```

## 快速开始

```bash
# 1. 安装
pip install streamlit

# 2. 生成测试数据
py demo.py

# 3. 打开面板
streamlit run dashboard.py
```

## 核心能力

- @trace 装饰器：一行代码记录任何函数的输入/输出/耗时
- SQLite 存储：所有追踪数据本地保存
- 可视化面板：时间线、耗时分析、错误定位
- 零依赖：不需要 LangSmith / LangFuse 等外部平台

## 面试价值

- 系统设计能力（追踪架构设计）
- 工程化思维（可观测性）
- 可演示：现场跑 demo → 面板展示追踪结果
