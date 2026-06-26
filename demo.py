"""
Demo: 模拟 Agent 工作流 + 全链路追踪
======================================
模拟竞品分析 Agent，每一步都被追踪记录。
跑完去 dashboard.py 看可视化面板，或 replay.py 回放。

展示：
  - @trace 装饰器：自动追踪函数调用
  - tracer.span() 上下文管理器：追踪代码块（LLM 调用/工具调用）
  - token 追踪：记录每次 LLM 调用的 token 消耗
  - 错误捕获：异常自动记录，不影响其他步骤
"""

import time
import random
from tracer import trace, start_session, end_session, tracer

SESSION = f"debug-{int(time.time())}"


@trace("search_competitor", session_id=SESSION, step_type="tool_call")
def search_competitor(company: str) -> dict:
    """模拟搜索竞品信息"""
    time.sleep(0.3)
    results = {
        "tesla": {"title": "Tesla Q1 delivers 420K vehicles", "source": "Reuters", "sentiment": "neutral"},
        "byd": {"title": "BYD Q1 surpasses 1M vehicles", "source": "Bloomberg", "sentiment": "positive"},
    }
    return results.get(company.lower(), {"title": f"{company} - no data", "source": "unknown"})


@trace("extract_insights", session_id=SESSION, step_type="llm_call")
def extract_insights(data: dict) -> str:
    """模拟 LLM 提取洞察"""
    time.sleep(0.4)
    return f"Analysis: {data.get('title', 'N/A')} | Sentiment: {data.get('sentiment', 'unknown')}"


@trace("generate_report", session_id=SESSION)
def generate_report(insights: list) -> str:
    """模拟生成报告"""
    time.sleep(0.5)
    return f"## Competitive Analysis Report\n\n" + "\n".join(f"- {i}" for i in insights)


@trace("risk_assessment", session_id=SESSION)
def risk_assessment(report: str) -> str:
    """模拟风险评估"""
    time.sleep(0.2)
    risks = ["Data limited to Q1 2026", "Missing private company financials", "News sentiment may lag market"]
    return f"Risks identified: {len(risks)}\n" + "\n".join(f"- {r}" for r in risks)


# ═══ 错误场景会话 ═══
SESSION_ERR = f"error-{int(time.time())}"


@trace("fetch_market_data", session_id=SESSION_ERR, step_type="tool_call")
def fetch_market_data():
    time.sleep(0.2)
    raise ConnectionError("Market API timeout after 30s")


@trace("fallback_search", session_id=SESSION_ERR, step_type="tool_call")
def fallback_search():
    time.sleep(0.15)
    return "Cached market data from 2 hours ago"


if __name__ == "__main__":
    print("Agent Debugger Demo")
    print("=" * 60)

    # ── 场景 1：正常 Agent 工作流 ──
    print("\n[1/3] Simulating competitive analysis agent workflow...\n")
    start_session(SESSION, "competitive-analysis-tesla-vs-byd",
                  agent_name="competitive-researcher",
                  tags="demo,success",
                  metadata={"companies": ["tesla", "byd"], "mode": "full"})

    # 使用装饰器追踪的函数
    tesla_data = search_competitor("tesla")
    byd_data = search_competitor("byd")

    # 使用上下文管理器追踪 LLM 调用（更精细的控制）
    with tracer.span("analyze_tesla", SESSION, "llm_call") as span:
        span.input_data = str(tesla_data)[:200]
        insights_tesla = extract_insights(tesla_data)
        span.output_data = insights_tesla[:200]
        span.tokens = 850  # 模拟 token 消耗

    with tracer.span("analyze_byd", SESSION, "llm_call") as span:
        span.input_data = str(byd_data)[:200]
        insights_byd = extract_insights(byd_data)
        span.output_data = insights_byd[:200]
        span.tokens = 920

    report = generate_report([insights_tesla, insights_byd])
    risks = risk_assessment(report)

    end_session(SESSION)
    print("  [OK] Normal workflow completed: 7 steps recorded")

    # ── 场景 2：错误处理 ──
    print("\n[2/3] Simulating error scenario...\n")
    start_session(SESSION_ERR, "api-timeout-recovery",
                  agent_name="market-researcher",
                  tags="demo,error,recovery")

    try:
        fetch_market_data()
    except ConnectionError:
        print("  [!] Expected error caught: Market API timeout")

    fallback = fallback_search()

    end_session(SESSION_ERR, "completed")
    print("  [OK] Error scenario completed: error recorded, fallback executed")

    # ── 场景 3：摘要 ──
    print("\n[3/3] Summary")
    print("-" * 40)
    from tracer import get_summary
    s = get_summary()
    print(f"  Total sessions: {s['total_sessions']}")
    print(f"  Total steps:    {s['total_steps']}")
    print(f"  Errors:         {s['errors']}")
    print(f"  Total time:     {s['total_time_ms']}ms")
    print(f"  Total tokens:   {s['total_tokens']}")

    print(f"\n  All trace data saved to traces.db")
    print(f"  Run: streamlit run dashboard.py   (visual panel)")
    print(f"  Run: py replay.py                 (step-by-step replay)")
