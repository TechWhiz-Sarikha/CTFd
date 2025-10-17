import configparser
import json
import os
from distutils.util import strtobool
from typing import Union
from sqlalchemy.engine.url import URL

_FORCED_EXTRA_CONFIG_TYPES = {}

class EnvInterpolation(configparser.BasicInterpolation):
    """Interpolation which expands environment variables in values."""
    def before_get(self, parser, section, option, value, defaults):
        value = super().before_get(parser, section, option, value, defaults)
        envvar = os.getenv(option)
        if value == "" and envvar:
            return process_string_var(envvar, key=option)
        else:
            return value

def process_string_var(value, key=None):
    if key in _FORCED_EXTRA_CONFIG_TYPES:
        t = _FORCED_EXTRA_CONFIG_TYPES[key]
        if t == "str":
            return str(value)
        elif t == "int":
            return int(value)
        elif t == "float":
            return float(value)
        elif t == "bool":
            return bool(strtobool(value))

    if value == "":
        return None

    if value.isdigit():
        return int(value)
    elif value.replace(".", "", 1).isdigit():
        return float(value)

    try:
        return bool(strtobool(value))
    except ValueError:
        return value

def process_boolean_str(value):
    if type(value) is bool:
        return value
    if value is None:
        return False
    if value == "":
        return None
    return bool(strtobool(value))

def empty_str_cast(value, default=None):
    if value == "":
        return default
    return value

def gen_secret_key():
    try:
        with open(".ctfd_secret_key", "rb") as secret:
            key = secret.read()
    except OSError:
        key = None

    if not key:
        key = os.urandom(64)
        try:
            with open(".ctfd_secret_key", "wb") as secret:
                secret.write(key)
                secret.flush()
        except OSError:
            pass
    return key

# Load config.ini
config_ini = configparser.ConfigParser(interpolation=EnvInterpolation())
config_ini.optionxform = str
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
config_ini.read(path)

class ServerConfig(object):
    SECRET_KEY: str = empty_str_cast(config_ini["server"]["SECRET_KEY"]) or gen_secret_key()

    DATABASE_URL: str = empty_str_cast(config_ini["server"]["DATABASE_URL"])
    if not DATABASE_URL:
        if empty_str_cast(config_ini["server"]["DATABASE_HOST"]) is not None:
            DATABASE_URL = str(URL(
                drivername=empty_str_cast(config_ini["server"]["DATABASE_PROTOCOL"]) or "mysql+pymysql",
                username=empty_str_cast(config_ini["server"]["DATABASE_USER"]) or "ctfd",
                password=empty_str_cast(config_ini["server"]["DATABASE_PASSWORD"]),
                host=empty_str_cast(config_ini["server"]["DATABASE_HOST"]),
                port=empty_str_cast(config_ini["server"]["DATABASE_PORT"]),
                database=empty_str_cast(config_ini["server"]["DATABASE_NAME"]) or "ctfd",
            ))
        else:
            DATABASE_URL = f"sqlite:///{os.path.dirname(os.path.abspath(__file__))}/ctfd.db"

    REDIS_URL: str = empty_str_cast(config_ini["server"]["REDIS_URL"])
    REDIS_HOST: str = empty_str_cast(config_ini["server"]["REDIS_HOST"])
    REDIS_PROTOCOL: str = empty_str_cast(config_ini["server"]["REDIS_PROTOCOL"]) or "redis"
    REDIS_USER: str = empty_str_cast(config_ini["server"]["REDIS_USER"])
    REDIS_PASSWORD: str = empty_str_cast(config_ini["server"]["REDIS_PASSWORD"])
    REDIS_PORT: int = empty_str_cast(config_ini["server"]["REDIS_PORT"]) or 6379
    REDIS_DB: int = empty_str_cast(config_ini["server"]["REDIS_DB"]) or 0

    if REDIS_URL or REDIS_HOST is None:
        CACHE_REDIS_URL = REDIS_URL
    else:
        CACHE_REDIS_URL = f"{REDIS_PROTOCOL}://"
        if REDIS_USER:
            CACHE_REDIS_URL += REDIS_USER
        if REDIS_PASSWORD:
            CACHE_REDIS_URL += f":{REDIS_PASSWORD}"
        CACHE_REDIS_URL += f"@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    if CACHE_REDIS_URL:
        CACHE_TYPE: str = "redis"
    else:
        CACHE_TYPE: str = "filesystem"
        CACHE_DIR: str = os.path.join(os.path.dirname(__file__), os.pardir, ".data", "filesystem_cache")
        CACHE_THRESHOLD: int = 0

    # === SECURITY ===
    SESSION_COOKIE_HTTPONLY: bool = config_ini["security"].getboolean("SESSION_COOKIE_HTTPONLY", fallback=True)
    SESSION_COOKIE_SAMESITE: str = empty_str_cast(config_ini["security"]["SESSION_COOKIE_SAMESITE"]) or "Lax"
    PERMANENT_SESSION_LIFETIME: int = config_ini["security"].getint("PERMANENT_SESSION_LIFETIME") or 604800
    CROSS_ORIGIN_OPENER_POLICY: str = empty_str_cast(config_ini["security"].get("CROSS_ORIGIN_OPENER_POLICY")) or "same-origin-allow-popups"

    TRUSTED_HOSTS: list[str] = []
    if config_ini["security"].get("TRUSTED_HOSTS"):
        TRUSTED_HOSTS = [h.strip() for h in empty_str_cast(config_ini["security"].get("TRUSTED_HOSTS")).split(",")]

    TRUSTED_PROXIES = [
        r"^127\.0\.0\.1$", r"^::1$", r"^fc00:", r"^10\.", r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", r"^192\.168\.",
    ]

    # === OPTIONAL ===
    REVERSE_PROXY: Union[str, bool] = empty_str_cast(config_ini["optional"].get("REVERSE_PROXY"), default=True)
    FORCE_HTTPS: bool = process_boolean_str(empty_str_cast(config_ini["optional"].get("FORCE_HTTPS"), default=True))
    APPLICATION_ROOT: str = empty_str_cast(config_ini["optional"].get("APPLICATION_ROOT"), default="/")

    TEMPLATES_AUTO_RELOAD: bool = process_boolean_str(empty_str_cast(config_ini["optional"].get("TEMPLATES_AUTO_RELOAD"), default=True))
    THEME_FALLBACK: bool = process_boolean_str(empty_str_cast(config_ini["optional"].get("THEME_FALLBACK"), default=True))
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = process_boolean_str(empty_str_cast(config_ini["optional"].get("SQLALCHEMY_TRACK_MODIFICATIONS"), default=False))
    UPDATE_CHECK: bool = process_boolean_str(empty_str_cast(config_ini["optional"].get("UPDATE_CHECK"), default=True))

# Actually initialize ServerConfig
Config = ServerConfig()
for k, v in config_ini.items("extra"):
    if hasattr(Config, k):
        raise ValueError(f"Built-in Config {k} should not be defined in [extra] section")
    setattr(Config, k, v)
