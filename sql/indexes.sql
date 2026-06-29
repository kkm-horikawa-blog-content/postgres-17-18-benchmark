-- =====================================================================
--  インデックス（データ投入後に作成すると速い）
--  各シナリオが「効く条件」をここで作り込む。
-- =====================================================================

-- 【シナリオ②】スキップスキャンの肝。
--   複合インデックスの先頭列 event_type は8種類しかない（低カーディナリティ）。
--   occurred_at 単独のインデックスは「あえて作らない」。
--   → occurred_at だけで絞るクエリは、PG17ではこの索引を活かせず全表スキャンに倒れ、
--     PG18では先頭列を読み飛ばすスキップスキャンが効く。
CREATE INDEX idx_events_type_time ON events (event_type, occurred_at);

-- 【シナリオ④】深いJOINのための外部キー索引
CREATE INDEX idx_events_user    ON events (user_id);
CREATE INDEX idx_events_project ON events (project_id);
CREATE INDEX idx_projects_org   ON projects (org_id);
CREATE INDEX idx_projects_owner ON projects (owner_id);
CREATE INDEX idx_users_org      ON users (org_id);

-- 【カウンターウェイト: 認証の点ルックアップ】メールで1人引く
CREATE INDEX idx_users_email ON users (email);

-- 【ペルソナC】あいまい検索（部分一致・類似）用の trigram GIN 索引
CREATE INDEX idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops);
CREATE INDEX idx_articles_body_trgm  ON articles USING gin (body  gin_trgm_ops);
CREATE INDEX idx_articles_org        ON articles (org_id);
