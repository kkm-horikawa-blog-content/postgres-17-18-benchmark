#!/usr/bin/env bash
# pg18 の events を Faker無しの INSERT...SELECT 倍々で >RAM(37GB) まで増やす。
# scan(count/s1) のディスク律速テスト用。索引は全部落として heap だけにする（挿入も走査も素直に）。
set -eu
P(){ PGPASSWORD=bench psql -h localhost -p 5418 -U bench -d bench -tAX -c "$1"; }
echo "START $(date +%H:%M:%S)  rows=$(P 'select count(*) from events')"
P "ALTER TABLE events DROP CONSTRAINT IF EXISTS events_pkey" || true
for idx in idx_events_type_time idx_events_user idx_events_project; do P "DROP INDEX IF EXISTS $idx" || true; done
P "SET maintenance_work_mem='1GB'" || true
COLS="id + (SELECT max(id) FROM events), org_id,user_id,project_id,event_type,amount,quantity,region,device,channel,is_billable,metadata,occurred_at"
for step in 1 2 3 4; do   # 20M -> 40 -> 80 -> 160 -> 320M
  t0=$(date +%s)
  P "INSERT INTO events SELECT $COLS FROM events"
  n=$(P 'select count(*) from events')
  echo "  step $step done: rows=$n  (+$(( $(date +%s)-t0 ))s)  heap=$(P "select pg_size_pretty(pg_relation_size('events'))")"
done
P "ANALYZE events"
echo "DONE $(date +%H:%M:%S) rows=$(P 'select count(*) from events') heap=$(P "select pg_size_pretty(pg_relation_size('events'))")"
