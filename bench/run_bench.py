#!/usr/bin/env python3
"""
ベンチマーク実行ランナー
========================
各シナリオを EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) で実行し、
  - 実行時間（複数回の中央値）
  - 実行計画のトップノード（Seq Scan か Index Scan か = 計画フリップ判定）
  - 読んだバッファ数
を JSON で出力する。PostgreSQL 17 / 18 双方に同じSQLを投げる。

体感ラベル: <100ms=一瞬 / 0.1-1s=わずかな待ち / 1-10s=待たされる / >10s=固まる
"""
import argparse
import json
import statistics
import sys
import time

import psycopg

SCENARIOS = {
    # ① 大規模集計（非同期I/O）: インデックスを使わない全表集計
    "s1_aggregate": """
        SELECT date_trunc('month', occurred_at) AS m,
               region,
               sum(amount)  AS revenue,
               count(*)     AS cnt
        FROM events
        WHERE is_billable
        GROUP BY 1, 2
        ORDER BY 1, 2
    """,
    # ② スキップスキャン: 複合索引(event_type, occurred_at)の先頭列を省いて occurred_at だけで絞る
    "s2_skipscan": """
        SELECT count(*), sum(amount)
        FROM events
        WHERE occurred_at >= timestamptz '2025-06-01'
          AND occurred_at <  timestamptz '2025-06-08'
    """,
    # ④ 深いリレーション + 多カラムのJOIN集計
    "s4_deepjoin": """
        SELECT o.plan, p.status, count(*) AS cnt, sum(e.amount) AS revenue
        FROM events e
        JOIN projects p      ON p.id = e.project_id
        JOIN organizations o ON o.id = p.org_id
        JOIN users u         ON u.id = p.owner_id
        WHERE e.is_billable
          AND e.occurred_at >= timestamptz '2025-01-01'
        GROUP BY o.plan, p.status
        ORDER BY revenue DESC
    """,
    # カウンターウェイト: 認証の点ルックアップ（メールで1人引く）
    "auth_lookup": """
        SELECT id, org_id, full_name, role
        FROM users
        WHERE email = %(email)s
    """,
    # ペルソナC: あいまい検索（部分一致）
    "cms_fuzzy": """
        SELECT id, title
        FROM articles
        WHERE title ILIKE %(kw)s
        LIMIT 50
    """,
}


def server_info(conn):
    v = conn.execute("SHOW server_version").fetchone()[0]
    try:
        io = conn.execute("SHOW io_method").fetchone()[0]
    except Exception:
        io = "n/a (PG17)"
    sb = conn.execute("SHOW shared_buffers").fetchone()[0]
    return {"server_version": v, "io_method": io, "shared_buffers": sb}


def explain_once(conn, sql, params):
    q = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql
    row = conn.execute(q, params).fetchone()[0]
    plan = row[0]["Plan"]
    return row[0]["Execution Time"], plan


def summarize_plan(plan):
    """トップから主要ノード型を集めて Seq/Index を判定"""
    nodes = []
    def walk(p):
        nodes.append(p.get("Node Type", "?"))
        for c in p.get("Plans", []):
            walk(c)
    walk(plan)
    uses_seq = any("Seq Scan" in n for n in nodes)
    uses_idx = any("Index" in n for n in nodes)
    top = plan.get("Node Type", "?")
    return {"top_node": top, "node_types": nodes,
            "uses_seq_scan": uses_seq, "uses_index": uses_idx}


def label(ms):
    if ms < 100:   return "一瞬"
    if ms < 1000:  return "わずかな待ち"
    if ms < 10000: return "待たされる"
    return "固まる"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--scenario", required=True, choices=list(SCENARIOS) + ["all"])
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--tag", default="")   # pg17 / pg18-worker / pg18-sync 等
    args = ap.parse_args()

    targets = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    out = []
    with psycopg.connect(args.dsn, autocommit=True) as conn:
        info = server_info(conn)
        print(f"[info] {info}", file=sys.stderr)
        for name in targets:
            sql = SCENARIOS[name]
            params = {}
            if name == "auth_lookup":
                params = {"email": "user777777@example.com"}
                # 実在しうるメールに合わせる（存在しなくても索引探索コストは測れる）
            if name == "cms_fuzzy":
                params = {"kw": "%管理%"}
            times, plan = [], None
            try:
                for _ in range(args.runs):
                    t, plan = explain_once(conn, sql, params)
                    times.append(t)
            except Exception as e:
                print(f"[skip] {name}: {e}", file=sys.stderr)
                continue
            med = statistics.median(times)
            rec = {"scenario": name, "tag": args.tag, **info,
                   "median_ms": round(med, 2), "label": label(med),
                   "runs": times, "plan": summarize_plan(plan)}
            out.append(rec)
            print(f"[{name}] {args.tag}: median={med:.1f}ms ({label(med)}) "
                  f"top={rec['plan']['top_node']} seq={rec['plan']['uses_seq_scan']}",
                  file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
