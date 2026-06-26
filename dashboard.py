"""
Agent 全链路调试面板
====================
Streamlit 可视化追踪面板——Agent 版 Chrome DevTools。
"""

import streamlit as st
from tracer import get_sessions, get_traces, get_summary

st.set_page_config(page_title="Agent 调试面板", page_icon="🔍", layout="wide")
st.title("🔍 Agent 全链路调试面板")

# ═══ 总览卡片 ═══
summary = get_summary()
c1, c2, c3, c4 = st.columns(4)
c1.metric("会话总数", summary["total_sessions"])
c2.metric("执行步骤", summary["total_steps"])
c3.metric("错误数", summary["errors"])
c4.metric("错误率", summary["error_rate"])

st.divider()

# ═══ 会话列表 ═══
sessions = get_sessions()
if not sessions:
    st.info("📋 暂无追踪数据。先运行 demo.py 生成测试数据。")
    st.code("py demo.py")
    st.stop()

st.subheader(f"📋 会话列表（{len(sessions)} 个）")

for s in sessions:
    sid = s["session_id"]
    status_icon = {"completed": "✅", "running": "🔄", "failed": "❌"}.get(s["status"], "❓")
    with st.expander(
        f"{status_icon} {s['task_name']} — "
        f"{s['total_steps']} 步 / {s['total_duration_ms']}ms / {s['status']}"
    ):
        traces = get_traces(sid)
        if not traces:
            st.write("无步骤数据")
            continue

        # 步骤时间线
        st.write("**执行时间线：**")
        for t in traces:
            icon = {"success": "✅", "error": "❌"}.get(t["status"], "⚪")
            bar = "█" * max(1, t["duration_ms"] // 50)
            st.write(
                f"{icon} **{t['step_name']}** "
                f"({t['duration_ms']}ms) `{'░' * (10 - len(bar))}{bar}`"
            )

            if t.get("error_msg"):
                st.error(f"   ⚠️ {t['error_msg']}")

        # 耗时最长的步骤
        st.write("**⏱️ 耗时分析：**")
        sorted_traces = sorted(traces, key=lambda x: x["duration_ms"] or 0, reverse=True)
        for t in sorted_traces[:3]:
            st.write(f"- {t['step_name']}: {t['duration_ms']}ms")

st.divider()
st.caption("💡 先跑 `py demo.py` 生成测试数据，再回来看面板。")
