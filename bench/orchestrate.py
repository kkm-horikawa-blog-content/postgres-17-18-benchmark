#!/usr/bin/env python3
"""
50M ベンチ一括オーケストレータ（コンテナ内・デタッチ実行用）
ディスク逼迫を避けるため 1 バージョンずつ完了させ、pg17 計測後に events を空ける。
進捗は /work/bigrun.log に逐次出力。最後に ALL_DONE を書く。
"""
import json, os, subprocess, sys, time
import psycopg

SCALE = 20_000_000
DSN = {
    "pg17": "postgresql://bench:bench@pg17:5432/bench",
    "pg18": "postgresql://bench:bench@pg18:5432/bench",
}
CORE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_events_type_time ON events (event_type, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_user    ON events (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_project ON events (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_projects_org   ON projects (org_id)",
    "CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects (owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_org      ON users (org_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_email    ON users (email)",
    "CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_articles_org   ON articles (org_id)",
]

def log(m):
    with open("/work/bigrun.log", "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout, p.stderr

def s2_explain(dsn):
    with psycopg.connect(dsn, autocommit=True) as cn:
        q = ("EXPLAIN (ANALYZE, BUFFERS) SELECT count(*),sum(amount) FROM events "
             "WHERE occurred_at >= timestamptz '2025-06-01' "
             "AND occurred_at < timestamptz '2025-06-08'")
        rows = cn.execute(q).fetchall()
        return "\n".join(r[0] for r in rows)

def main():
    open("/work/bigrun.log", "w").close()
    os.makedirs("/work/results", exist_ok=True)
    meta = {}
    for c in ("pg17", "pg18"):
        log(f"=== {c}: load core {SCALE:,} ===")
        out, err = run(["python", "loader/load.py", "--dsn", DSN[c],
                        "--tables", "core", "--scale", str(SCALE)])
        log(f"{c} core loaded; tail: " + err.strip().splitlines()[-1] if err.strip() else f"{c} core loaded")
        log(f"=== {c}: load cms 300000 ===")
        run(["python", "loader/load.py", "--dsn", DSN[c], "--tables", "cms", "--scale", "300000"])
        log(f"{c} cms loaded")
        log(f"=== {c}: build indexes ===")
        with psycopg.connect(DSN[c], autocommit=True) as cn:
            for ix in CORE_INDEXES:
                cn.execute(ix)
        log(f"{c} indexed")
        log(f"=== {c}: ANALYZE (timed) ===")
        t = time.time()
        with psycopg.connect(DSN[c], autocommit=True) as cn:
            cn.execute("ANALYZE")
        dt = time.time() - t
        meta[f"{c}_analyze_seconds"] = round(dt, 1)
        log(f"{c} ANALYZE took {dt:.1f}s")
        meta[f"{c}_s2_explain"] = s2_explain(DSN[c])
        log(f"=== {c}: bench ===")
        out, err = run(["python", "bench/run_bench.py", "--dsn", DSN[c],
                        "--scenario", "all", "--tag", c, "--runs", "5"])
        open(f"/work/results/{c}_{SCALE}.json", "w").write(out)
        log(f"{c} bench done:\n" + err.strip())
        # disk size of this version
        with psycopg.connect(DSN[c], autocommit=True) as cn:
            sz = cn.execute("select pg_size_pretty(pg_database_size('bench'))").fetchone()[0]
        meta[f"{c}_db_size"] = sz
        log(f"{c} db size {sz}")
        if c == "pg17":
            log("free disk: truncate pg17 core after capturing results")
            with psycopg.connect(DSN[c], autocommit=True) as cn:
                cn.execute("TRUNCATE events,projects,users,organizations RESTART IDENTITY CASCADE")
    open("/work/results/meta_50m.json", "w").write(json.dumps(meta, ensure_ascii=False, indent=2))
    log("ALL_DONE")

if __name__ == "__main__":
    main()
