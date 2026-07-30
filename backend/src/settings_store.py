"""系统设置持久化：仓库根目录 conf.ini 的读写。

设置页在这里读/写；运行时（如 use_llm/deepseek.py）从这里取「实时」值，
改完即时生效、无需重启后端。各项初值取自 config.py（其本身读环境变量），
首次运行自动把默认值写出为 conf.ini。
"""
import configparser
import threading

from . import config

CONF_PATH = config.ROOT / "conf.ini"

# 设置结构：section -> {key: (default, cast)}。
# cast 用于读出时的类型转换、以及回写前的合法性校验（非法值抛 ValueError）。
_SCHEMA = {
    "deepseek": {
        "api_key": (config.DEEPSEEK_API_KEY, str),
        "base_url": (config.DEEPSEEK_BASE_URL, str),
        "model": (config.DEEPSEEK_MODEL, str),
        "timeout": (config.DEEPSEEK_TIMEOUT, float),
        "temperature": (config.DEEPSEEK_TEMPERATURE, float),
    },
    "postgres": {
        # 结构化连接参数；host 留空＝未启用。db_manager 会自动建库/建表。
        "host": (config.POSTGRES_HOST, str),
        "port": (config.POSTGRES_PORT, int),
        "user": (config.POSTGRES_USER, str),
        "password": (config.POSTGRES_PASSWORD, str),
        "database": (config.POSTGRES_DATABASE, str),
    },
    "webrtc": {
        # 头显视角点对点回传的 ICE 服务器。stun_urls 可用逗号分隔多个。
        # turn_url 留空＝只用 STUN（两端都在对称 NAT 后时会连不上）。
        "stun_urls": (config.STUN_URLS, str),
        "turn_url": (config.TURN_URL, str),
        "turn_username": (config.TURN_USERNAME, str),
        "turn_credential": (config.TURN_CREDENTIAL, str),
    },
}

_lock = threading.Lock()
# interpolation=None：禁用 % 插值，否则含 % 的密码/API key 读取时抛 InterpolationSyntaxError
_parser = configparser.ConfigParser(interpolation=None)
_loaded = False


def _cast_val(raw, default, cast):
    if cast is str:
        return raw
    if raw is None or raw == "":
        return cast(default)
    try:
        return cast(raw)
    except (ValueError, TypeError):
        return cast(default)


def _ensure_loaded():
    """惰性加载 conf.ini；缺失的 section/key 用默认补齐并回写（首次生成文件）。"""
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        if CONF_PATH.exists():
            _parser.read(CONF_PATH, encoding="utf-8")
        changed = not CONF_PATH.exists()
        for section, keys in _SCHEMA.items():
            if not _parser.has_section(section):
                _parser.add_section(section)
                changed = True
            for key, (default, _cast) in keys.items():
                if not _parser.has_option(section, key):
                    _parser.set(section, key, str(default))
                    changed = True
        if changed:
            _write_locked()
        _loaded = True


def _write_locked():
    with open(CONF_PATH, "w", encoding="utf-8") as f:
        _parser.write(f)


def get_section(section: str) -> dict:
    """返回某 section 的实时值（已类型转换）。未知 section 返回空 dict。"""
    _ensure_loaded()
    keys = _SCHEMA.get(section, {})
    out = {}
    for key, (default, cast) in keys.items():
        raw = _parser.get(section, key, fallback=str(default))
        out[key] = _cast_val(raw, default, cast)
    return out


def all_settings() -> dict:
    """返回全部设置：{section: {key: value}}。"""
    return {section: get_section(section) for section in _SCHEMA}


def update_section(section: str, values: dict) -> dict:
    """写入某 section 的部分/全部键，落盘 conf.ini，返回更新后的实时值。

    未知 section 抛 KeyError；值类型非法抛 ValueError（不落盘）。
    """
    if section not in _SCHEMA:
        raise KeyError(section)
    _ensure_loaded()
    with _lock:
        if not _parser.has_section(section):
            _parser.add_section(section)
        for key, (_default, cast) in _SCHEMA[section].items():
            if key not in values:
                continue
            v = values[key]
            if cast is not str:
                cast(v)  # 校验：非法即抛 ValueError
            _parser.set(section, key, str(v))
        _write_locked()
    return get_section(section)
