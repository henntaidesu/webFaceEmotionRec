"""用 adb 管理 Quest 头显（网页驱动，逻辑跑在后端）。

**adb 走公网，不走数据线。** 头显的 adbd 监听 config.ADB_TCPIP_PORT（10020），经路由器
端口映射暴露成 config.HEADSET_ADB_ADDRESS；后端 `adb connect` 上去就能跨网操作头显。
这样操作的人只要能打开网页——手边不需要数据线，也不需要和头显同网段。
（数据线那条老路仍然可用：address 传空串即可，插在**本服务器**上的设备。）

adb 在这里只干两件事：**把头显里的应用拉起来**、**报告头显在不在线**。
业务数据不走 adb —— Unity 应用直接连服务器的公网地址（见 Unity 侧 BackendConfig），
所以隧道断了也只影响「启动/状态」，不影响采集与出图。

一次性前提（头显插数据线时做一次，之后永久生效）：
    adb shell setprop persist.adb.tcp.port 10020   # 重启后依然监听
    adb tcpip 10020                                 # 本次立即生效
见 enable_tcpip()——网页在头显插着数据线时可一键完成。

坑记两条：
  * 同时可能有数据线设备和网络设备，所以每条命令都带 `-s <serial>` 指名道姓。
  * monkey / am start 命令送到就返回 0，应用没起来也报成功；只能靠 pidof 验证。
    而头显**摘下来时根本起不来**——Quest 会休眠、VR 运行时是停的。
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .. import config

# 启动应用后等它真正起进程的时长（秒）。Unity 应用起进程通常 1～3 秒；
# 失败时才会等满，所以给够余量。
_LAUNCH_POLL_SEC = 0.5
_LAUNCH_WAIT_SEC = 8.0
# 跨公网的 adb 往返比 USB 慢得多，超时给宽一点
_NET_TIMEOUT = 15.0


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


def _run(adb: str, args: list[str], timeout: float = _NET_TIMEOUT) -> tuple[int, str]:
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


def normalize_address(address: str) -> str:
    """把填的头显地址补成 adb 要的 host:port（默认 ADB_TCPIP_PORT）。空串原样返回。"""
    a = (address or "").strip()
    if not a:
        return ""
    for scheme in ("http://", "https://"):
        if a.startswith(scheme):
            a = a[len(scheme):]
    a = a.split("/", 1)[0]
    return a if ":" in a else f"{a}:{config.ADB_TCPIP_PORT}"


def _adb_connect(adb: str, address: str) -> tuple[bool, str]:
    """`adb connect <host:port>`。

    坑：连不上时 adb 也可能返回 0，真话写在输出里（"cannot connect" / "failed"），
    所以退出码和文本都得看。
    """
    code, out = _run(adb, ["connect", address])
    low = out.lower()
    ok = code == 0 and "connected to" in low and "cannot" not in low
    return ok, out


def _dev(serial: str | None) -> list[str]:
    """`-s <serial>` 前缀：网络设备和数据线设备可能同时在，必须指名道姓。"""
    return ["-s", serial] if serial else []


def _app_running(adb: str, pkg: str, serial: str | None = None) -> bool:
    _, out = _run(adb, [*_dev(serial), "shell", "pidof", pkg])
    return bool(out.strip())


def _app_installed(adb: str, pkg: str, serial: str | None = None) -> bool:
    _, out = _run(adb, [*_dev(serial), "shell", "pm", "list", "packages", pkg])
    return pkg in out


def _resolve_activity(adb: str, pkg: str, serial: str | None = None) -> str | None:
    """问系统这个包的启动 Activity（Unity 一般是 com.unity3d.player.UnityPlayerActivity）。

    返回 "pkg/activity" 形式，直接能喂给 am start -n。
    """
    code, out = _run(
        adb, [*_dev(serial), "shell", "cmd", "package", "resolve-activity", "--brief", pkg],
    )
    if code != 0:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(pkg + "/"):
            return line
    return None


def _wake(adb: str, serial: str | None = None) -> None:
    """摘下头显后 Quest 会睡死，睡着时 am start 静默失败——先把它叫醒再启动。"""
    _, out = _run(adb, [*_dev(serial), "shell", "dumpsys", "power"])
    if "mWakefulness=Awake" not in out:
        _run(adb, [*_dev(serial), "shell", "input", "keyevent", "KEYCODE_WAKEUP"])


def _launch(adb: str, pkg: str, serial: str | None = None) -> bool:
    """启动头显里的应用，并**确认它真的起来了**。

    不看退出码——monkey 和 am start 都是「命令送到就返回 0」，应用一个进程都没起
    也照样成功。只认 pidof：轮询到进程出现才算启动成功，否则如实报失败。
    """
    _wake(adb, serial)
    comp = _resolve_activity(adb, pkg, serial)
    if comp:
        _run(adb, [*_dev(serial), "shell", "am", "start", "-n", comp])
    else:
        # 解析不出 Activity 时退回 monkey（老路径），至少还有一次机会
        _run(adb, [*_dev(serial), "shell", "monkey", "-p", pkg,
                   "-c", "android.intent.category.LAUNCHER", "1"])

    deadline = time.monotonic() + _LAUNCH_WAIT_SEC
    while time.monotonic() < deadline:
        if _app_running(adb, pkg, serial):
            return True
        time.sleep(_LAUNCH_POLL_SEC)
    return False


def _pick_device(adb: str, address: str) -> tuple[list[dict], str | None]:
    """列设备并挑一台。填了 address 就优先用它，没连上先 adb connect 一次。"""
    devs = _devices(adb)
    if address:
        if not any(d["id"] == address and d["state"] == "device" for d in devs):
            _adb_connect(adb, address)
            devs = _devices(adb)
        for d in devs:
            if d["id"] == address and d["state"] == "device":
                return devs, address
    online = [d for d in devs if d["state"] == "device"]
    return devs, online[0]["id"] if online else None


def enable_tcpip(port: int | None = None) -> dict:
    """把**插在本机数据线上**的头显切到 TCP 调试，并设成重启后依然生效。

    这是启用公网 adb 的一次性前提，只能在有数据线时做。`adb tcpip` 本身重启就失效，
    所以同时写 persist.adb.tcp.port，让 adbd 每次开机都监听这个端口。
    """
    port = port or config.ADB_TCPIP_PORT
    adb = find_adb()
    if not adb:
        return {"ok": False, "error": "找不到 adb，请设置环境变量 ADB_PATH 指向 adb.exe"}
    usb = [d for d in _devices(adb) if d["state"] == "device" and ":" not in d["id"]]
    if not usb:
        return {"ok": False, "error": "本机没有数据线连着的头显——这一步必须插线做一次"}
    serial = usb[0]["id"]
    _run(adb, [*_dev(serial), "shell", "setprop", "persist.adb.tcp.port", str(port)])
    code, out = _run(adb, [*_dev(serial), "tcpip", str(port)])
    ok = code == 0 and "error" not in out.lower()
    return {
        "ok": ok,
        "port": port,
        "device_id": serial,
        "message": (
            f"头显 adbd 已监听 {port}（并已设为重启后保持）。"
            f"接下来在路由器上把公网 {port} 端口映射到头显内网 IP 即可。"
            if ok else f"切换失败：{out}"
        ),
    }


def status(port: int, pkg: str, address: str | None = None) -> dict:
    """当前头显连接状态（网页轮询用）。address 默认取 config.HEADSET_ADB_ADDRESS。"""
    adb = find_adb()
    if not adb:
        return {"adb_found": False, "error": "找不到 adb，请设置环境变量 ADB_PATH 指向 adb.exe"}
    address = normalize_address(
        config.HEADSET_ADB_ADDRESS if address is None else address
    )
    devs, serial = _pick_device(adb, address)
    return {
        "adb_found": True,
        "address": address,
        "device_connected": bool(serial),
        "device_id": serial,
        "over_network": bool(serial and ":" in serial),
        "unauthorized": any(d["state"] == "unauthorized" for d in devs),
        "app_installed": _app_installed(adb, pkg, serial) if serial else False,
        "app_running": _app_running(adb, pkg, serial) if serial else False,
    }


def connect(port: int, pkg: str, launch: bool = True, address: str | None = None) -> dict:
    """连上头显并把应用拉起来。网页「连接头显」按钮调用。

    port 保留只为签名兼容——业务数据不再走 adb 隧道，Unity 直连服务器公网地址。
    """
    adb = find_adb()
    if not adb:
        return {"ok": False, "error": "找不到 adb，请设置环境变量 ADB_PATH 指向 adb.exe"}

    address = normalize_address(
        config.HEADSET_ADB_ADDRESS if address is None else address
    )
    devs, serial = _pick_device(adb, address)
    if not serial:
        if any(d["state"] == "unauthorized" for d in devs):
            msg = "头显已连上但没授权调试：戴上头显点「允许 USB 调试 → 始终允许」"
        elif address:
            msg = (
                f"连不上 {address}：确认头显开着且联网、公网端口已映射到头显，"
                f"并且头显的 adbd 监听在这个端口（插线执行一次 adb tcpip "
                f"{config.ADB_TCPIP_PORT}，或用「启用无线调试」按钮）"
            )
        else:
            msg = "未检测到头显：本机没有数据线连着的设备，也没填公网 adb 地址"
        return {"ok": False, "error": msg, "status": status(port, pkg, address)}

    launched, launch_error = False, ""
    if launch:
        if _app_running(adb, pkg, serial):
            launched = True
        elif not _app_installed(adb, pkg, serial):
            launch_error = f"头显里没装应用（{pkg}），请先用 Unity 打包安装"
        else:
            launched = _launch(adb, pkg, serial)
            if not launched:
                launch_error = (
                    "应用没能自动启动：请先戴上头显再点连接"
                    "（摘下时 Quest 会休眠、VR 运行时是停的，任何方式都拉不起 VR 应用）"
                )

    message = f"已连上头显 {serial}"
    if launched:
        message += "，应用已启动"
    elif launch_error:
        message += f"；{launch_error}"
    return {
        "ok": True,
        "message": message,
        "launched": launched,
        "launch_error": launch_error,
        "status": status(port, pkg, address),
    }
