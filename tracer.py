"""
Agent Trace 追踪器
==================
轻量级 @trace 装饰器 + 上下文管理器，记录每一步的输入/输出/耗时。
类似 @traceable，但数据存本地 SQLite，可导出分析、可回放。

用法：
    # 装饰器模式
    @trace("search", session_id="debug-001")
    def search(query): ...

    # 上下文管理器模式
    with tracer.span("llm_call", session_id="debug-001") as step:
        result = call_llm(prompt)
        step.output_data = result
        step.tokens = 1500
"""

import time
import sqlite3
import json
import functools
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Callable

DB_PATH = Path(__file__).parent / "traces.db"

_local = threading.local()


def _get_db() -> sqlite3.Connection:
    """获取线程安全的数据库连接"""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init():
    """初始化数据库表（首次使用时自动调用）"""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            task_name TEXT NOT NULL,
            agent_name TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            total_steps INTEGER DEFAULT 0,
            total_duration_ms INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT
        );
        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            step_type TEXT DEFAULT 'function',
            step_order INTEGER,
            input_data TEXT DEFAULT '',
            output_data TEXT DEFAULT '',
            duration_ms INTEGER DEFAULT 0,
            tokens_used INTEGER DEFAULT 0,
            status TEXT DEFAULT 'success',
            error_msg TEXT DEFAULT '',
            error_traceback TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_traces_session ON traces(session_id);
        CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status);
    """)
    conn.commit()


# ============================================================
# Span: 一个追踪单元
# ============================================================

class Span:
    """一个追踪 Span —— 在 with 块内可修改属性"""
    def __init__(self, session_id: str, step_name: str, step_type: str = "function"):
        self.session_id = session_id
        self.step_name = step_name
        self.step_type = step_type
        self.input_data: str = ""
        self.output_data: str = ""
        self.tokens: int = 0
        self.metadata: dict = {}
        self.error_msg: str = ""
        self.error_traceback: str = ""
        self.status: str = "success"
        self._start: float = 0.0
        self._end: float = 0.0

    @property
    def duration_ms(self) -> int:
        return int((self._end - self._start) * 1000) if self._end else 0


# ============================================================
# TracerInstance: 上下文管理器 + 数据库操作
# ============================================================

class TracerInstance:
    """线程安全的追踪器实例"""

    def __init__(self):
        init()

    @contextmanager
    def span(self, step_name: str, session_id: str = "default",
             step_type: str = "function", **meta):
        """
        上下文管理器：追踪一个代码块的执行。

        Yields:
            Span 对象，可在 with 块内设置 .output_data, .tokens 等

        Example:
            with tracer.span("call_deepseek", session_id, "llm_call") as sp:
                sp.input_data = prompt[:200]
                result = client.chat(prompt)
                sp.output_data = result[:500]
                sp.tokens = 1500
        """
        sp = Span(session_id, step_name, step_type)
        sp.metadata = meta
        sp._start = time.perf_counter()

        # 确保 session 存在
        self._ensure_session(session_id, step_name)

        # 计算步骤序号
        conn = _get_db()
        cur = conn.execute(
            "SELECT COUNT(*) FROM traces WHERE session_id = ?", (session_id,)
        )
        order = cur.fetchone()[0] + 1

        try:
            yield sp
            sp._end = time.perf_counter()
            sp.status = "success"
        except Exception as e:
            sp._end = time.perf_counter()
            sp.status = "error"
            import traceback
            sp.error_msg = str(e)[:500]
            sp.error_traceback = traceback.format_exc()[:2000]
            raise
        finally:
            # 写入数据库
            self._insert_trace(sp, order)
            self._update_session_stats(session_id)

    def _ensure_session(self, session_id: str, task_name: str):
        conn = _get_db()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, task_name) VALUES (?, ?)",
            (session_id, task_name)
        )
        conn.commit()

    def _insert_trace(self, sp: Span, order: int):
        conn = _get_db()
        conn.execute(
            """INSERT INTO traces (session_id, step_name, step_type, step_order,
               input_data, output_data, duration_ms, tokens_used, status,
               error_msg, error_traceback, metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sp.session_id, sp.step_name, sp.step_type, order,
             sp.input_data[:1000], sp.output_data[:2000],
             sp.duration_ms, sp.tokens, sp.status,
             sp.error_msg, sp.error_traceback,
             json.dumps(sp.metadata, ensure_ascii=False))
        )
        conn.commit()

    def _update_session_stats(self, session_id: str):
        conn = _get_db()
        cur = conn.execute(
            """SELECT COUNT(*) as steps, SUM(duration_ms) as total_ms,
               SUM(tokens_used) as total_tokens,
               SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors
               FROM traces WHERE session_id = ?""",
            (session_id,)
        )
        row = cur.fetchone()
        conn.execute(
            """UPDATE sessions SET total_steps=?, total_duration_ms=?,
               total_tokens=?, error_count=?
               WHERE session_id=?""",
            (row["steps"] or 0, row["total_ms"] or 0,
             row["total_tokens"] or 0, row["errors"] or 0, session_id)
        )
        conn.commit()


# 全局单例
tracer = TracerInstance()


# ============================================================
# @trace 装饰器
# ============================================================

def trace(step_name: str, session_id: str = "default",
          step_type: str = "function"):
    """
    装饰器：自动追踪函数调用的输入/输出/耗时。

    Example:
        @trace("search", session_id="debug-001")
        def search(query: str) -> dict: ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.span(step_name, session_id, step_type) as sp:
                sp.input_data = json.dumps(
                    {"args": str(args)[:300], "kwargs": str(kwargs)[:300]},
                    ensure_ascii=False
                )
                result = func(*args, **kwargs)
                sp.output_data = json.dumps(
                    {"result": str(result)[:800]},
                    ensure_ascii=False
                )
                return result
        return wrapper
    return decorator


# ============================================================
# 会话管理
# ============================================================

def start_session(session_id: str, task_name: str, agent_name: str = "",
                  tags: str = "", metadata: dict = None):
    """开始一个追踪会话"""
    conn = _get_db()
    conn.execute(
        """INSERT OR REPLACE INTO sessions
           (session_id, task_name, agent_name, tags, status,
            created_at, metadata_json)
           VALUES (?, ?, ?, ?, 'running', datetime('now'), ?)""",
        (session_id, task_name, agent_name, tags,
         json.dumps(metadata or {}, ensure_ascii=False))
    )
    conn.commit()


def end_session(session_id: str, status: str = "completed"):
    """结束追踪会话"""
    conn = _get_db()
    conn.execute(
        "UPDATE sessions SET status=?, ended_at=datetime('now') WHERE session_id=?",
        (status, session_id)
    )
    conn.commit()


# ============================================================
# 查询 API
# ============================================================

def get_sessions(limit: int = 50, status: str = "") -> list[dict]:
    """获取会话列表，可按状态筛选"""
    conn = _get_db()
    query = "SELECT * FROM sessions"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cur = conn.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    return rows


def get_traces(session_id: str, status: str = "") -> list[dict]:
    """获取指定会话的所有步骤"""
    conn = _get_db()
    query = "SELECT * FROM traces WHERE session_id = ?"
    params = [session_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY step_order ASC"

    cur = conn.execute(query, params)
    return [dict(r) for r in cur.fetchall()]


def get_summary() -> dict:
    """获取全局统计"""
    conn = _get_db()
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    total_traces = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    errors = conn.execute(
        "SELECT COUNT(*) FROM traces WHERE status='error'"
    ).fetchone()[0]
    total_time = conn.execute(
        "SELECT SUM(duration_ms) FROM traces"
    ).fetchone()[0] or 0
    total_tokens = conn.execute(
        "SELECT SUM(tokens_used) FROM traces"
    ).fetchone()[0] or 0
    return {
        "total_sessions": total_sessions,
        "total_steps": total_traces,
        "errors": errors,
        "total_time_ms": total_time,
        "total_tokens": total_tokens,
        "error_rate": f"{errors / max(total_traces, 1) * 100:.1f}%",
    }


def search_traces(keyword: str, limit: int = 50) -> list[dict]:
    """按关键词搜索追踪步骤"""
    conn = _get_db()
    cur = conn.execute(
        """SELECT t.*, s.task_name FROM traces t
           LEFT JOIN sessions s ON t.session_id = s.session_id
           WHERE t.step_name LIKE ? OR t.input_data LIKE ?
           OR t.output_data LIKE ? OR t.error_msg LIKE ?
           ORDER BY t.created_at DESC LIMIT ?""",
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit)
    )
    return [dict(r) for r in cur.fetchall()]


# ============================================================
# 导出
# ============================================================

def export_session(session_id: str, fmt: str = "json") -> str:
    """
    导出会话数据。
    Args:
        session_id: 会话 ID
        fmt: "json" 或 "csv"
    Returns:
        导出文件路径
    """
    conn = _get_db()
    session = dict(conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone())
    traces = get_traces(session_id)
    data = {"session": session, "traces": traces}

    out_dir = Path(__file__).parent / "exports"
    out_dir.mkdir(exist_ok=True)

    if fmt == "json":
        path = out_dir / f"{session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    else:
        import csv
        path = out_dir / f"{session_id}.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            if traces:
                writer = csv.DictWriter(f, fieldnames=traces[0].keys())
                writer.writeheader()
                writer.writerows(traces)

    return str(path)


def export_all(fmt: str = "json") -> str:
    """导出所有会话数据"""
    out_dir = Path(__file__).parent / "exports"
    out_dir.mkdir(exist_ok=True)

    conn = _get_db()
    sessions = [dict(r) for r in
                conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()]
    all_data = []
    for s in sessions:
        traces = get_traces(s["session_id"])
        all_data.append({"session": s, "traces": traces})

    path = out_dir / f"all_sessions_{int(time.time())}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2, default=str)
    return str(path)


def clear_data():
    """清空所有追踪数据（危险操作）"""
    conn = _get_db()
    conn.execute("DELETE FROM traces")
    conn.execute("DELETE FROM sessions")
    conn.commit()
