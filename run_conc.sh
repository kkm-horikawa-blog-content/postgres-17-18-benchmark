#!/usr/bin/env bash
LABEL="$1"; shift; CLIENTS="$@"
for c in $CLIENTS; do
  j=$(( c<8 ? c : 8 ))
  out=$(docker exec -e PGPASSWORD=bench pg-bench-pg18-1 pgbench -h localhost -p 5432 -U bench -d bench -f /tmp/bench_user.sql -c $c -j $j -T 12 -n 2>&1)
  tps=$(echo "$out" | grep -oE 'tps = [0-9.]+' | head -1 | grep -oE '[0-9.]+')
  lat=$(echo "$out" | grep -oE 'latency average = [0-9.]+' | grep -oE '[0-9.]+')
  printf "%-16s c=%-3s tps=%-9s lat=%sms\n" "$LABEL" "$c" "${tps:-NA}" "${lat:-NA}"
done
