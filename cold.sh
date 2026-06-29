#!/usr/bin/env bash
# cold 測定: OSページキャッシュをdrop → PG再起動でshared_buffersも空に → 1回だけ実行。
# 実I/O待ち(I/O Timings shared read)と実行時間を取り出す。
# 使い方: cold.sh <port> <label>
set -u
PORT="$1"; LABEL="$2"
PGENV="PGPASSWORD=bench"
PSQL="psql -h localhost -p $PORT -U bench -d bench -tAX"

declare -A Q
Q[count]="SELECT count(*) FROM events"
Q[s1]="SELECT date_trunc('month', occurred_at) AS m, region, sum(amount) AS revenue, count(*) AS cnt FROM events WHERE is_billable GROUP BY 1,2 ORDER BY 1,2"
Q[s4]="SELECT o.plan, p.status, count(*) AS cnt, sum(e.amount) AS revenue FROM events e JOIN projects p ON p.id=e.project_id JOIN organizations o ON o.id=p.org_id JOIN users u ON u.id=p.owner_id WHERE e.is_billable AND e.occurred_at >= timestamptz '2025-01-01' GROUP BY o.plan,p.status ORDER BY revenue DESC"

for key in count s1 s4; do
  # cold 化: 同期 → OSキャッシュdrop（コンテナ再起動はしない。shared_buffers=256MBは小さいので無視できる）
  sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
  out=$(eval $PGENV $PSQL -c "\"EXPLAIN (ANALYZE, BUFFERS) ${Q[$key]}\"" 2>&1)
  exec_ms=$(echo "$out" | grep -oE 'Execution Time: [0-9.]+' | grep -oE '[0-9.]+')
  ioread=$(echo "$out" | grep -oE 'I/O Timings: shared read=[0-9.]+' | grep -oE '[0-9.]+$' | head -1)
  workers=$(echo "$out" | grep -oE 'Workers Launched: [0-9]+' | grep -oE '[0-9]+$' | head -1)
  printf "%-22s %-6s exec=%9sms  io_read=%9sms  workers=%s\n" "$LABEL" "$key" "${exec_ms:-NA}" "${ioread:-0}" "${workers:-0}"
done
