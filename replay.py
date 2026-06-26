"""
Agent 执行回放器
================
像 Chrome DevTools 的 "Replay" 一样，逐步重现 Agent 的执行过程。

功能：
  - 选择会话 → 逐步回放每一步
  - 展示每步的输入/输出/耗时/状态
  - 支持「自动播放」和「手动步进」两种模式
  - 高亮错误步骤
  - 对比两个会话的差异

用法：
    py replay.py                    # 交互式回放
    py replay.py <session_id>       # 回放指定会话
"""

import time as _time
import sys
from tracer import get_sessions, get_traces, get_summary


def print_header(text: str, width: int = 60):
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}")


def print_step(trace: dict, index: int, total: int):
    """打印一个步骤的详细信息"""
    status_icon = "[FAIL]" if trace["status"] == "error" else "[ OK ]"
    step_name = trace["step_name"]
    step_type = trace.get("step_type", "function")
    duration = trace["duration_ms"]
    tokens = trace.get("tokens_used", 0)

    # 耗时可视化条
    bar_len = min(30, max(1, duration // 20))
    bar = "=" * bar_len

    print(f"\n  {status_icon} Step {index}/{total}: {step_name} [{step_type}]")
    print(f"  {' ' * 6} time: {duration}ms {bar}")
    if tokens:
        print(f"  {' ' * 6} tokens: {tokens}")

    # 输入
    input_data = trace.get("input_data", "")
    if input_data and input_data.strip():
        print(f"  {' ' * 6} input: {input_data[:200]}")
        if len(input_data) > 200:
            print(f"  {' ' * 6}        (... {len(input_data) - 200} more chars)")

    # 输出
    output_data = trace.get("output_data", "")
    if output_data and output_data.strip():
        print(f"  {' ' * 6} output: {output_data[:200]}")
        if len(output_data) > 200:
            print(f"  {' ' * 6}         (... {len(output_data) - 200} more chars)")

    # 错误
    if trace["status"] == "error":
        error_msg = trace.get("error_msg", "unknown error")
        print(f"  {' ' * 6} [!] ERROR: {error_msg}")
        traceback = trace.get("error_traceback", "")
        if traceback:
            print(f"  {' ' * 6} traceback:")
            for line in traceback.split("\n")[:5]:
                print(f"  {' ' * 8} {line}")


def replay_session(session_id: str, auto_play: bool = False, interval: float = 0.5):
    """
    回放一个会话的所有步骤。

    Args:
        session_id: 会话 ID
        auto_play: True=自动播放，False=手动步进（按 Enter）
        interval: 自动播放时每步间隔秒数
    """
    traces = get_traces(session_id)
    if not traces:
        print(f"\n  no traces found for session: {session_id}")
        return

    session = None
    for s in get_sessions(limit=999):
        if s["session_id"] == session_id:
            session = s
            break

    total = len(traces)
    errors = sum(1 for t in traces if t["status"] == "error")
    total_time = sum(t["duration_ms"] or 0 for t in traces)
    total_tokens = sum(t.get("tokens_used", 0) or 0 for t in traces)

    print_header(f"REPLAY: {session['task_name'] if session else session_id}")
    print(f"  steps: {total} | errors: {errors} | total time: {total_time}ms | tokens: {total_tokens}")
    print(f"  mode: {'auto-play (' + str(interval) + 's)' if auto_play else 'step-by-step (press Enter)'}")

    if auto_play:
        print(f"\n  starting auto-play...")
        _time.sleep(1)

    for i, trace in enumerate(traces, 1):
        print_step(trace, i, total)

        if auto_play:
            _time.sleep(interval)
        else:
            action = input(f"\n  [{i}/{total}] press Enter to continue, 'q' to quit, 'f' to fast-forward: ").strip().lower()
            if action == 'q':
                print("\n  replay stopped.")
                break
            elif action == 'f':
                auto_play = True
                interval = 0.1
                print("  fast-forward mode on")

    print_header("REPLAY COMPLETE")
    print(f"  {total} steps replayed, {errors} errors found")


def compare_sessions(session_id_1: str, session_id_2: str):
    """
    对比两个会话的执行差异。

    比较维度：
      - 总步骤数
      - 总耗时
      - 每步耗时对比
      - 错误率
    """
    traces1 = get_traces(session_id_1)
    traces2 = get_traces(session_id_2)

    s1 = None
    s2 = None
    for s in get_sessions(limit=999):
        if s["session_id"] == session_id_1:
            s1 = s
        if s["session_id"] == session_id_2:
            s2 = s

    print_header("SESSION COMPARISON")
    print(f"  Session A: {s1['task_name'] if s1 else session_id_1}")
    print(f"  Session B: {s2['task_name'] if s2 else session_id_2}")
    print()

    # 基本指标对比
    print(f"  {'Metric':<25} {'Session A':>15} {'Session B':>15} {'Diff':>15}")
    print(f"  {'-'*70}")
    print(f"  {'steps':<25} {len(traces1):>15} {len(traces2):>15} {len(traces2)-len(traces1):>+15}")
    time1 = sum(t["duration_ms"] or 0 for t in traces1)
    time2 = sum(t["duration_ms"] or 0 for t in traces2)
    print(f"  {'total time (ms)':<25} {time1:>15} {time2:>15} {time2-time1:>+15}")
    err1 = sum(1 for t in traces1 if t["status"] == "error")
    err2 = sum(1 for t in traces2 if t["status"] == "error")
    print(f"  {'errors':<25} {err1:>15} {err2:>15} {err2-err1:>+15}")
    tok1 = sum(t.get("tokens_used", 0) or 0 for t in traces1)
    tok2 = sum(t.get("tokens_used", 0) or 0 for t in traces2)
    print(f"  {'tokens':<25} {tok1:>15} {tok2:>15} {tok2-tok1:>+15}")

    # 步骤级别对比 (按同名步骤匹配)
    print(f"\n  step-level comparison:")
    names1 = {t["step_name"]: t for t in traces1}
    names2 = {t["step_name"]: t for t in traces2}
    all_names = sorted(set(list(names1.keys()) + list(names2.keys())))

    print(f"  {'step':<25} {'A (ms)':>10} {'B (ms)':>10} {'diff':>10}")
    print(f"  {'-'*55}")
    for name in all_names:
        dur1 = names1[name]["duration_ms"] if name in names1 else None
        dur2 = names2[name]["duration_ms"] if name in names2 else None
        if dur1 and dur2:
            diff = dur2 - dur1
            flag = " [!]" if abs(diff) > 100 else ""
            print(f"  {name:<25} {dur1:>10} {dur2:>10} {diff:>+10}{flag}")
        elif dur1:
            print(f"  {name:<25} {dur1:>10} {'-':>10} {'only A':>10}")
        else:
            print(f"  {name:<25} {'-':>10} {dur2:>10} {'only B':>10}")


def list_and_pick():
    """列出所有会话，让用户选择一个来回放"""
    sessions = get_sessions(limit=50)
    if not sessions:
        print("\n  no sessions found. run 'py demo.py' first to generate test data.")
        return

    print_header("AVAILABLE SESSIONS")
    for i, s in enumerate(sessions, 1):
        status = {"completed": "ok", "running": "..", "failed": "!!"}.get(s["status"], "??")
        print(f"  [{i}] {status} {s['task_name']:<30} {s['total_steps']} steps | {s['total_duration_ms']}ms | {s.get('created_at', '-')}")

    print(f"\n  commands: [1-{len(sessions)}] replay session | 'c' compare two | 'q' quit")
    choice = input("  > ").strip().lower()

    if choice == 'q':
        return
    elif choice == 'c':
        print("\n  select two sessions to compare:")
        a = input("  session A (#): ").strip()
        b = input("  session B (#): ").strip()
        try:
            compare_sessions(sessions[int(a) - 1]["session_id"],
                             sessions[int(b) - 1]["session_id"])
        except (ValueError, IndexError):
            print("  invalid selection")
        return
    else:
        try:
            idx = int(choice) - 1
            sid = sessions[idx]["session_id"]
            mode = input("  auto-play? [y/N]: ").strip().lower()
            replay_session(sid, auto_play=(mode == 'y'))
        except (ValueError, IndexError):
            print("  invalid selection")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 命令行直接指定 session_id
        sid = sys.argv[1]
        auto = "--auto" in sys.argv
        replay_session(sid, auto_play=auto)
    else:
        # 交互式选择
        print_header("AGENT REPLAY VIEWER")
        print(f"  sessions: {get_summary()['total_sessions']}")
        list_and_pick()
