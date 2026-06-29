#!/usr/bin/env python3
"""
Faker 種プール増幅ローダー
==========================
Faker は 1 件ずつ生成すると遅く、1 億行を素直に作ると日が暮れる。
そこで「リアルな種プール」（実在感のある名前・会社名・文章など数万〜数十万件）を
一度だけ Faker で生成し、それを組み合わせ・サンプリングして大量行へ増幅する。
これで「中身のリアルさ」と「億単位の規模」を両立する。

乱数シードを固定しているので、PostgreSQL 17 と 18 にまったく同じデータが入る。
（=バージョン差だけを測れる）

使い方:
    python load.py --dsn postgresql://bench:bench@localhost:5417/bench \
                   --tables core --scale 1000000
    python load.py --dsn ... --tables cms --scale 1000000
"""
import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg
from faker import Faker

# ----- 再現性のための固定シード（両バージョンで同一データになる） -----
SEED = 20260629
random.seed(SEED)
fake = Faker("ja_JP")
Faker.seed(SEED)

EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)
SPAN_SECONDS = int(timedelta(days=730).total_seconds())  # 約2年に分散

EVENT_TYPES = ["view", "click", "create", "update",
               "delete", "export", "comment", "login"]  # 8種=低カーディナリティ
REGIONS = ["JP-East", "JP-West", "US", "EU", "APAC", "LATAM"]
DEVICES = ["desktop", "mobile", "tablet"]
CHANNELS = ["web", "api", "mobile_app", "batch"]
PLANS = ["free", "pro", "enterprise"]
ROLES = ["admin", "member", "viewer"]


def build_pools(seed_size: int):
    """Faker で一度だけ生成する種プール"""
    t0 = time.time()
    print(f"[pool] 種プール生成中 (size={seed_size}) ...", file=sys.stderr)
    names = [fake.name() for _ in range(seed_size)]
    companies = [fake.company() for _ in range(max(seed_size // 20, 200))]
    domains = [fake.domain_name() for _ in range(max(seed_size // 50, 100))]
    # 記事タイトル・本文の素材（文章）
    sentences = [fake.text(max_nb_chars=200) for _ in range(max(seed_size // 10, 500))]
    words = [fake.word() for _ in range(2000)]
    print(f"[pool] 完了 ({time.time()-t0:.1f}s)", file=sys.stderr)
    return dict(names=names, companies=companies, domains=domains,
                sentences=sentences, words=words)


def ts(rng_int: int) -> datetime:
    return EPOCH + timedelta(seconds=rng_int % SPAN_SECONDS)


def copy_table(conn, table, columns, row_iter, total, label):
    """COPY で一括投入。進捗を出す。"""
    t0 = time.time()
    cols = ", ".join(columns)
    n = 0
    with conn.cursor().copy(f"COPY {table} ({cols}) FROM STDIN") as cp:
        for row in row_iter:
            cp.write_row(row)
            n += 1
            if n % 1_000_000 == 0:
                rate = n / (time.time() - t0)
                print(f"[{label}] {n:,}/{total:,} ({rate:,.0f} rows/s)", file=sys.stderr)
    conn.commit()
    print(f"[{label}] 完了 {n:,}行 ({time.time()-t0:.1f}s)", file=sys.stderr)


# ---------------------------------------------------------------- generators
def gen_orgs(n, pools):
    for i in range(1, n + 1):
        yield (i, random.choice(pools["companies"]),
               random.choice(PLANS), fake.country_code(),
               ts(random.randint(0, SPAN_SECONDS)))


def gen_users(n, n_org, pools):
    names = pools["names"]; domains = pools["domains"]
    for i in range(1, n + 1):
        nm = names[i % len(names)]
        # メールはユニークになるよう id を混ぜる（実在感は名前由来で担保）
        email = f"user{i}@{domains[i % len(domains)]}"
        yield (i, random.randint(1, n_org), email, nm,
               random.choice(ROLES), ts(random.randint(0, SPAN_SECONDS)))


def gen_projects(n, n_org, n_user, pools):
    words = pools["words"]
    for i in range(1, n + 1):
        name = f"{random.choice(words)}-{random.choice(words)}"
        yield (i, random.randint(1, n_org), random.randint(1, n_user),
               name, random.choice(["active", "archived"]),
               ts(random.randint(0, SPAN_SECONDS)))


def gen_events(n, n_org, n_user, n_proj):
    # 高速化のためローカル束縛
    ri = random.randint; rc = random.choice
    et = EVENT_TYPES; rg = REGIONS; dv = DEVICES; ch = CHANNELS
    for i in range(1, n + 1):
        amount = round(random.lognormvariate(4.0, 1.1), 2)  # 売上/工数っぽい分布
        meta = json.dumps({"v": ri(1, 5), "ref": rc(ch)})
        yield (i, ri(1, n_org), ri(1, n_user), ri(1, n_proj),
               rc(et), amount, ri(1, 50), rc(rg), rc(dv), rc(ch),
               ri(0, 1) == 1, meta, ts(ri(0, SPAN_SECONDS)))


def gen_articles(n, n_org, n_user, pools):
    sents = pools["sentences"]; words = pools["words"]
    ls = len(sents)
    for i in range(1, n + 1):
        title = f"{random.choice(words)}{random.choice(words)}についての{random.choice(words)}"
        # 本文は種プールの文章を数個つなげて増幅（実在感を保つ）
        body = "".join(sents[(i + k) % ls] for k in range(3))
        meta = json.dumps({"views": random.randint(0, 100000),
                           "lang": "ja"})
        yield (i, random.randint(1, n_org), random.randint(1, n_user),
               title, body, random.choice(["draft", "published", "archived"]),
               meta, ts(random.randint(0, SPAN_SECONDS)))


def gen_tags(n):
    for i in range(1, n + 1):
        yield (i, fake.word() + str(i))


def gen_article_tags(n_art, n_tag):
    for a in range(1, n_art + 1):
        for _ in range(2):  # 1記事に約2タグ
            yield (a, random.randint(1, n_tag))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--scale", type=int, required=True,
                    help="events（およびCMSのarticles）の行数")
    ap.add_argument("--tables", default="core",
                    choices=["core", "cms", "all"])
    ap.add_argument("--seed-size", type=int, default=50000)
    args = ap.parse_args()

    N = args.scale
    # 現実的な比率でサテライトテーブルを決める
    n_org = max(20, N // 20000)
    n_user = min(max(N // 20, 50), 10_000_000)   # 1億ユーザーは非現実的→上限
    n_proj = max(50, N // 2000)
    pools = build_pools(args.seed_size)

    with psycopg.connect(args.dsn) as conn:
        # COPY 高速化
        conn.execute("SET synchronous_commit = off")
        if args.tables in ("core", "all"):
            print(f"[plan] orgs={n_org:,} users={n_user:,} "
                  f"projects={n_proj:,} events={N:,}", file=sys.stderr)
            copy_table(conn, "organizations",
                       ["id", "name", "plan", "country", "created_at"],
                       gen_orgs(n_org, pools), n_org, "orgs")
            copy_table(conn, "users",
                       ["id", "org_id", "email", "full_name", "role", "created_at"],
                       gen_users(n_user, n_org, pools), n_user, "users")
            copy_table(conn, "projects",
                       ["id", "org_id", "owner_id", "name", "status", "created_at"],
                       gen_projects(n_proj, n_org, n_user, pools), n_proj, "projects")
            copy_table(conn, "events",
                       ["id", "org_id", "user_id", "project_id", "event_type",
                        "amount", "quantity", "region", "device", "channel",
                        "is_billable", "metadata", "occurred_at"],
                       gen_events(N, n_org, n_user, n_proj), N, "events")

        if args.tables in ("cms", "all"):
            n_art = min(N // 2, 50_000_000) if args.tables == "all" else N
            n_tag = 300
            print(f"[plan] articles={n_art:,} tags={n_tag}", file=sys.stderr)
            # CMS単独実行時は基盤が無い場合があるので最小限を補う
            conn.execute("INSERT INTO organizations (id,name,plan,country,created_at) "
                         "VALUES (1,'seed','pro','JP',now()) ON CONFLICT DO NOTHING")
            conn.execute("INSERT INTO users (id,org_id,email,full_name,role,created_at) "
                         "VALUES (1,1,'seed@example.com','seed','admin',now()) "
                         "ON CONFLICT DO NOTHING")
            conn.commit()
            n_org_eff = n_org if args.tables == "all" else 1
            n_user_eff = n_user if args.tables == "all" else 1
            copy_table(conn, "tags", ["id", "name"], gen_tags(n_tag), n_tag, "tags")
            copy_table(conn, "articles",
                       ["id", "org_id", "author_id", "title", "body",
                        "status", "metadata", "created_at"],
                       gen_articles(n_art, n_org_eff, n_user_eff, pools),
                       n_art, "articles")
            copy_table(conn, "article_tags", ["article_id", "tag_id"],
                       gen_article_tags(n_art, n_tag), n_art * 2, "article_tags")

    print("[done] ロード完了", file=sys.stderr)


if __name__ == "__main__":
    main()
