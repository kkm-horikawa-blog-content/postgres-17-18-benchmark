#!/usr/bin/env python3
"""
詳細プローブ: s1_aggregate（遅くなった集計）を中心に、
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON) から
  - 実行時間（中央値）
  - I/O Read Time（ページ読み取りに費やした時間 = 実I/O待ち）
  - shared hit / read ブロック数
  - 並列ワーカー数（起動数）
  - トップ/スキャンノード
を抜き出して1行サマリで出す。--set で任意GUCをセッション適用。
"""
import argparse, json, statistics, sys
import psycopg

QUERIES = {
    "s1_aggregate": """
        SELECT date_trunc('month', occurred_at) AS m, region,
               sum(amount) AS revenue, count(*) AS cnt
        FROM events WHERE is_billable
        GROUP BY 1,2 ORDER BY 1,2""",
    "s4_deepjoin": """
        SELECT o.plan, p.status, count(*) AS cnt, sum(e.amount) AS revenue
        FROM events e
        JOIN projects p      ON p.id = e.project_id
        JOIN organizations o ON o.id = p.org_id
        JOIN users u         ON u.id = p.owner_id
        WHERE e.is_billable AND e.occurred_at >= timestamptz '2025-01-01'
        GROUP BY o.plan, p.status ORDER BY revenue DESC""",
    "s2_skipscan": """
        SELECT count(*), sum(amount) FROM events
        WHERE occurred_at >= timestamptz '2025-06-01'
          AND occurred_at <  timestamptz '2025-06-08'""",
}

def walk(plan):
    yield plan
    for c in plan.get("Plans", []):
        yield from walk(c)

def agg_plan(plan):
    hit = read = rdtime = workers = 0
    scan = None
    for n in walk(plan):
        hit  += n.get("Shared Hit Blocks", 0)
        read += n.get("Shared Read Blocks", 0)
        rdtime += n.get("I/O Read Time", 0.0)
        if "Workers Launched" in n:
            workers = max(workers, n.get("Workers Launched", 0))
        nt = n.get("Node Type", "")
        if "Scan" in nt and scan is None:
            scan = nt
    return dict(shared_hit=hit, shared_read=read, io_read_ms=round(rdtime,1),
                workers=workers, scan=scan, top=plan.get("Node Type"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--query", default="s1_aggregate", choices=list(QUERIES))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--set", action="append", default=[], help='例: effective_io_concurrency=64')
    ap.add_argument("--tag", default="")
    ap.add_argument("--dump", default="")
    args = ap.parse_args()

    sql = QUERIES[args.query]
    with psycopg.connect(args.dsn, autocommit=True) as conn:
        ver = conn.execute("show server_version").fetchone()[0]
        try: io = conn.execute("show io_method").fetchone()[0]
        except Exception: io = "n/a"
        for s in args.set:
            k, v = s.split("=", 1)
            conn.execute("SELECT set_config(%s, %s, false)", (k.strip(), v.strip()))
        # 実効値を記録
        eff = {}
        for g in ("effective_io_concurrency","io_combine_limit",
                  "max_parallel_workers_per_gather","io_method","io_workers",
                  "shared_buffers"):
            try: eff[g] = conn.execute(f"show {g}").fetchone()[0]
            except Exception: pass
        times, last = [], None
        for _ in range(args.runs):
            row = conn.execute("EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON) "+sql).fetchone()[0]
            times.append(row[0]["Execution Time"]); last = row[0]
        med = statistics.median(times)
        a = agg_plan(last["Plan"])
        tag = args.tag or f"PG{ver.split('.')[0]}/{io}"
        print(f"{tag:28s} q={args.query:12s} med={med:8.1f}ms  "
              f"io_read={a['io_read_ms']:8.1f}ms  hit={a['shared_hit']:>8} read={a['shared_read']:>8}  "
              f"workers={a['workers']} scan={a['scan']} "
              f"[eic={eff.get('effective_io_concurrency')} iocl={eff.get('io_combine_limit')} "
              f"mpw={eff.get('max_parallel_workers_per_gather')} iow={eff.get('io_workers')}]")
        if args.dump:
            with open(args.dump, "w") as f:
                json.dump({"tag":tag,"ver":ver,"io_method":io,"eff":eff,
                           "median_ms":med,"runs":times,"agg":a,"plan":last}, f,
                          ensure_ascii=False, indent=2)
if __name__ == "__main__":
    main()
