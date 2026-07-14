"""Управление CLO-туннелем (динамический публичный URL)."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import Optional

from .constants import ALBUM_API_PORT

log = logging.getLogger("cards.clo")

_HTTPS_URL_RE = re.compile(r"https://[^\s\"']+", re.IGNORECASE)
_URL_WAIT_SEC = 45.0


def _clo_critical(message: str) -> None:
    """Красная критическая ошибка CLO в лог и stderr."""
    banner = (
        "\n"
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        f"  CLO ERROR: {message}\n"
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
    )
    # ANSI bright red (Windows Terminal / modern consoles)
    sys.stderr.write(f"\033[91m{banner}\033[0m")
    sys.stderr.flush()
    log.error("CLO ERROR: %s", message)


class CloTunnelError(RuntimeError):
    """Критический сбой CLO-туннеля."""


class CloTunnel:
    def __init__(
        self,
        exe_path: str,
        local_port: int = ALBUM_API_PORT,
        fallback_url: str = "",
        *,
        protocol: str = "http",
        token: str = "",
    ) -> None:
        self._exe_path = Path(exe_path)
        self._protocol = protocol
        self._local_port = int(local_port)
        self._fallback_url = fallback_url.rstrip("/")
        self._token = token.strip()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._public_url: str = self._fallback_url
        self._last_output: str = ""

    @property
    def public_url(self) -> str:
        return self._public_url

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def _run_clo(self, *args: str, timeout: float = 30.0) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            str(self._exe_path),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self._exe_path.parent),
        )
        try:
            out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise CloTunnelError(f"таймаут команды: clo {' '.join(args)}")
        text = (out_b or b"").decode("utf-8", errors="replace")
        code = proc.returncode if proc.returncode is not None else -1
        return code, text

    async def _apply_token(self) -> None:
        if not self._token:
            _clo_critical(
                "CLO_TOKEN пуст в .env — задай токен CloudPub (clo options / личный кабинет)."
            )
            raise CloTunnelError("CLO_TOKEN не задан")
        code, out = await self._run_clo("set", "token", self._token, timeout=20.0)
        if code != 0:
            _clo_critical(f"clo set token завершился с кодом {code}: {out.strip() or 'нет вывода'}")
            raise CloTunnelError("не удалось записать CLO_TOKEN")
        log.info("CLO: token записан через clo set token")

    async def start(self) -> bool:
        """Поднять CLO. При ошибке — красный CRITICAL и CloTunnelError (кроме CLO_PUBLIC_URL)."""
        if self._fallback_url:
            self._public_url = self._fallback_url
            log.info("CLO: используем CLO_PUBLIC_URL=%s (без clo.exe)", self._public_url)
            return True

        if not self._exe_path.is_file():
            _clo_critical(f"clo.exe не найден: {self._exe_path}")
            raise CloTunnelError(f"clo.exe не найден: {self._exe_path}")

        try:
            await self._apply_token()
        except CloTunnelError:
            raise
        except Exception as exc:
            _clo_critical(f"сбой при clo set token: {exc}")
            raise CloTunnelError("сбой при clo set token") from exc

        # clo publish <PROTOCOL> <ADDRESS>  — e.g. clo publish http 18770
        try:
            self._process = await asyncio.create_subprocess_exec(
                str(self._exe_path),
                "publish",
                self._protocol,
                str(self._local_port),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self._exe_path.parent),
            )
        except Exception as exc:
            _clo_critical(f"не удалось запустить clo publish: {exc}")
            raise CloTunnelError("не удалось запустить clo publish") from exc

        assert self._process.stdout is not None
        deadline = asyncio.get_event_loop().time() + _URL_WAIT_SEC
        buffer = ""
        while asyncio.get_event_loop().time() < deadline:
            if self._process.returncode is not None:
                break
            try:
                chunk = await asyncio.wait_for(
                    self._process.stdout.read(512),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                if self._public_url:
                    break
                continue
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            buffer += text
            log.debug("CLO: %s", text.rstrip())
            match = _HTTPS_URL_RE.search(buffer)
            if match:
                self._public_url = match.group(0).rstrip("/.,;")
                log.info("CLO публичный URL: %s", self._public_url)
                return True

        self._last_output = buffer.strip()
        if self._public_url:
            return True

        snippet = self._last_output[-800:] if self._last_output else "(пусто)"
        code = self._process.returncode if self._process else None
        _clo_critical(
            "публичный URL не получен после clo publish. "
            f"exit={code}; вывод:\n{snippet}"
        )
        await self.stop()
        raise CloTunnelError("CLO: публичный URL не распознан")

    async def stop(self) -> None:
        if self._process is None:
            return
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None
