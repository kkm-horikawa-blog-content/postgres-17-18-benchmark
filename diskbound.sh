#!/usr/bin/env bash
# ディスク律速測定: メモリ上限でキャッシュを絞った状態(23GB heap >> cache)で
# count(全走査) と s1(集計) を3回。実I/O待ちが大きく出るはず。
set -u
PORT="$1"; LABEL="$2"
P="psql -h localhost -p $PORT -U bench -d bench -tAX"
declare -A Q
Q[count]="SELECT count(*) FROM events"
Q[s1]="SELECT date_trunc('month', occurred_at) AS m, region, sum(amount), count(*) FROM events WHERE is_billable GROUP BY 1,2 ORDER BY 1,2"
for key in count s1; do
  for r in 1 2 3; do
    out=$(PGPASSWORD=bench $P -c "EXPLAIN (ANALYZE, BUFFERS) ${Q[$key]}" 2>&1)
    e=$(echo "$out" | grep -oE 'Execution Time: [0-9.]+' | grep -oE '[0-9.]+')
    io=$(echo "$out" | grep -oE 'I/O Timings: shared read=[0-9.]+' | grep -oE '[0-9.]+$' | head -1)
    w=$(echo "$out" | grep -oE 'Workers Launched: [0-9]+' | grep -oE '[0-9]+$' | head -1)
    printf "%-18s %-6s r%s exec=%9sms io_read=%9sms workers=%s\n" "$LABEL" "$key" "$r" "${e:-NA}" "${io:-0}" "${w:-0}"
  done
done
