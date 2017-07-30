# coding=utf-8
import configparser
# redis is a conditional import
import logging
import os
import importlib
# yaml is a conditional import
# json is a conditional import
from discord import Member
from .utils import Singleton, decode, decode_auto, bin2bool

__author__ = "DefaltSimon"

# Server handler for Nano

parser = configparser.ConfigParser()
parser.read("plugins/config.ini")

par = configparser.ConfigParser()
par.read("settings.ini")

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# CONSTANTS

MAX_INPUT_LENGTH = 800

server_defaults = {
    "name": "",
    "owner": "",
    "filterwords": False,
    "filterspam": False,
    "filterinvite": False,
    "sleeping": False,
    "welcomemsg": "Welcome to :server, :user!",
    "kickmsg": "**:user** has been kicked.",
    "banmsg": "**:user** has been banned.",
    "leavemsg": "**:user** has left the server :cry:",
    "logchannel": None,
    "prefix": str(parser.get("Servers", "defaultprefix")),
    "dchan": None,
    "lang": "en",
}

# Utility for input validation


def validate_input(fn):
    def wrapper(self, *args, **kwargs):
        for arg in args:
            if len(str(arg)) > MAX_INPUT_LENGTH:
                return False

        for k, v in kwargs.items():
            if (len(str(k)) > MAX_INPUT_LENGTH) or (len(str(v)) > MAX_INPUT_LENGTH):
                return False

        # If no filters need to be applied, do everything normally
        return fn(self, *args, **kwargs)

    return wrapper

# (Redis)ServerHandler is a singleton, --> only one instance
# Singleton imported from utils


class ServerHandler:
    def __init__(self):
        pass

    @staticmethod
    def get_redis_credentials():
        setup_type = 1 if par.get("Redis", "setup") == "openshift" else 2

        if setup_type == 1:
            redis_ip = os.environ["OPENSHIFT_REDIS_HOST"]
            redis_port = os.environ["OPENSHIFT_REDIS_PORT"]
            redis_pass = os.environ["REDIS_PASSWORD"]

        else:
            redis_ip = par.get("Redis", "ip")
            redis_port = par.get("Redis", "port")
            redis_pass = par.get("Redis", "password")

            # Fallback to defaults
            if not redis_ip:
                redis_ip = "localhost"
            if not redis_port:
                redis_port = 6379
            if not redis_pass:
                redis_pass = None

        return redis_ip, redis_port, redis_pass

    @classmethod
    def get_handler(cls, legacy=False):
        # Factory method
        if legacy:
            raise NotImplementedError
        else:
            redis_ip, redis_port, redis_pass = cls.get_redis_credentials()
            return RedisServerHandler(redis_ip, redis_port, redis_pass)

    # Permission checker
    def has_role(self, user, server, role_name):
        if not isinstance(user, Member):
            return False

        for role in user.roles:
            if role.name == role_name:
                return True

        return False

    def can_use_admin_commands(self, user, server):
        bo = self.is_bot_owner(user.id)
        so = self.is_server_owner(user.id, server)
        ia = self.is_admin(user, server)

        return bo or so or ia

    @staticmethod
    def is_bot_owner(uid):
        return str(uid) == str(par.get("Settings", "ownerid"))

    @staticmethod
    def is_server_owner(uid, server):
        return str(uid) == str(server.owner.id)

    def is_admin(self, user, server):
        return self.has_role(user, server, "Nano Admin")

    def is_mod(self, user, server):
        bo = self.is_bot_owner(user.id)
        so = self.is_server_owner(user.id, server)
        ia = self.has_role(user, server, "Nano Mod")

        return bo or so or ia


# Everything regarding RedisServerHandler below
# Careful when converting data, this was changed (see converter.py for implementation)
WORDFILTER_SETTING = "wordfilter"
SPAMFILTER_SETTING = "spamfilter"
INVITEFILTER_SETTING = "invitefilter"

mod_settings_map = {
    "word filter": WORDFILTER_SETTING,
    "filter words": WORDFILTER_SETTING,
    "wordfilter": WORDFILTER_SETTING,

    "spam filter": SPAMFILTER_SETTING,
    "filter spam": SPAMFILTER_SETTING,
    "spamfilter": SPAMFILTER_SETTING,

    "invite filter": INVITEFILTER_SETTING,
    "filterinvite": INVITEFILTER_SETTING,
    "filterinvites": INVITEFILTER_SETTING,
}

# IMPORTANT
# The format for saving server data is => server:id_here
# For commands => commands:id_here
# For mutes => mutes:id_here
# For blacklist => blacklist:id_here
# For the selfroles => sr:


class RedisServerHandler(ServerHandler, metaclass=Singleton):
    __slots__ = ("_redis", "redis", "pool")

    def __init__(self, redis_ip, redis_port, redis_password):
        super().__init__()

        self._redis = importlib.import_module("redis")

        self.pool = self._redis.ConnectionPool(host=redis_ip, port=redis_port, password=redis_password, db=0)
        log.info("Redis ConnectionPool created")

        self.redis = self._redis.StrictRedis(connection_pool=self.pool)

        try:
            self.redis.ping()
        except self._redis.ConnectionError:
            log.critical("Could not connect to Redis db!")
            return

        log.info("Connected to Redis database")

    def bg_save(self):
        return bool(self.redis.bgsave() == b"OK")

    def server_setup(self, server, **_):
        # These are server defaults
        s_data = server_defaults.copy()
        s_data["owner"] = server.owner.id
        s_data["name"] = server.name

        sid = "server:{}".format(server.id)

        self.redis.hmset(sid, s_data)
        # commands:id, mutes:id and blacklist:id are created automatically when needed

        log.info("New server: {}".format(server.name))

    def server_exists(self, server_id):
        return bool(decode(self.redis.exists("server:{}".format(server_id))))

    def check_server(self, server):
        # shortcut for checking sever existence
        if not self.server_exists(server.id):
            self.server_setup(server)

    def get_server_data(self, server):
        # Special: HGETALL returns a dict with binary keys and values!
        base = decode(self.redis.hgetall("server:{}".format(server.id)))
        cmd_list = self.get_custom_commands(server)
        bl = self.get_blacklists(server)
        mutes = self.get_mute_list(server)

        data = decode(base)
        data["commands"] = cmd_list
        data["blacklist"] = bl
        data["mutes"] = mutes

        return data

    def get_var(self, server_id, key):
        # If value is in json, it will be a json-encoded string and not parsed
        return decode(self.redis.hget("server:{}".format(server_id), key))

    @validate_input
    def update_var(self, server_id, key, value):
        self.redis.hset("server:{}".format(server_id), key, value)

    @validate_input
    def update_moderation_settings(self, server, key, value):
        if not mod_settings_map.get(key):
            return False

        return decode(self.redis.hset("server:{}".format(server.id), mod_settings_map.get(key), value))

    def check_server_vars(self, server):
        try:
            serv = "server:{}".format(server.id)

            if decode(self.redis.hget(serv, "owner")) != str(server.owner.id):
                self.redis.hset(serv, "owner", server.owner.id)

            if decode(self.redis.hget(serv, "name")) != str(server.name):
                self.redis.hset(serv, "name", server.name)
        except AttributeError:
            pass

    def delete_server_by_list(self, current_servers):
        servers = ["server:{}".format(name) for name in current_servers]

        server_list = [decode_auto(a) for a in self.redis.scan(0, match="server:*")[1]]

        for server in servers:
            try:
                server_list.remove(server)
            except ValueError:
                pass

        if server_list:
            for rem_serv in server_list:
                self.delete_server(rem_serv)

            log.info("Removed {} old servers.".format(len(server_list)))

    def delete_server(self, server_id):
        self.redis.delete("commands:{}".format(server_id))
        self.redis.delete("blacklist:{}".format(server_id))
        self.redis.delete("mutes:{}".format(server_id))

        return self.redis.delete("server:{}".format(server_id))

    @validate_input
    def set_command(self, server, trigger, response):
        serv = "commands:{}".format(server.id)

        if len(trigger) > 80:
            return False

        self.redis.hset(serv, trigger, response)
        return True

    def remove_command(self, server, trigger):
        serv = "commands:{}".format(server.id)

        # if decode(self.redis.hexists(serv, trigger)):
        #     self.redis.hdel(serv, trigger)
        #     return True
        #
        # else:
        #     return False

        return bin2bool(decode_auto(self.redis.hdel(serv, trigger)))

    def get_custom_commands(self, server_id):
        return decode(self.redis.hgetall("commands:{}".format(server_id)))

    def get_command_amount(self, server_id):
        return decode(self.redis.hlen("commands:{}".format(server_id)))

    def custom_command_exists(self, server_id, trigger):
        return decode(self.redis.hexists("commands:{}".format(server_id), trigger))

    @validate_input
    def add_channel_blacklist(self, server_id, channel_id):
        serv = "blacklist:{}".format(server_id)
        return bool(self.redis.sadd(serv, channel_id))

    @validate_input
    def remove_channel_blacklist(self, server_id, channel_id):
        serv = "blacklist:{}".format(server_id)
        return bool(self.redis.srem(serv, channel_id))

    def is_blacklisted(self, server_id, channel_id):
        serv = "blacklist:{}".format(server_id)
        return bin2bool(self.redis.sismember(serv, channel_id))

    def get_blacklists(self, server_id):
        serv = "blacklist:{}".format(server_id)
        return list(decode(self.redis.smembers(serv)) or [])

    def get_prefix(self, server):
        return decode(self.redis.hget("server:{}".format(server.id), "prefix"))

    @validate_input
    def change_prefix(self, server, prefix):
        self.check_server(server)

        self.redis.hset("server:{}".format(server.id), "prefix", prefix)

    def has_spam_filter(self, server):
        return decode(self.redis.hget("server:{}".format(server.id), SPAMFILTER_SETTING)) is True

    def has_word_filter(self, server):
        return decode(self.redis.hget("server:{}".format(server.id), WORDFILTER_SETTING)) is True

    def has_invite_filter(self, server):
        return decode(self.redis.hget("server:{}".format(server.id), INVITEFILTER_SETTING)) is True

    def get_log_channel(self, server):
        return decode(self.redis.hget("server:{}".format(server.id), "logchannel"))

    def is_sleeping(self, server):
        return decode(self.redis.hget("server:{}".format(server.id), "sleeping"))

    @validate_input
    def set_sleeping(self, server, var):
        self.redis.hset("server:{}".format(server.id), "sleeping", bool(var))

    @validate_input
    def mute(self, server, user_id):
        serv = "mutes:{}".format(server.id)
        return bool(self.redis.sadd(serv, user_id))

    @validate_input
    def unmute(self, member_id, server_id):
        serv = "mutes:{}".format(server_id)
        return bool(self.redis.srem(serv, member_id))

    def is_muted(self, server, user_id):
        serv = "mutes:{}".format(server.id, user_id)
        return bool(self.redis.sismember(serv, user_id))

    def get_mute_list(self, server):
        serv = "mutes:{}".format(server.id)
        return list(decode(self.redis.smembers(serv)) or [])

    def get_defaultchannel(self, server):
        return decode(self.redis.hget("server:{}".format(server.id), "dchan"))

    def set_defaultchannel(self, server, channel_id):
        self.redis.hset("server:{}".format(server.id), "dchan", channel_id)

    def set_lang(self, server_id, language):
        self.redis.hset("server:{}".format(server_id), "lang", language)

    def get_lang(self, server_id):
        return decode(self.redis.hget("server:{}".format(server_id), "lang"))

    @validate_input
    def remove_server(self, server_id):
        # Not used
        s = bin2bool(self.redis.delete("server:{}".format(server_id)))
        c = bin2bool(self.redis.delete("commands:{}".format(server_id)))
        m = bin2bool(self.redis.delete("mutes:{}".format(server_id)))
        b = bin2bool(self.redis.delete("blacklist:{}".format(server_id)))

        return s and c and m and b

    def get_selfroles(self, server_id):
        return decode(self.redis.smembers("sr:{}".format(server_id)))

    def add_selfrole(self, server_id, role_name):
        return bin2bool(self.redis.sadd("sr:{}".format(server_id), role_name))

    def remove_selfrole(self, server_id, role_name):
        return bin2bool(self.redis.srem("sr:{}".format(server_id), role_name))

    def is_selfrole(self, server_id, role_name):
        return bin2bool(self.redis.sismember("sr:{}".format(server_id), role_name))

    # Special debug methods
    def db_info(self, section=None):
        return decode_auto(self.redis.info(section=section))

    def db_size(self):
        return int(self.redis.dbsize())

    # Plugin storage system
    def get_plugin_data_manager(self, namespace, *args, **kwargs):
        return RedisPluginDataManager(self._redis, self.pool, namespace, *args, **kwargs)


class RedisPluginDataManager:
    def __init__(self, _redis, pool, namespace, *_, **__):
        self.namespace = str(namespace)
        self.redis = _redis.StrictRedis(connection_pool=pool)

        log.info("New plugin namespace registered: {}".format(self.namespace))

    def _make_key(self, name):
        # Returns a hash name formatted with the namespace
        return "{}:{}".format(self.namespace, name)

    def set(self, key, val):
        return decode(self.redis.set(self._make_key(key), val))

    def get(self, key):
        return decode(self.redis.get(self._make_key(key)))

    def hget(self, name, field):
        return decode(self.redis.hget(self._make_key(name), field))

    def hgetall(self, name):
        return decode(self.redis.hgetall(self._make_key(name)))

    def hdel(self, name, field):
        return decode(self.redis.hdel(self._make_key(name), field))

    def hmset(self, name, payload):
        return decode(self.redis.hmset(self._make_key(name), payload))

    def hset(self, name, field, value):
        return decode(self.redis.hset(self._make_key(name), field, value))

    def exists(self, name):
        return bool(decode(self.redis.exists(self._make_key(name))))

    def delete(self, name):
        return bool(decode(self.redis.delete(self._make_key(name))))

    def scan_iter(self, match, use_namespace=True):
        match = self._make_key(match) if use_namespace else match
        return [a for a in self.redis.scan_iter(match)]

    def lpush(self, key, value):
        return decode(self.redis.lpush(self._make_key(key), value))

    def lrange(self, key, from_key=0, to_key=-1):
        return decode(self.redis.lrange(self._make_key(key), from_key, to_key))

    def lrem(self, key, value, count=1):
        return decode(self.redis.lrem(key, count, value))

    def lpop(self, key, index):
        return decode(self.redis.lpop(key, index))
