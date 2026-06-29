#!/usr/bin/env bash
# 書き込み(CRUD)実測: INSERT 3M / UPDATE ~600k / DELETE ~430k。
# 各操作前に CHECKPOINT して条件を揃え、\timing の値を拾う。
set -u
PORT="$1"; LABEL="$2"; N="${3:-3000000}"
P(){ PGPASSWORD=bench psql -h localhost -p "$PORT" -U bench -d bench -tAX "$@"; }
ms(){ P -c "\timing on" -c "$1" 2>&1 | grep -oE 'Time: [0-9.]+ ms' | grep -oE '[0-9.]+' | head -1; }

P -c "DROP TABLE IF EXISTS wtest" >/dev/null
P -c "CREATE TABLE wtest (id bigint, org_id bigint, amount numeric(12,2), occurred_at timestamptz, payload text)" >/dev/null

P -c "CHECKPOINT" >/dev/null
ins=$(ms "INSERT INTO wtest SELECT g, (g%1000)+1, (g%100000)/100.0, timestamptz '2025-01-01' + (g%2000000)*interval '1 sec', md5(g::text) FROM generate_series(1,$N) g")
P -c "CREATE INDEX ON wtest(id)" >/dev/null
P -c "CHECKPOINT" >/dev/null
upd=$(ms "UPDATE wtest SET amount = amount + 1 WHERE id % 5 = 0")
P -c "CHECKPOINT" >/dev/null
del=$(ms "DELETE FROM wtest WHERE id % 7 = 0")
P -c "CHECKPOINT" >/dev/null
vac=$(ms "VACUUM wtest")

cks=$(P -tAc "show data_checksums")
printf "%-14s checksums=%-3s  INSERT(%s)=%8sms  UPDATE=%8sms  DELETE=%8sms  VACUUM=%8sms\n" \
  "$LABEL" "$cks" "$N" "${ins:-NA}" "${upd:-NA}" "${del:-NA}" "${vac:-NA}"
