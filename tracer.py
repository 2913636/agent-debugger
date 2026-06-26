"""
Agent Trace 追踪器
===================
轻量级 @trace 装饰器，记录每一步的输入/输出/耗时。
类似 @traceable，但数据存本地 SQLite，可导出分析。
"""

import time
import sqlite3
import json
import functools
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "traces.db"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            step_order INTEGER,
            input_data TEXT,
            output_data TEXT,
            duration_ms INTEGER,
            status TEXT DEFAULT 'success',
            error_msg TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            task_name TEXT,
            agent_name TEXT,
            total_steps INTEGER DEFAULT 0,
            total_duration_ms INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            created_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT
        )
    """)
    conn.commit()
    return conn


def trace(step_name: str, session_id: str = "default"):
    """
    装饰器：记录函数调用的输入/输出/耗时。

    用法：
        @trace("搜索特斯拉", session_id="debug-001")
        def search(query):
            return "搜索结果..."
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            conn = _get_db()
            start = time.time()

            # 记录输入
            input_data = json.dumps({"args": str(args)[:200], "kwargs": str(kwargs)[:200]},
                                    ensure_ascii=False)

            # 确保 session 存在
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, task_name) VALUES (?, ?)",
                (session_id, step_name)
            )

            # 获取当前步骤序号
            cur = conn.execute(
                "SELECT COUNT(*) FROM traces WHERE session_id = ?", (session_id,)
            )
            order = cur.fetchone()[0] + 1

            try:
                result = func(*args, **kwargs)
                elapsed = int((time.time() - start) * 1000)
                output_data = json.dumps({"result": str(result)[:500]}, ensure_ascii=False)

                conn.execute(
                    """INSERT INTO traces (session_id, step_name, step_order, input_data,
                       output_data, duration_ms, status) VALUES (?,?,?,?,?,?,?)""",
                    (session_id, step_name, order, input_data, output_data, elapsed, "success")
                )
                conn.commit()
                conn.close()
                return result

            except Exception as e:
                elapsed = int((time.time() - start) * 1000)
                conn.execute(
                    """INSERT INTO traces (session_id, step_name, step_order, input_data,
                       duration_ms, status, error_msg) VALUES (?,?,?,?,?,?,?)""",
                    (session_id, step_name, order, input_data, elapsed, "error", str(e))
                )
                conn.commit()
                conn.close()
                raise

        return wrapper
    return decorator


def start_session(session_id: str, task_name: str, agent_name: str = ""):
    """开始一个追踪会话"""
    conn = _get_db()
    conn.execute(
        """INSERT OR REPLACE INTO sessions (session_id, task_name, agent_name, status, created_at)
           VALUES (?, ?, ?, 'running', datetime('now'))""",
        (session_id, task_name, agent_name)
    )
    conn.commit()
    conn.close()


def end_session(session_id: str, status: str = "completed"):
    """结束追踪会话"""
    conn = _get_db()
    cur = conn.execute(
        "SELECT COUNT(*) as steps, SUM(duration_ms) as total FROM traces WHERE session_id = ?",
        (session_id,)
    )
    row = cur.fetchone()
    conn.execute(
        "UPDATE sessions SET total_steps=?, total_duration_ms=?, status=?, ended_at=datetime('now') WHERE session_id=?",
        (row[0] or 0, row[1] or 0, status, session_id)
    )
    conn.commit()
    conn.close()


def get_sessions(limit: int = 20) -> list:
    """获取所有会话列表"""
    conn = _get_db()
    cur = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows


def get_traces(session_id: str) -> list:
    """获取指定会话的所有步骤"""
    conn = _get_db()
    cur = conn.execute(
        "SELECT * FROM traces WHERE session_id=? ORDER BY step_order", (session_id,)
    )
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows


def get_summary():
    """获取总览统计"""
    conn = _get_db()
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    total_traces = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    errors = conn.execute("SELECT COUNT(*) FROM traces WHERE status='error'").fetchone()[0]
    total_time = conn.execute("SELECT SUM(duration_ms) FROM traces").fetchone()[0] or 0
    conn.close()
    return {
        "total_sessions": total_sessions,
        "total_steps": total_traces,
        "errors": errors,
        "total_time_ms": total_time,
        "error_rate": f"{errors/max(total_traces,1)*100:.1f}%"
    }
