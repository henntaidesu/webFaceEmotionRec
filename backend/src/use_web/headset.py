"""通过 USB 数据线用 adb 管理 Quest 头显（网页驱动，逻辑跑在后端）。

核心：adb 反向隧道（adb reverse tcp:PORT tcp:PORT）——头显访问自己的
localhost:PORT，adb 经 USB 把它转发到电脑后端。这样头显连后端**不用 WiFi、
不用同网段、不用开防火墙**，只要数据线连着并授权 USB 调试即可。

头显里 Unity 应用把 backendBaseUrl 设为 http://127.0.0.1:PORT 即走此通道。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .. import config


def find_adb() -> str | None:
    """定位 adb.exe：先看 config.ADB_PATH，再查 MQDH 常见路径，最后查 PATH。"""
    if config.ADB_PATH and Path(config.ADB_PATH).exists():
        return config.ADB_PATH
    candidates = [
        r"D:\Program Files\Meta Quest Developer Hub\resources\bin\adb.exe",
        r"C:\Program Files\Meta Quest Developer Hub\resources\bin\adb.exe",
        str(Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe"),
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which("adb")


def _run(adb: str, args: list[str], timeout: float = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(
            [adb, *args], capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        return -1, str(e)


def _devices(adb: str) -> list[dict]:
    _, out = _run(adb, ["devices"])
    result = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        dev_id, state = line.split("\t", 1)
        result.append({"id": dev_id.strip(), "state": state.strip()})
    return result


def _reverse_list(adb: str) -> str:
    _, out = _run(adb, ["reverse", "--list"])
    return out


def _set_reverse(adb: str, port: int) -> tuple[bool, str]:
    code, out = _run(adb, ["reverse", f"tcp:{port}", f"tcp:{port}"])
    return code == 0, out


def _app_running(adb: str, pkg: str) -> bool:
    _, out = _run(adb, ["shell", "pidof", pkg])
    return bool(out.strip())


def _app_installed(adb: str, pkg: str) -> bool:
    _, out = _run(adb, ["shell", "pm", "list", "packages", pkg])
    return pkg in out


def _launch(adb: str, pkg: str) -> bool:
    code, _ = _run(
        adb, ["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
    )
    return code == 0


def status(port: int, pkg: str) -> dict:
    """当前头显 USB 连接状态（网页轮询用）。"""
    adb = find_adb()
    if not adb:
        return {"adb_found": False, "error": "找不到 adb，请设置环境变量 ADB_PATH 指向 adb.exe"}
    devs = _devices(adb)
    online = [d for d in devs if d["state"] == "device"]
    unauthorized = [d for d in devs if d["state"] == "unauthorized"]
    dev = online[0]["id"] if online else None
    reverse_ok = f"tcp:{port}" in _reverse_list(adb)
    return {
        "adb_found": True,
        "device_connected": bool(online),
        "device_id": dev,
        "unauthorized": bool(unauthorized),
        "reverse_ok": reverse_ok,
        "app_installed": _app_installed(adb, pkg) if online else False,
        "app_running": _app_running(adb, pkg) if online else False,
    }


def connect(port: int, pkg: str, launch: bool = True) -> dict:
    """建立 USB 反向隧道（+可选启动应用）。网页「连接头显」按钮调用。"""
    adb = find_adb()
    if not adb:
        return {"ok": False, "error": "找不到 adb，请设置环境变量 ADB_PATH 指向 adb.exe"}
    devs = _devices(adb)
    online = [d for d in devs if d["state"] == "device"]
    if not online:
        unauth = any(d["state"] == "unauthorized" for d in devs)
        msg = (
            "头显已连但未授权 USB 调试：戴上头显点「允许 USB 调试→始终允许」"
            if unauth else
            "未检测到头显：用数据线连接、开启开发者模式并授权 USB 调试（并确认没开安卓模拟器抢占 adb）"
        )
        return {"ok": False, "error": msg, "status": status(port, pkg)}

    ok, out = _set_reverse(adb, port)
    launched = False
    if ok and launch and not _app_running(adb, pkg):
        launched = _launch(adb, pkg)
    return {
        "ok": ok,
        "message": "USB 反向隧道已建立" if ok else f"建立隧道失败：{out}",
        "launched": launched,
        "status": status(port, pkg),
    }
