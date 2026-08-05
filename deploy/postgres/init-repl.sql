-- 主库初始化：创建流复制用户（幂等；生产请替换为强密码并与 replica-entrypoint.sh 一致）
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'repl') THEN
    CREATE ROLE repl REPLICATION LOGIN PASSWORD 'replpass';
  END IF;
END
$$;