#!/usr/bin/env bash
# 現pg18コンテナのcgroupに read IOPS 制限をかける（遅いディスク再現）。引数: riops (0=解除)
PID=$(docker inspect -f '{{.State.Pid}}' pg-bench-pg18-1)
CG="/sys/fs/cgroup$(sed 's/^0:://' /proc/$PID/cgroup)"
if [ "$1" = "0" ]; then
  echo "259:0 rbps=max wiops=max riops=max wbps=max" | sudo tee "$CG/io.max" >/dev/null
  echo "throttle cleared"
else
  echo "259:0 riops=$1" | sudo tee "$CG/io.max" >/dev/null
  echo "throttle set: riops=$1 on $CG"
fi
