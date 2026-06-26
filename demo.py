"""
Demo: 模拟 Agent 工作流 + 全链路追踪
======================================
模拟竞品分析 Agent，每一步都被 @trace 自动记录。
跑完去 dashboard.py 看追踪面板。
"""

import time
import random
from tracer import trace, start_session, end_session

SESSION = f"debug-{int(time.time())}"


@trace("搜索特斯拉", session_id=SESSION)
def search_tesla():
    time.sleep(0.3)
    return {"title": "特斯拉 Q1 交付 42 万辆", "source": "Reuters"}


@trace("搜索比亚迪", session_id=SESSION)
def search_byd():
    time.sleep(0.25)
    return {"title": "比亚迪 Q1 突破 100 万辆", "source": "Bloomberg"}


@trace("分析数据", session_id=SESSION)
def analyze(data: str):
    time.sleep(0.4)
    return f"分析结果：{data[:50]}... => 比亚迪销量领先 2.4 倍"


@trace("生成报告", session_id=SESSION)
def generate(analysis: str):
    time.sleep(0.5)
    return f"《2026 新能源车竞争力报告》\n{analysis}"


@trace("风险评估", session_id=SESSION)
def risk_check(report: str):
    time.sleep(0.2)
    return "风险：数据仅限 Q1，未覆盖全年"


# ═══ 模拟一次"错误步骤"的会话 ═══
SESSION2 = f"error-{int(time.time())}"


@trace("调用搜索 API", session_id=SESSION2)
def search_with_error():
    time.sleep(0.2)
    raise ConnectionError("API 连接超时")


if __name__ == "__main__":
    # ── 正常会话 ──
    print("🔍 模拟竞品分析 Agent 工作流...\n")
    start_session(SESSION, "竞品分析-特斯拉vs比亚迪", "竞品研究员")

    data1 = search_tesla()
    data2 = search_byd()
    analysis = analyze(f"{data1}, {data2}")
    report = generate(analysis)
    risk_check(report)

    end_session(SESSION)

    print("✅ 正常会话完成")

    # ── 错误会话 ──
    print("\n⚠️ 模拟 API 超时错误...")
    start_session(SESSION2, "搜索失败场景", "搜索Agent")
    try:
        search_with_error()
    except ConnectionError:
        pass
    end_session(SESSION2, "failed")

    print("✅ 错误会话已记录")
    print(f"\n📊 所有追踪数据已存入 traces.db")
    print("💡 运行 streamlit run dashboard.py 查看追踪面板")
