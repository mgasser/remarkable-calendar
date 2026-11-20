"""Direct upload over SSH (tablet in the same network, Developer Mode on newer models).

Kept for setups where the planner runs at home instead of on a server.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

XOCHITL = "/home/root/.local/share/remarkable/xochitl/"


class SshSync:
    def __init__(self, host: str, password: str, folder: str):
        self.host, self.password, self.folder = host, password, folder

    def upload(self, files: list[Path]) -> None:
        import paramiko

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
        ssh.connect(self.host, username="root", password=self.password, timeout=15)
        try:
            sftp = ssh.open_sftp()
            index = self._index(sftp)
            parent = self._find(index, self.folder, "CollectionType", "") or self._create(sftp, self.folder, "", "CollectionType")
            for f in files:
                doc = self._find(index, f.stem, "DocumentType", parent) or self._create(sftp, f.stem, parent, "DocumentType")
                sftp.put(str(f), f"{XOCHITL}{doc}.pdf")
                log.info("Uploaded %s via SSH", f.name)
            ssh.exec_command("systemctl restart xochitl")
        finally:
            ssh.close()

    @staticmethod
    def _index(sftp) -> dict[str, dict]:
        index = {}
        for name in sftp.listdir(XOCHITL):
            if name.endswith(".metadata"):
                try:
                    with sftp.open(XOCHITL + name) as fh:
                        index[name[:-9]] = json.load(fh)
                except (OSError, ValueError):
                    continue
        return index

    @staticmethod
    def _find(index, name, kind, parent):
        for uid, meta in index.items():
            if meta.get("visibleName") == name and meta.get("type") == kind \
                    and meta.get("parent", "") == parent and not meta.get("deleted"):
                return uid
        return None

    @staticmethod
    def _create(sftp, name, parent, kind) -> str:
        uid = str(uuid.uuid4())
        meta = {"deleted": False, "lastModified": str(int(time.time() * 1000)), "metadatamodified": False,
                "modified": False, "parent": parent, "pinned": False, "synced": False, "type": kind,
                "version": 1, "visibleName": name}
        with sftp.open(f"{XOCHITL}{uid}.metadata", "w") as fh:
            fh.write(json.dumps(meta))
        content = {} if kind == "CollectionType" else {"fileType": "pdf"}
        with sftp.open(f"{XOCHITL}{uid}.content", "w") as fh:
            fh.write(json.dumps(content))
        return uid
