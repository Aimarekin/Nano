# coding=utf-8
import asyncio
import importlib
import logging
import time
import traceback

from typing import Union
from discord import DiscordException

from data.stats import MESSAGE, WRONG_ARG
from data.utils import resolve_time, convert_to_seconds, is_valid_command, gen_id, IgnoredException, log_to_file

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# CONSTANTS

DEFAULT_REMINDER_LIMIT = 2
TICK_DURATION = 15

REM_MIN_DURATION = 5
REM_MAX_DURATION = 172800

REM_MAX_CONTENT = 800

REM_MAX_DAYS = int(REM_MAX_DURATION / 86400)

REMINDER_PERSONAL = "personal"
REMINDER_CHANNEL = "channel"

commands = {
    "_remind": {"desc": "General module for timers\nSubcommands: remind me in, remind here in, remind list, remind remove", "use": None, "alias": None},
    "_remind me in": {"desc": "Adds a reminder (reminds you in dm)", "use": "[command] [time (ex: 3h 5min)] : [message] OR  [command] [time] to [message]", "alias": None},
    "_remind here in": {"desc": "Adds a reminder (reminds everybody in current channel)", "use": "[command] [time (ex: 3h 5min)] : [message] OR  [command] [time] to [message]", "alias": None},
    "_remind list": {"desc": "Displays all ongoing timers.", "use": None, "alias": "_reminder list"},
    "_reminder list": {"desc": "Displays all ongoing timers.", "use": None, "alias": "_remind list"},
    "_remind help": {"desc": "Displays help for reminders.", "use": None, "alias": None},
    "_remind remove": {"desc": "Removes a timer with supplied description or time (or all timers with 'all')", "use": "[command] [timer description or time in sec]", "alias": None},
}

valid_commands = commands.keys()

class RedisReminderHandler:
    """
    Data type: Hash

    reminder:<USER_ID>:<REM_ID> =>

                    Values:
                            content: Formatted content to send
                            receiver: User/Channel id
                            time_created: unix epoch time
                            time_target: time_created + full_time
                            author: author id
                            raw: raw content

    """
    def __init__(self, client, handler, trans, loop=asyncio.get_event_loop()):
        self.redis = handler.get_plugin_data_manager(namespace="reminder")

        self.loop = loop
        self.client = client
        self.trans = trans

        try:
            self.json = importlib.import_module("ujson")
        except ImportError:
            self.json = importlib.import_module("json")

    def get_reminder_amount(self):
        return len(self.get_all_reminders())

    def prepare_private(self, content, lang):
        return self.trans.get("MSG_REMINDER_PRIVATE", lang).format(content)

    def prepare_channel(self, content, lang):
        return self.trans.get("MSG_REMINDER_CHANNEL", lang).format(content)

    def get_reminders(self, user_id) -> dict:
        keys = [a for a in self.redis.scan_iter("{}:*".format(user_id))]

        if not keys:
            return {}

        reminders = {}
        for r in keys:
            r_id = int(r.rsplit(":", maxsplit=1)[1])
            reminders[r_id] = self.redis.hgetall(r, use_namespace=False)

        return reminders

    @staticmethod
    def _extract_user_id(key_name: str):
        # Dirty but fast
        # How it works:
        # Example: "reminder:DefaltSimon:328742938"
        # Splits by the first and last : and returns the middle
        # Safe even if user has : in his/her name

        return key_name.split(":", maxsplit=1)[1].rsplit(":", maxsplit=1)[0]

    def get_all_reminders(self):
        # Not actually *, but reminder:*, due to how plugin manager works
        return [self.get_reminders(self._extract_user_id(k)) for k in self.redis.scan_iter("*")]

    def find_id_from_content(self, user_id, content):
        reminders = self.get_reminders(user_id)

        for r_id, rem in reminders.items():
            if rem["raw"] == content:
                return r_id

        return None

    def remove_all_reminders(self, user):
        self.redis.delete(user.id)

    def remove_reminder(self, user_id, rem_id):
        return self.redis.delete("{}:{}".format(user_id, rem_id))

    def check_reminders(self, user):
        """
        :param user: User or Member
        :return: True -> user can add more reminders
        """
        if self.redis.exists(user.id):
            return len(self.get_reminders(user.id)) <= DEFAULT_REMINDER_LIMIT

        else:
            return True

    def set_reminder(self, channel, author, content: str, tim: int,
                     lang: str, reminder_type: Union[REMINDER_CHANNEL, REMINDER_PERSONAL]=REMINDER_PERSONAL):
        """
        Sets a reminder
        :param channel: Where to send this
        :param author: Who is the author
        :param content: String : message
        :param tim: time (int)
        :param reminder_type: type of reminder (personal (DM) or channel)
        :param lang: language used in that guild
        :return: bool indicating success
        """
        t = time.time()

        if not self.check_reminders(author):
            return -1

        tim = convert_to_seconds(tim)
        if not (REM_MIN_DURATION <= tim < REM_MAX_DURATION):  # Allowed reminder duration: 5 sec to 2 days
            return False

        raw = str(content)
        # Add the reminder to the list
        rm_id = gen_id(length=12)


        if reminder_type == REMINDER_PERSONAL:
            tree = {"receiver": author.id, "time_created": int(t), "author": author.id,
                    "lang": lang, "time_target": int(tim + t), "raw": raw, "type": reminder_type}

        else:
            tree = {"receiver": channel.id, "server": channel.guild.id, "author": author.id, "lang": lang,
                    "time_created": int(t), "time_target": int(tim + t), "raw": raw, "type": reminder_type}


        log.info("New reminder by {}".format(author.id))
        hash_name = "{}:{}".format(author.id, rm_id)

        return self.redis.hmset(hash_name, tree)

    @staticmethod
    async def tick(last_time):
        """
        Very simple implementation of a self-correcting tick system
        :return: None
        """
        current_time = time.time()
        delta = TICK_DURATION - (current_time - last_time)

        # If previous loop took more than TICK_DURATION, do one right away
        if delta <= 0:
            return time.time()

        await asyncio.sleep(delta)

        return time.time()

    async def dispatch(self, rem):
        try:
            rem_type = rem["type"]

            if rem_type == REMINDER_CHANNEL:
                log.info("Dispatching channel reminder by {}".format(rem["receiver"]))

                guild = self.client.get_guild(int(rem["server"]))
                channel = guild.get_channel(int(rem["receiver"]))

                content = self.prepare_channel(rem["raw"], rem["lang"])
                await channel.send(content)

            # Private reminder.
            else:
                log.info("Dispatching personal reminder by {}".format(rem["receiver"]))

                user = self.client.get_user(int(rem["receiver"]))

                if not user:
                    log.info("User missing, ignoring...")
                    return

                content = self.prepare_private(rem["raw"], rem["lang"])
                await user.send(content)


        except DiscordException as e:
            log.warning(e)

    async def start_monitoring(self):
        await self.client.wait_until_ready()

        last_time = time.time()

        while True:
            # Iterate through users and their reminders
            for user in self.get_all_reminders():

                for rm_id, reminder in user.items():
                    # If enough time has passed, send the reminder
                    if int(reminder["time_target"]) <= last_time:

                        try:
                            await self.dispatch(reminder)
                        except Exception:
                            log.warning("ERROR in reminders, see bugs.txt")
                            log_to_file(traceback.format_exc(), "bug")

                            self.remove_reminder(reminder["author"], rm_id)
                        finally:
                            self.remove_reminder(reminder["author"], rm_id)

            # And tick.
            last_time = await self.tick(last_time)


class Reminder:
    def __init__(self, **kwargs):
        self.client = kwargs.get("client")
        self.loop = kwargs.get("loop")
        self.handler = kwargs.get("handler")
        self.nano = kwargs.get("nano")
        self.stats = kwargs.get("stats")
        self.trans = kwargs.get("trans")

        self.reminder = RedisReminderHandler(self.client, self.handler, self.trans, self.loop)

        self.filter = None

        self.loop.create_task(self.reminder.start_monitoring())

    async def on_plugins_loaded(self):
        self.filter = self.nano.get_plugin("commons").get("instance").at_everyone_filter

    async def parse_parameters(self, message, cut_length, lang, fail_msg):
        args = message.content[cut_length:].split(":")
        if len(args) < 2:
            # Try notation with "to" or equivalent in current language
            args = message.content[cut_length:].split(self.trans.get("MSG_REMINDER_TO_LITERAL", lang), maxsplit=1)
            # Still not valid
            if len(args) < 2:
                await message.channel.send(fail_msg)
                self.stats.add(WRONG_ARG)
                raise IgnoredException

        r_time, text = args[0].strip(" "), args[1].strip(" ")

        # If total seconds are not passed (valid), convert to total seconds
        if not r_time.isnumeric():
            if "[" in r_time or "]" in r_time:
                # When people actually do !remind here in [1h 32min]: something
                await message.channel.send(self.trans.get("MSG_REMINDER_NO_BRACKETS", lang))
                raise IgnoredException

            try:
                r_time = convert_to_seconds(r_time)
            except ValueError:
                await message.channel.send(self.trans.get("MSG_REMINDER_INVALID_FORMAT", lang))
                raise IgnoredException

        else:
            r_time = int(args[0])

        # Check text validity
        if len(text) > REM_MAX_CONTENT:
            raise ValueError

        return r_time, text

    async def on_message(self, message, **kwargs):
        trans = self.trans

        prefix = kwargs.get("prefix")
        lang = kwargs.get("lang")

        # Check if this is a valid command
        if not is_valid_command(message.content, commands, prefix):
            return
        else:
            self.stats.add(MESSAGE)

        def startswith(*matches):
            for match in matches:
                if message.content.startswith(match):
                    return True

            return False

        # !remind me in [time]:[text] or [time] to [text]
        if startswith(prefix + "remind me in"):
            try:
                r_time, text = await self.parse_parameters(message, len(prefix) + 13,
                                                           lang, trans.get("MSG_REMINDER_WU_ME", lang).format(prefix))
            # Raised when reminder content is too long
            except ValueError:
                await message.channel.send(trans.get("MSG_REMINDER_TOO_LONG_CONTENT", lang).format(REM_MAX_CONTENT))
                return


            resp = self.reminder.set_reminder(message.author, message.author, text, r_time, lang)

            # Too many reminders going on
            if resp == -1:
                await message.channel.send(trans.get("MSG_REMIDNER_LIMIT_EXCEEDED", lang).format(DEFAULT_REMINDER_LIMIT))

            # Invalid range
            elif resp is False:
                await message.channel.send(trans.get("MSG_REMINDER_INVALID_RANGE", lang).format(REM_MIN_DURATION, REM_MAX_DAYS))

            # Everything valid
            else:
                await message.channel.send(trans.get("MSG_REMINDER_SET", lang))

        # !remind here in [time]:[reminder]
        elif startswith(prefix + "remind here in"):
            try:
                r_time, text = await self.parse_parameters(message, len(prefix) + 13,
                                                           lang, trans.get("MSG_REMINDER_WU_HERE", lang).format(prefix))
            # Raised when reminder content is too long
            except ValueError:
                await message.channel.send(trans.get("MSG_REMINDER_TOO_LONG_CONTENT", lang).format(REM_MAX_CONTENT))
                return

            resp = self.reminder.set_reminder(message.channel, message.author, text, r_time, lang, reminder_type=REMINDER_CHANNEL)

            if resp == -1:
                await message.channel.send(trans.get("MSG_REMIDNER_LIMIT_EXCEEDED", lang).format(DEFAULT_REMINDER_LIMIT))

            elif resp is False:
                await message.channel.send(trans.get("MSG_REMINDER_INVALID_RANGE", lang).format(REM_MIN_DURATION, REM_MAX_DAYS))

            else:
                await message.channel.send(trans.get("MSG_REMINDER_SET", lang))

        # !remind list
        elif startswith(prefix + "remind list", prefix + "reminder list"):
            reminders = self.reminder.get_reminders(message.author.id)

            if not reminders:
                await message.channel.send(trans.get("MSG_REMINDER_LIST_NONE", lang))
                return

            rem = []
            rem_literal = trans.get("MSG_REMINDER_LIST_L", lang)

            for reminder in reminders.values():
                # Gets the remaining time
                ttl = int(reminder["time_target"]) - time.time()

                cont = self.filter(reminder.get("raw"), message.author)

                # Zero or negative number
                if ttl <= 0:
                    when = trans.get("MSG_REMINDER_SOON", lang)
                else:
                    when = resolve_time(ttl, lang)

                rem.append(rem_literal.format(cont, when))

            await message.channel.send(trans.get("MSG_REMINDER_LIST", lang).format("\n\n".join(rem)))

        # !remind remove
        elif startswith(prefix + "remind remove"):
            r_name = message.content[len(prefix + "remind remove "):]

            if not r_name:
                await message.channel.send(trans.get("ERROR_INVALID_CMD_ARGUMENTS", lang))
                return

            if r_name == "all":
                self.reminder.remove_all_reminders(message.author)
                await message.channel.send(trans.get("MSG_REMINDER_DELETE_ALL", lang))

            else:
                r_id = self.reminder.find_id_from_content(message.author.id, r_name)

                # No reminder with such content
                if not r_id:
                    await message.channel.send(trans.get("MSG_REMINDER_DELETE_NONE", lang))
                else:
                    self.reminder.remove_reminder(message.author.id, r_id)
                    await message.channel.send(trans.get("MSG_REMINDER_DELETE_SUCCESS", lang))

        # !remind help
        elif startswith(prefix + "remind"):
            await message.channel.send(trans.get("MSG_REMINDER_HELP", lang).replace("_", prefix))


class NanoPlugin:
    name = "Reminder Commands"
    version = "21"

    handler = Reminder
    events = {
        "on_message": 10,
        "on_plugins_loaded": 5,
        # type : importance
    }
