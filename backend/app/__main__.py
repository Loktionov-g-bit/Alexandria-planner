"""Container entrypoint: apply migrations, then serve."""

import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from .config import get_settings


def alembic(root: Path, *args: str) -> str:
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def wait_for_db(root: Path, attempts: int = 30) -> None:
    """A fresh PostgreSQL answers its healthcheck during initdb and then restarts once; wait until it really accepts us."""
    for i in range(attempts):
        try:
            alembic(root, "current")
            return
        except subprocess.CalledProcessError:
            if i == attempts - 1:
                raise
            print("database not ready yet, retrying", flush=True)
            time.sleep(2)


def backup_before_migration(root: Path) -> None:
    """SPEC §10: automatic DB backup before every migration (only when one is pending)."""
    current = alembic(root, "current").split()
    head = alembic(root, "heads").split()
    if not current or not head or current[0] == head[0]:
        return  # nothing to migrate (or a brand new database)
    st = get_settings()
    folder = st.data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    url = st.database_url
    if url.startswith("sqlite"):
        src = Path(url.split("///", 1)[1])
        dst = folder / f"pre-{head[0]}-{stamp}.sqlite3"
        shutil.copy2(src, dst)
    else:
        dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        dst = folder / f"pre-{head[0]}-{stamp}.dump"
        # pg_dump custom format, compressed; restore: pg_restore -d <db> --clean <file>
        subprocess.run(["pg_dump", "--format=custom", "--no-owner", f"--file={dst}", dsn], check=True)
    print(f"backup before migration: {dst}", flush=True)
    old = sorted(folder.glob("pre-*"), key=lambda p: p.stat().st_mtime)
    for p in old[: max(0, len(old) - st.backup_keep)]:
        p.unlink(missing_ok=True)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    wait_for_db(root)
    backup_before_migration(root)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, check=True)
    st = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips=st.forwarded_allow_ips,
        root_path=st.root_path,
        log_level="info",
    )


if __name__ == "__main__":
    main()
