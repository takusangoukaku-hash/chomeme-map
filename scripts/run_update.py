# -*- coding: utf-8 -*-
"""Windows タスクスケジューラ用の起動ラッパー。

pythonw.exe で起動されるため、コンソール画面を出さずに update.py を
子プロセスとして実行し、出力を data/update.log に追記する。
引数はそのまま update.py に渡す(例: --backfill 0 --no-push)。
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY312 = Path(sys.executable).with_name("python.exe")  # pythonw.exe -> python.exe
LOG = ROOT / "data" / "update.log"
CREATE_NO_WINDOW = 0x08000000


def main():
    LOG.parent.mkdir(exist_ok=True)
    # ログは直近 2MB 程度で切り詰める(無限に育てない)
    if LOG.exists() and LOG.stat().st_size > 2_000_000:
        tail = LOG.read_bytes()[-1_000_000:]
        LOG.write_bytes(tail)
    with LOG.open("ab") as log:
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start {sys.argv[1:]} =====\n".encode("utf-8"))
        log.flush()
        r = subprocess.run([str(PY312), str(ROOT / "scripts" / "update.py"), *sys.argv[1:]],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           creationflags=CREATE_NO_WINDOW,
                           env={**__import__("os").environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})
        log.write(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')} end exit={r.returncode} =====\n".encode("utf-8"))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
