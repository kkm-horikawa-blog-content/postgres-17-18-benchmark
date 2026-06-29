# PostgreSQL 17 → 18 実機ベンチマーク

PostgreSQL 17.9 と 18 を Docker で並走させ、**「どんな用途のテーブルで・どれくらい体感が変わるか」** を実測するためのベンチマーク一式です。

公式アナウンスの数字ではなく、自分の手元で再現・カスタムできることを重視しています。ブログ記事の検証コードとして公開しています。

> 関連記事: [PostgreSQL 18は本当に速いのか、17から上げて5000万行で実測した（kkm-mako.com）](https://kkm-mako.com/blog/articles/postgresql-18-upgrade-benchmark/)

## 何を測るか（5つの典型テーブル）

実務でよくある5パターンのテーブル・クエリを、PG17とPG18の両方で実行して比較します。

| シナリオ | 想定する読者のテーブル | 効くPG18の新機能 |
|---|---|---|
| ① 大規模集計 | 売上・ログの集計レポート / ダッシュボード | 非同期I/O（`io_method`） |
| ② スキップスキャン | マルチテナントSaaSの業務テーブル | B-treeスキップスキャン |
| ④ 深いJOIN | 多テーブルをたどる集計 | プランナ + 非同期I/O |
| 認証の点ルックアップ | ログイン・セッション（カウンターウェイト） | （ほぼ変化なし） |
| CMSあいまい検索 | 記事・投稿の部分一致検索 | （要実測） |

## 必要なもの

- Docker / Docker Compose
- `psql` クライアント（`make schema` などで使用）
- Python 3.10+（データ生成・ベンチ実行）

## 使い方（ワンタッチ）

```bash
make deps                    # Python依存(psycopg, Faker, matplotlib)をインストール
make up                      # PostgreSQL 17.9 / 18 を起動
make schema                  # 両方にスキーマを作成
make load   SCALE=1000000    # 両方に同じデータを投入（種プール増幅・乱数固定で同一）
make index                   # 投入後にインデックス作成 + ANALYZE
make bench  SCALE=1000000    # 全シナリオを両方で実測 → results/ にJSON出力
make chart                   # 結果をPNGグラフ化 → charts/output/
```

### 条件を変えて追試する

```bash
make load SCALE=50000000     # 5000万行（ディスクとRAMに余裕があれば1億も可）
make load-cms SCALE=1000000  # CMS（記事）テーブルだけ投入

# PG18の非同期I/Oを切って比較（worker / sync / io_uring）
IO_METHOD=sync make restart-pg18
```

## 仕組み

### 種プール増幅方式（loader/load.py）

Faker は1件ずつ生成すると遅く、1億行を素直に作ると日が暮れます。そこで「リアルな種プール」（実在感のある名前・会社名・文章を数万〜数十万件）を一度だけ Faker で生成し、それを組み合わせ・サンプリングして大量行へ COPY で増幅します。実在感と規模を両立させる手法です。

乱数シードを固定しているので、**PG17とPG18にまったく同じデータ**が入ります（=バージョン差だけを測れる）。

### ディスク律速に追い込む（docker-compose.yml）

`shared_buffers` を 256MB に固定し、データを RAM に載りきらせないことで、非同期I/Oの効果が体感レベルで出るようにしています。データ量がマシンのRAMを十分に超えるスケール（例: 5000万行以上）で測ると、シナリオ①の差が顕著になります。

## ライセンス

MIT
