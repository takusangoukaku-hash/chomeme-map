# -*- coding: utf-8 -*-
"""通知用スケジュールタスク(Claude)から呼ばれる補助スクリプト。

1. 今日の更新がまだ始まっていなければ、タスクスケジューラの
   chomeme-map-daily-update を起動する(取りこぼしの保険)
2. 更新が終わるまで待つ(最長 --timeout 秒、既定4時間)
3. 結果を1行のJSON(RESULT: {...})で出力する
   - pending_shops: まだ通知していない新着店舗(過去分の未通知も含む)
   - last_run: 直近の実行記録(data/last_run.json)
   - days_since_push: 最後に git push した日からの経過日数
   - lock_running: 待機終了時点でまだ実行中か

`--ack` を付けると pending_shops を「通知済み」として消去するだけで終了する。
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOCK = DATA / "update.lock"
LAST_RUN = DATA / "last_run.json"
PENDING = DATA / "pending_notify.json"
TASK_NAME = "chomeme-map-daily-update"
JST = timezone(timedelta(hours=9))


def argval(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return default


def last_run():
    if LAST_RUN.exists():
        return json.loads(LAST_RUN.read_text(encoding="utf-8"))
    return None


def last_run_time():
    lr = last_run()
    if not lr:
        return None
    return datetime.strptime(lr["finished"], "%Y-%m-%dT%H:%M:%S%z")


def ran_recently(hours=12):
    t = last_run_time()
    return t is not None and datetime.now(JST) - t < timedelta(hours=hours)


def days_since_push():
    r = subprocess.run(["git", "log", "-1", "--format=%cI", "origin/main"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    t = datetime.fromisoformat(r.stdout.strip())
    return round((datetime.now(JST) - t).total_seconds() / 86400, 1)


def start_task():
    r = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME],
                       capture_output=True, text=True, encoding="cp932", errors="replace")
    print(f"schtasks /Run -> exit {r.returncode}: {(r.stdout or r.stderr).strip()}")
    return r.returncode == 0


def main():
    if "--ack" in sys.argv:
        PENDING.unlink(missing_ok=True)
        print("acknowledged: pending_notify.json cleared")
        return 0

    timeout = argval("--timeout", 4 * 3600)
    t0 = time.time()

    # 1. 実行中でも今日の実行済みでもなければ起動(数分待って様子を見る)
    if not LOCK.exists() and not ran_recently():
        print("no update running today yet -> waiting 5 min for the scheduler")
        time.sleep(300)
        if not LOCK.exists() and not ran_recently():
            print("still nothing -> starting the task ourselves")
            if not start_task():
                print("fallback: running update.py directly")
                subprocess.Popen([sys.executable, str(ROOT / "scripts" / "run_update.py")],
                                 cwd=ROOT)
            time.sleep(60)

    # 2. 終わるまで待つ
    while time.time() - t0 < timeout:
        if not LOCK.exists() and ran_recently():
            break
        time.sleep(60)

    pending = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []
    result = {
        "pending_shops": pending,
        "last_run": last_run(),
        "days_since_push": days_since_push(),
        "lock_running": LOCK.exists(),
        "waited_min": round((time.time() - t0) / 60),
    }
    print("RESULT: " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
