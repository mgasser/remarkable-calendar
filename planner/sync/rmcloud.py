"""Upload to the reMarkable Cloud with rmapi (https://github.com/ddvk/rmapi).

`put --content-only` replaces the PDF of an existing document and keeps its handwriting;
for a document that does not exist yet it creates a new one.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class RmapiError(RuntimeError):
    pass


class CloudSync:
    def __init__(self, rmapi_bin: str, config_path: Path, folder: str, timeout: int = 300):
        self.bin = rmapi_bin
        self.config_path = config_path
        self.folder = "/" + folder.strip("/")
        self.timeout = timeout

    def _run(self, *args: str, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
        env = {**os.environ, "RMAPI_CONFIG": str(self.config_path)}
        proc = subprocess.run([self.bin, *args], env=env, input=input_text, text=True,
                              capture_output=True, timeout=self.timeout)
        if check and proc.returncode != 0:
            raise RmapiError(f"rmapi {' '.join(args)} failed ({proc.returncode}): "
                             f"{(proc.stderr or proc.stdout).strip()[-500:]}")
        return proc

    @property
    def authenticated(self) -> bool:
        return self.config_path.exists() and self.config_path.stat().st_size > 0

    def authenticate(self, one_time_code: str | None = None) -> None:
        """First login. Code from https://my.remarkable.com/device/desktop/connect"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if one_time_code:
            self._run("ls", "/", input_text=one_time_code.strip() + "\n")
        else:  # interactive: rmapi asks for the code itself
            env = {**os.environ, "RMAPI_CONFIG": str(self.config_path)}
            if subprocess.run([self.bin, "ls", "/"], env=env).returncode != 0:
                raise RmapiError("rmapi login failed")
        if not self.authenticated:
            raise RmapiError("rmapi did not store a token; check the one-time code")
        log.info("reMarkable Cloud: logged in, token stored in %s", self.config_path)

    def ensure_folder(self) -> None:
        parts = [p for p in self.folder.split("/") if p]
        path = ""
        for part in parts:
            parent = path or "/"
            path = f"{path}/{part}"
            listing = self._run("ls", parent, check=False).stdout
            names = {line.split("\t", 1)[-1].strip() for line in listing.splitlines() if line.startswith("[d]")}
            if part not in names:
                self._run("mkdir", path)
                log.info("Created folder %s on the reMarkable", path)

    def upload(self, files: list[Path]) -> None:
        if not self.authenticated:
            raise RmapiError(f"Not logged in to reMarkable Cloud ({self.config_path} missing). "
                             "Run: docker compose run --rm planner auth")
        self.ensure_folder()
        for f in files:
            self._run("put", "--content-only", str(f), self.folder)
            log.info("Uploaded %s to %s", f.name, self.folder)
