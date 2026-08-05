"""扩容执行器：NoopScaler（dry-run）与 ComposeScaler（docker compose --scale）。"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Protocol

logger = logging.getLogger(__name__)


class Scaler(Protocol):
    async def set_replicas(self, service: str, count: int) -> None: ...


class NoopScaler:
    """dry-run：只记录决策，不真正执行。"""

    async def set_replicas(self, service: str, count: int) -> None:
        logger.info("[dry-run] 调整 %s 副本数 -> %s", service, count)


class ComposeScaler:
    """在宿主机执行 docker compose up -d --scale <service>=<count>。"""

    def __init__(
        self,
        compose_dir: str = ".",
        compose_file: str = "docker-compose.prod.yml",
        compose_env_file: str = ".env.prod",
    ) -> None:
        self._dir = compose_dir
        self._file = compose_file
        self._env_file = compose_env_file

    async def set_replicas(self, service: str, count: int) -> None:
        cmd = [
            "docker",
            "compose",
            "-f",
            self._file,
            "--env-file",
            self._env_file,
            "up",
            "-d",
            "--scale",
            f"{service}={count}",
        ]
        logger.info("执行扩容: %s", " ".join(cmd))
        result = await asyncio.to_thread(subprocess.run, cmd, cwd=self._dir, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error("扩容命令失败: %s", result.stderr[-500:])
            raise RuntimeError(f"docker compose --scale 失败: {result.stderr[-200:]}")
        logger.info("扩容成功: %s -> %s", service, count)