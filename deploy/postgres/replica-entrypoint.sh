#!/bin/sh
# 从库入口：数据目录为空时从主库 pg_basebackup（-R 写入 standby.signal + primary_conninfo），
# 然后交给官方 docker-entrypoint 以 standby 模式启动。POSIX sh，兼容 alpine。
set -eu

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "[replica] initializing from primary via pg_basebackup ..."
  rm -rf "$PGDATA"/*
  pg_basebackup -h postgres -U repl -D "$PGDATA" -R -X stream -P
  chown -R postgres:postgres "$PGDATA"
fi

echo "[replica] starting postgres in standby mode ..."
exec docker-entrypoint.sh postgres