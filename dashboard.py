"""
Agent 全链路调试面板
====================
Streamlit 可视化追踪面板 —— Agent 版 Chrome DevTools。

功能：
  - 总览卡片：会话数/步骤数/错误率/总耗时
  - 会话列表：展开查看每步执行细节
  - 时间线视图：每个步骤的耗时条
  - 错误分析：定位失败步骤及原因
  - 搜索：跨会话搜索追踪数据
  - 导出：JSON/CSV 下载
"""

import streamlit as st
import pandas as pd
from tracer import (
    get_sessions, get_traces, get_summary,
    search_traces, export_session,
)

st.set_page_config(page_title="Agent 调试面板", page_icon="debug", layout="wide")
st.title("Agent 全链路调试平台")
st.caption("Agent 版 Chrome DevTools —— 记录、回放、分析每一步执行")

# ═══ 侧边栏 ═══
with st.sidebar:
    st.header("controls")
    view_mode = st.radio(
        "view",
        ["sessions", "search", "export_data"],
        format_func=lambda x: {"sessions": "sessions", "search": "search",
                               "export_data": "export"}[x],
        label_visibility="collapsed",
    )

# ═══ 总览卡片 ═══
summary = get_summary()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("sessions", summary["total_sessions"])
c2.metric("total steps", summary["total_steps"])
c3.metric("errors", summary["errors"],
          delta=f"-{summary['error_rate']}" if summary["errors"] == 0 else summary["error_rate"],
          delta_color="off")
c4.metric("total time", f"{summary['total_time_ms']:,}ms")
c5.metric("total tokens", f"{summary['total_tokens']:,}")

st.divider()

# ═══ 会话视图 ═══
if view_mode == "sessions":
    status_filter = st.selectbox(
        "filter by status", ["all", "completed", "running", "failed"],
        key="status_filter"
    )
    sessions = get_sessions(
        limit=100,
        status="" if status_filter == "all" else status_filter
    )

    if not sessions:
        st.info("No trace data yet. Run demo first: `py demo.py`")
        st.code("py demo.py")
        st.stop()

    st.subheader(f"sessions ({len(sessions)})")

    for s in sessions:
        sid = s["session_id"]
        status_icon = {"completed": "ok", "running": "running", "failed": "error"}.get(
            s["status"], "?"
        )
        error_badge = f" [{s.get('error_count', 0)} errors]" if s.get("error_count", 0) > 0 else ""

        with st.expander(
            f"{status_icon} **{s['task_name']}** — "
            f"{s['total_steps']} steps / {s['total_duration_ms']}ms / "
            f"{s.get('total_tokens', 0)} tokens{error_badge}",
            expanded=len(sessions) == 1,
        ):
            traces = get_traces(sid)
            if not traces:
                st.write("no trace data")
                continue

            # ── 会话元信息 ──
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            meta_col1.write(f"**agent:** {s.get('agent_name', '-')}")
            meta_col2.write(f"**tags:** {s.get('tags', '-')}")
            meta_col3.write(f"**created:** {s.get('created_at', '-')}")

            # ── 时间线 ──
            st.write("**timeline:**")
            max_duration = max(t["duration_ms"] or 1 for t in traces)

            timeline_data = []
            for t in traces:
                pct = max(1, (t["duration_ms"] or 0) / max(max_duration, 1) * 100)
                bar = "#" * max(1, int(pct / 2))
                icon = "x" if t["status"] == "error" else "ok"
                timeline_data.append({
                    "step": t["step_order"],
                    "name": t["step_name"],
                    "type": t.get("step_type", "function"),
                    "status": icon,
                    "duration": f"{t['duration_ms']}ms",
                    "bar": bar,
                    "pct": f"{pct:.0f}%",
                })

            for item in timeline_data:
                cols = st.columns([0.5, 2, 1, 1.5, 3])
                cols[0].write(item["step"])
                cols[1].write(f"{item['status']} **{item['name']}**")
                cols[2].write(f"[{item['type']}]")
                cols[3].write(item["duration"])
                cols[4].write(f"`{item['bar']}` {item['pct']}")

            st.divider()

            # ── 步骤详情 ──
            st.write("**step details:**")
            detail_tabs = st.tabs([f"step {t['step_order']}: {t['step_name'][:30]}"
                                   for t in traces])

            for tab, t in zip(detail_tabs, traces):
                with tab:
                    if t["status"] == "error":
                        st.error(f"error: {t.get('error_msg', 'unknown')}")
                        if t.get("error_traceback"):
                            with st.expander("traceback"):
                                st.code(t["error_traceback"], language="python")

                    detail_col1, detail_col2 = st.columns(2)
                    with detail_col1:
                        st.write("**input:**")
                        st.code(t.get("input_data", "-")[:500] or "-",
                                language="json")
                    with detail_col2:
                        st.write("**output:**")
                        st.code(t.get("output_data", "-")[:500] or "-",
                                language="json")

                    st.caption(
                        f"duration: {t['duration_ms']}ms | "
                        f"tokens: {t.get('tokens_used', 0)} | "
                        f"time: {t.get('created_at', '-')}"
                    )

            # ── 耗时排行 ──
            st.write("**slowest steps:**")
            sorted_traces = sorted(traces, key=lambda x: x["duration_ms"] or 0, reverse=True)
            for t in sorted_traces[:5]:
                icon = "x" if t["status"] == "error" else "ok"
                st.write(
                    f"- {icon} {t['step_name']}: **{t['duration_ms']}ms**"
                    f"{' (error: ' + t.get('error_msg', '')[:60] + ')' if t['status'] == 'error' else ''}"
                )

            # ── 操作按钮 ──
            btn_col1, btn_col2 = st.columns(2)
            if btn_col1.button("export JSON", key=f"json_{sid}"):
                path = export_session(sid, "json")
                st.success(f"exported to {path}")
            if btn_col2.button("export CSV", key=f"csv_{sid}"):
                path = export_session(sid, "csv")
                st.success(f"exported to {path}")

# ═══ 搜索视图 ═══
elif view_mode == "search":
    keyword = st.text_input("search keyword", placeholder="search by step name, input, output, or error...")
    if keyword:
        results = search_traces(keyword, limit=100)
        st.subheader(f"results ({len(results)})")
        if not results:
            st.info("no results found")
        for r in results:
            icon = "x" if r["status"] == "error" else "ok"
            with st.expander(
                f"{icon} [{r.get('task_name', '-')}] {r['step_name']} — {r['duration_ms']}ms"
            ):
                st.write(f"**session:** {r['session_id']}")
                st.write(f"**type:** {r.get('step_type', 'function')}")
                if r.get("input_data"):
                    st.text(f"input: {r['input_data'][:200]}")
                if r.get("output_data"):
                    st.text(f"output: {r['output_data'][:200]}")
                if r.get("error_msg"):
                    st.error(r["error_msg"])

# ═══ 导出视图 ═══
elif view_mode == "export_data":
    st.subheader("export all data")
    if st.button("export all as JSON"):
        from tracer import export_all
        path = export_all("json")
        st.success(f"exported to {path}")
        with open(path, "r", encoding="utf-8") as f:
            st.download_button(
                "download JSON", f.read(),
                file_name=f"agent-traces-{pd.Timestamp.now().strftime('%Y%m%d-%H%M%S')}.json",
                mime="application/json"
            )

    if st.button("clear all data", type="secondary"):
        st.warning("this will delete all trace data!")
        if st.button("confirm delete", type="primary"):
            from tracer import clear_data
            clear_data()
            st.success("all data cleared. refresh to see changes.")
            st.rerun()

st.divider()
st.caption(
    "tip: run `py demo.py` to generate test data, then explore here. "
    "integrate with your agent using `from tracer import tracer`"
)
