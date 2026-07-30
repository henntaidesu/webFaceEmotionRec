"""网页登录：口令校验 + 无状态会话 Cookie。

服务已经开在公网上，训练/评测/删模型/系统设置这些接口不能谁都能调。这里只做
最小的一层：conf.ini `[auth]` 配一个用户名口令，登录后种一个签名 Cookie，
后端对「网页用」的接口一律要求带上它。

会话是**无状态**的：token = `<过期时间戳>.<HMAC 签名>`，签名密钥直接由用户名+
口令派生。所以后端重启不会把人踢下线，而改口令会让所有已发出的会话立刻失效。

两点必须清楚：

* **站点是 http 明文**，口令和 Cookie 在链路上都没加密。这挡的是顺手点进来的
  人，不是能抓包的攻击者。要真防住得上 HTTPS。
* **头显要用的接口全部放行**（见 _PUBLIC_EXACT）。Unity 那边不会带 Cookie，
  要它带就得改五个脚本 + 重打包重装头显应用——采集期间不划算。代价是这些接口
  仍然裸露在公网上（FEA 上传、会话上传、刺激控制读写、自评、WebRTC 信令）。
"""
import hashlib
import hmac
import time

from .. import config
from .. import settings_store

COOKIE_NAME = "wfer_session"
SESSION_MAX_AGE = int(config.AUTH_SESSION_DAYS * 86400)

# 放行清单：(方法, 路径)。方法要分开写——例如刺激图 GET 是头显在拉图，
# 同一路径的 DELETE 是网页在删图，后者必须拦住。
_PUBLIC_EXACT = frozenset({
    ("GET", "/health"),
    # 头显 Unity 应用（Assets/Scripts/*.cs）用到的全部接口
    ("GET", "/api/stimulus/current"),    # VREmotionSelectionUI：轮询当前刺激图
    ("GET", "/api/stimulus/options"),    # VRStimulusControlPanel：选项表
    ("GET", "/api/stimulus/control"),    # 同上，每秒一次，兼作在线心跳
    ("POST", "/api/stimulus/control"),   # 同上，头显里改参数
    ("GET", "/api/stimulus/images"),     # VRSessionCollector：拉全景图列表
    ("POST", "/api/fea"),                # QuestProFaceCapture：推 63 维 FEA
    ("POST", "/api/session/start"),      # SessionUploader
    ("POST", "/api/session/ingest"),
    ("POST", "/api/session/stop"),
    ("POST", "/api/affect/selfreport"),  # VREmotionSelectionUI：头显里的情绪自评
    ("GET", "/api/headset/rtc/config"),  # HeadsetViewStreamer：头显侧 WebRTC 信令
    ("GET", "/api/headset/rtc/watch"),
    ("POST", "/api/headset/rtc/offer"),
    ("GET", "/api/headset/rtc/answer"),
})

# 前缀放行：刺激图静态文件（头显要下载图本身）、登录接口自身。
_PUBLIC_PREFIXES = ("/api/stimulus/files/", "/api/auth/")


def _conf() -> dict:
    """conf.ini [auth] 的实时值（改完不用重启）。"""
    return settings_store.get_section("auth")


def is_enabled() -> bool:
    """口令留空＝不启用登录，全部接口照旧放行。"""
    return bool(_conf()["password"])


def is_public(method: str, path: str) -> bool:
    if method == "OPTIONS":          # CORS 预检不带 Cookie，拦了没意义
        return True
    if path.startswith(_PUBLIC_PREFIXES):
        return True
    return (method, path) in _PUBLIC_EXACT


def _key() -> bytes:
    c = _conf()
    return hashlib.sha256(f"{c['username']}:{c['password']}".encode("utf-8")).digest()


def _sign(exp: int) -> str:
    return hmac.new(_key(), str(exp).encode("utf-8"), hashlib.sha256).hexdigest()


def issue_token() -> str:
    exp = int(time.time()) + SESSION_MAX_AGE
    return f"{exp}.{_sign(exp)}"


def check_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp_str, sig = token.split(".", 1)
    try:
        exp = int(exp_str)
    except ValueError:
        return False
    if exp < time.time():
        return False
    return hmac.compare_digest(sig, _sign(exp))


def verify(username, password) -> bool:
    """用户名口令是否正确（等时比较，避免逐字符试探）。"""
    c = _conf()
    ok_user = hmac.compare_digest(
        str(username or "").encode("utf-8"), c["username"].encode("utf-8"))
    ok_pass = hmac.compare_digest(
        str(password or "").encode("utf-8"), c["password"].encode("utf-8"))
    return ok_user and ok_pass
