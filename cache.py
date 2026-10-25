"""Download the two optional SQLite data files into AstrBot's persistent data area."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

import aiohttp


MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


async def download_sqlite(url: str, destination: Path, required_table: str) -> None:
    """Stream, validate, then atomically install a SQLite snapshot."""
    if not url.startswith("https://"):
        raise ValueError("数据库下载地址必须使用 HTTPS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".download")
    timeout = aiohttp.ClientTimeout(total=180, connect=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                if response.content_length and response.content_length > MAX_DOWNLOAD_BYTES:
                    raise ValueError("数据库下载超过 100 MiB 限额")
                size = 0
                with temporary.open("wb") as output:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_DOWNLOAD_BYTES:
                            raise ValueError("数据库下载超过 100 MiB 限额")
                        output.write(chunk)
        await asyncio.to_thread(_validate_sqlite, temporary, required_table)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_sqlite(path: Path, required_table: str) -> None:
    with path.open("rb") as source:
        if source.read(16) != b"SQLite format 3\x00":
            raise ValueError("下载内容不是 SQLite 数据库")
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        found = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (required_table,),
        ).fetchone()
        if not found:
            raise ValueError(f"数据库缺少 {required_table} 表")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite 数据库完整性检查失败")
    finally:
        connection.close()
