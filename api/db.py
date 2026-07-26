
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "eco_loop.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    sim_time_hours REAL NOT NULL,
    outdoor_air_temp_c REAL NOT NULL,
    
    baseline_kw REAL NOT NULL,
    baseline_temp_c REAL NOT NULL,
    baseline_pmv REAL NOT NULL,
    
    ai_kw REAL NOT NULL,
    ai_temp_c REAL NOT NULL,
    ai_pmv REAL NOT NULL,
    
    mode TEXT NOT NULL,
    rationale TEXT NOT NULL,
    degraded INTEGER NOT NULL,
    zones_json TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    mcp_calls_json TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")

    cursor = conn.execute("PRAGMA table_info(ticks)")
    cols = {row[1] for row in cursor.fetchall()}
    if cols and ("baseline_kw" not in cols or "mcp_calls_json" not in cols):
        conn.execute("DROP TABLE IF EXISTS ticks")

    conn.execute(SCHEMA)
    conn.commit()
    return conn


def reset_database(conn: sqlite3.Connection) -> None:
    
    conn.execute("DROP TABLE IF EXISTS ticks")
    conn.execute(SCHEMA)
    conn.commit()


def insert_tick(conn: sqlite3.Connection, run_id: str, tick: dict) -> None:
    conn.execute(
        """INSERT INTO ticks (
            run_id, sim_time_hours, outdoor_air_temp_c,
            baseline_kw, baseline_temp_c, baseline_pmv,
            ai_kw, ai_temp_c, ai_pmv,
            mode, rationale, degraded, zones_json, actions_json, mcp_calls_json
           )
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            tick.get("sim_time_hours", 0.0),
            tick.get("outdoor_air_temp_c", 0.0),
            tick.get("baseline_kw", tick.get("facility_electricity_kw", 0.0)),
            tick.get("baseline_temp_c", tick.get("baseline_temp", 22.0)),
            tick.get("baseline_pmv", 0.0),
            tick.get("ai_kw", tick.get("facility_electricity_kw", 0.0)),
            tick.get("ai_temp_c", tick.get("ai_temp", 22.0)),
            tick.get("ai_pmv", 0.0),
            tick.get("mode", "ai"),
            tick.get("rationale", ""),
            int(tick.get("degraded", False)),
            json.dumps(tick.get("zones", [])),
            json.dumps(tick.get("actions", [])),
            json.dumps(tick.get("mcp_calls", [])),
        ),
    )
    conn.commit()


def fetch_recent(conn: sqlite3.Connection, run_id: str | None = None, limit: int = 100) -> list[dict]:
    base_query = """SELECT sim_time_hours, outdoor_air_temp_c,
                      baseline_kw, baseline_temp_c, baseline_pmv,
                      ai_kw, ai_temp_c, ai_pmv,
                      mode, rationale, degraded, zones_json, actions_json, mcp_calls_json
               FROM ticks"""
    if run_id is not None:
        query = base_query + " WHERE run_id = ? ORDER BY id DESC LIMIT ?"
        rows = conn.execute(query, (run_id, limit)).fetchall()
    else:
        query = base_query + " ORDER BY id DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()

    result = []
    for r in rows:
        zones = json.loads(r[11]) if r[11] else []
        actions = json.loads(r[12]) if r[12] else []
        mcp_calls = json.loads(r[13]) if r[13] else []

        result.append({
            "sim_time_hours": r[0],
            "outdoor_air_temp_c": r[1],
            "baseline_kw": r[2],
            "baseline_temp_c": r[3],
            "baseline_pmv": r[4],
            "ai_kw": r[5],
            "ai_temp_c": r[6],
            "ai_pmv": r[7],
            "facility_electricity_kw": r[5],
            "mode": r[8],
            "rationale": r[9],
            "degraded": bool(r[10]),
            "zones": zones,
            "actions": actions,
            "mcp_calls": mcp_calls,
        })

    return result


def fetch_summary(conn: sqlite3.Connection, run_id: str | None = None) -> dict:
    if run_id is not None:
        rows = conn.execute(
            "SELECT sim_time_hours, baseline_kw, ai_kw FROM ticks WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sim_time_hours, baseline_kw, ai_kw FROM ticks ORDER BY id"
        ).fetchall()

    if not rows:
        return {
            "tick_count": 0,
            "total_electricity_kwh": 0.0,
            "baseline_kwh": 0.0,
            "ai_kwh": 0.0,
            "savings_kwh": 0.0,
            "savings_pct": 0.0,
            "carbon_offset_kg": 0.0,
        }

    default_dt = 0.25  
    baseline_kwh = 0.0
    ai_kwh = 0.0
    prev_sim_time = None
    for sim_time, baseline_kw, ai_kw in rows:
        dt = (sim_time - prev_sim_time) if prev_sim_time is not None and sim_time > prev_sim_time else default_dt
        baseline_kwh += baseline_kw * dt
        ai_kwh += ai_kw * dt
        prev_sim_time = sim_time

    
    savings_kwh = baseline_kwh - ai_kwh
    savings_pct = (savings_kwh / baseline_kwh * 100.0) if baseline_kwh > 0 else 0.0
    carbon_offset_kg = savings_kwh * 0.385

    return {
        "tick_count": len(rows),
        "total_electricity_kwh": ai_kwh,
        "baseline_kwh": round(baseline_kwh, 2),
        "ai_kwh": round(ai_kwh, 2),
        "savings_kwh": round(savings_kwh, 2),
        "savings_pct": round(savings_pct, 1),
        "carbon_offset_kg": round(carbon_offset_kg, 2),
    }
