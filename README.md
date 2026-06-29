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

## サンプル結果（2000万件・本記事の実測）

`sample_results/` に、記事で使った実測結果（JSON）とグラフを同梱しています。
要点: 大規模集計は PG18 がむしろ遅く（io_method 既定 worker で 4.3s→7.1s）、
複合索引の絞り込み（スキップスキャン）は速くなりました（847ms→585ms）。
詳細は記事を参照してください。

## 追加検証スクリプト（記事の深掘り）

「大きな集計が18で遅くなった」の原因を追う過程で足した、より細かく計測するためのスクリプト群です。`make up schema load index` でデータを入れた状態で使います（Python依存は `make deps`、または `python -m venv .venv && .venv/bin/pip install psycopg[binary] faker matplotlib`）。

| スクリプト | 何をするか |
|---|---|
| `bench/probe.py` | s1/s4/s2 を `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` で計測し、実行時間・I/O待ち・shared hit/read・並列ワーカー数を1行で出す。`--set "key=val"` で任意GUCを適用 |
| `cold.sh <port> <label>` | OSページキャッシュを drop して cold（ディスクから読む）状態で計測 |
| `diskbound.sh <port> <label>` | メモリ上限でキャッシュを絞り、テーブル>キャッシュのディスク律速で計測 |
| `write_bench.sh <port> <label> [N]` | INSERT/UPDATE/DELETE/VACUUM の書き込み計測（チェックサムの影響確認） |
| `run_conc.sh <label> <接続数...>` ＋ `bench_user.sql` | pgbench で同時接続スループット(TPS)を測る |
| `throttle.sh <riops\|0>` | cgroup で read IOPS を絞り「遅いディスク」を再現（`0` で解除） |
| `grow_pg18.sh` | events を Faker無しの `INSERT...SELECT` 倍々で >RAM まで増やす |
| `override-iouring.yml` | `io_method=io_uring` を試すとき seccomp を外す compose override |
| `charts/blog_figures.py` | 記事の図（集計の回復・I/O待ちvs実時間・同時接続TPS）を再生成 |

```bash
make probe Q=s1_aggregate          # 大きな集計の実行計画と時間
make probe Q=s4_deepjoin
bash cold.sh 5418 PG18             # cold（ディスク読み）で計測
bash write_bench.sh 5418 PG18     # 書き込み
bash run_conc.sh PG18 1 16 64     # 同時接続スループット
```

### 分かったこと（要点）

- **「大きな集計が18で遅い」の真因は非同期I/Oではなく、プランナが並列をやめて直列化したこと。** 式での `GROUP BY`（`date_trunc('month', …)`）がグループ数の見積りを大きく外し、並列が割高に見えるため。`max_parallel_workers_per_gather` を上げるか、`CREATE STATISTICS`（拡張統計。**17でも有効**）で見積りを直すと回復する。
- **非同期I/O(AIO)は I/O待ちを大きく減らすが、速いNVMeでは実時間の得は小さい。** さらに同時接続が多いと優位は消え、既定の `io_method=worker` がむしろ最も遅いことがある（`sync`/`io_uring` と要比較、`io_workers` は絞りすぎない）。
- **書き込みは17/18でほぼ互角。** 18でデータチェックサムが既定オンでも体感差はない。
