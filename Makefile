# =====================================================================
#  ワンタッチ追試用 Makefile
#
#  典型的な流れ:
#    make up                      # PG17 / PG18 を起動
#    make schema                  # 両方にスキーマ作成
#    make load SCALE=1000000      # 両方に同じデータを投入（種プール増幅）
#    make index                   # 投入後にインデックス作成
#    make bench SCALE=1000000     # 全シナリオを両方で実測 → results/ に出力
#    make chart                   # 結果をグラフ化
#
#  条件を変えたいとき:
#    make load SCALE=50000000     # 5000万行
#    IO_METHOD=sync make restart-pg18   # PG18のAIOを切って比較
# =====================================================================
SCALE   ?= 1000000
PG17_DSN = postgresql://bench:bench@localhost:5417/bench
PG18_DSN = postgresql://bench:bench@localhost:5418/bench
PY       = python3

up:
	docker compose up -d
	@echo "起動待ち..." && sleep 8

down:
	docker compose down -v

restart-pg18:
	docker compose up -d --force-recreate pg18 && sleep 6

schema:
	psql "$(PG17_DSN)" -f sql/schema.sql
	psql "$(PG18_DSN)" -f sql/schema.sql

load:
	$(PY) loader/load.py --dsn "$(PG17_DSN)" --tables core --scale $(SCALE)
	$(PY) loader/load.py --dsn "$(PG18_DSN)" --tables core --scale $(SCALE)

load-cms:
	$(PY) loader/load.py --dsn "$(PG17_DSN)" --tables cms --scale $(SCALE)
	$(PY) loader/load.py --dsn "$(PG18_DSN)" --tables cms --scale $(SCALE)

index:
	psql "$(PG17_DSN)" -f sql/indexes.sql && psql "$(PG17_DSN)" -c "ANALYZE"
	psql "$(PG18_DSN)" -f sql/indexes.sql && psql "$(PG18_DSN)" -c "ANALYZE"

bench:
	@mkdir -p results
	$(PY) bench/run_bench.py --dsn "$(PG17_DSN)" --scenario all --tag pg17  > results/pg17_$(SCALE).json
	$(PY) bench/run_bench.py --dsn "$(PG18_DSN)" --scenario all --tag pg18  > results/pg18_$(SCALE).json

chart:
	$(PY) charts/make_charts.py

deps:
	pip install -r loader/requirements.txt

.PHONY: up down restart-pg18 schema load load-cms index bench chart deps
