-- =====================================================================
--  PostgreSQL 17 vs 18 ベンチマーク用スキーマ
--  題材: 業務SaaS（プロジェクト管理 + 行動ログ分析 + 社内CMS）
--
--  読者が「自分のDBに近い」と感じられるよう、5つの典型テーブルを
--  1つの現実的なドメインに統合している。
--    organizations / users / projects ... 基盤
--    events ........................... ① 集計レポート ② スキップスキャン ④ 深いJOIN
--    users ............................ ④ 認証の点ルックアップ（カウンターウェイト）
--    articles / tags .................. ③ CMS全文・あいまい検索
--  PostgreSQL 17 / 18 のどちらでも同一DDLで動く（18固有構文は使わない）
-- =====================================================================

-- あいまい検索（部分一致・類似検索）に使う拡張
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------
-- 基盤テーブル（テナント・ユーザー・プロジェクト）
-- ---------------------------------------------------------------------
CREATE TABLE organizations (
    id          bigint PRIMARY KEY,
    name        text        NOT NULL,
    plan        text        NOT NULL,          -- free / pro / enterprise
    country     text        NOT NULL,
    created_at  timestamptz NOT NULL
);

-- 認証ペルソナ: ログイン時の「メールで1人引く」点ルックアップを測る
CREATE TABLE users (
    id          bigint PRIMARY KEY,
    org_id      bigint      NOT NULL REFERENCES organizations(id),
    email       text        NOT NULL,
    full_name   text        NOT NULL,
    role        text        NOT NULL,          -- admin / member / viewer
    created_at  timestamptz NOT NULL
);

CREATE TABLE projects (
    id          bigint PRIMARY KEY,
    org_id      bigint      NOT NULL REFERENCES organizations(id),
    owner_id    bigint      NOT NULL REFERENCES users(id),
    name        text        NOT NULL,
    status      text        NOT NULL,          -- active / archived
    created_at  timestamptz NOT NULL
);

-- ---------------------------------------------------------------------
-- 行動ログ（ファクトテーブル）: 本ベンチの主役
--   ① 大規模集計（非同期I/O）
--   ② スキップスキャン（event_type, occurred_at の複合インデックス）
--   ④ 深いリレーション + 多カラムのJOIN集計
-- ---------------------------------------------------------------------
CREATE TABLE events (
    id           bigint PRIMARY KEY,
    org_id       bigint      NOT NULL REFERENCES organizations(id),
    user_id      bigint      NOT NULL REFERENCES users(id),
    project_id   bigint      NOT NULL REFERENCES projects(id),
    event_type   text        NOT NULL,         -- 低カーディナリティ（8種類）= スキップスキャンの肝
    amount       numeric(12,2) NOT NULL,       -- 集計対象（売上・工数など）
    quantity     integer     NOT NULL,
    region       text        NOT NULL,
    device       text        NOT NULL,
    channel      text        NOT NULL,
    is_billable  boolean     NOT NULL,
    metadata     jsonb       NOT NULL,
    occurred_at  timestamptz NOT NULL
);

-- ---------------------------------------------------------------------
-- 社内CMS: 記事保存 + あいまい検索（ペルソナC）
-- ---------------------------------------------------------------------
CREATE TABLE articles (
    id          bigint PRIMARY KEY,
    org_id      bigint      NOT NULL REFERENCES organizations(id),
    author_id   bigint      NOT NULL REFERENCES users(id),
    title       text        NOT NULL,
    body        text        NOT NULL,
    status      text        NOT NULL,          -- draft / published / archived
    metadata    jsonb       NOT NULL,
    created_at  timestamptz NOT NULL
);

CREATE TABLE tags (
    id   bigint PRIMARY KEY,
    name text   NOT NULL
);

CREATE TABLE article_tags (
    article_id bigint NOT NULL REFERENCES articles(id),
    tag_id     bigint NOT NULL REFERENCES tags(id),
    PRIMARY KEY (article_id, tag_id)
);
