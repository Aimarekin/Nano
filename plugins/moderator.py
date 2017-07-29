# coding=utf-8
import logging
import re
from pickle import load

from discord import Message, Client, Embed

from data.stats import SUPPRESS
from data.utils import make_dots

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# CONSTANTS

accepted_chars = "abcdefghijklmnopqrstuvwxyz "


def normalize(line):
    # Ignores punctuation, new lines, etc...
    accepted = "".join([char for char in line if char in accepted_chars])

    return accepted


def two_chars(line):
    # Normalizes
    norm = normalize(line)
    # Yields two by two
    for rn in range(0, len(norm) - 1):
        yield norm[rn:rn + 1], norm[rn + 1:rn + 2]


def get_valid_commands(plugin):
        try:
            return plugin.commands
        except AttributeError:
            return None


class NanoModerator:
    def __init__(self):
        self.permutations = [
            dict(a="4"),
            dict(s="$"),
            dict(o="0"),
            dict(a="@"),
        ]

        with open("plugins/banned_words.txt", "r") as banned:
            self.word_list = [line.strip("\n") for line in banned.readlines()]

        # Builds a more sophisticated list
        before = len(self.word_list)
        for word in self.word_list:
            initial = str(word)

            for perm in self.permutations:
                (k, v), = perm.items()
                changed = initial.replace(k, v)
                if initial != changed:
                    self.word_list.append(changed)

        logger.info("Processed word list: added {} entries ({} total)".format(len(self.word_list) - before, len(self.word_list)))


        # Gibberish detector
        with open("plugins/spam_model.pki", "rb") as spam_model:
            self.spam_model = load(spam_model)

        self.data = self.spam_model["data"]
        self.threshold = self.spam_model["threshold"]
        self.char_positions = self.spam_model["positions"]

        # Entropy calculator
        self.chars2 = "abcdefghijklmnopqrstuvwxyz,.-!?_;:|1234567890*=)(/&%$#\"~<> "
        self.pos2 = dict([(c, index) for index, c in enumerate(self.chars2)])

        self.invite_regex = re.compile(r'(http(s)?://)?discord.gg/\w+')

    def check_swearing(self, message):
        """Returns True if there is a banned word
        :param message: Discord Message content
        """
        if isinstance(message, Message):
            message = str(message.content)

        message = str(message).lower()

        # Massive speed improvement in 0.3
        res = [a for a in self.word_list if a in message]
        return bool(res)

    def check_spam(self, message):
        """
        Does a set of checks.
        :param message: string to check
        :return: bool
        """
        if isinstance(message, Message):
            message = str(message.content)

        # 1. Should exclude links
        message = " ".join([word for word in message.split(" ") if
                            (not word.startswith("https://")) and (not word.startswith("http://"))])

        # 2. Should always ignore short sentences
        if len(message) < 10:
            return False

        result = self.detect_gib(message)
        # Currently uses only the gibberish detector since the other one
        # does not have a good detection of repeated chars

        return result

    def detect_gib(self, message):
        """Returns True if spam is found
        :param message: string
        """
        if not message:
            return

        th = len(message) / 2.4
        c = float(0)
        for ca, cb in two_chars(message):

            if self.data[self.char_positions[ca]][self.char_positions[cb]] < self.threshold[self.char_positions[ca]]:
                c += 1

        return bool(c >= th)

    def _detect_spam(self, message):
        """
        String entropy calculator.
        :param message: string
        :return: bool
        """

        counts = [[0 for _ in range(len(self.chars2))] for _ in range(len(self.chars2))]

        for o, t in two_chars(message):
            counts[self.pos2[o]][self.pos2[t]] += 1

        thr = 0
        for this in counts:
            for another in this:
                thr += another

        thr /= 3.5

        for this in counts:
            for another in this:
                if another > thr:
                    return True

        return False

    def check_invite(self, message):
        """
        Checks for invites
        :param message: string
        :return: bool
        """
        if isinstance(message, Message):
            message = str(message.content)

        res = self.invite_regex.search(str(message))

        return res if res else None


class LogManager:
    def __init__(self, client, nano, loop, handler, trans):
        self.client = client
        self.nano = nano
        self.loop = loop
        self.handler = handler
        self.trans = trans

        self.getter = None
        self.running = True

    async def get_plugin(self):
        self.getter = self.nano.get_plugin("server").get("instance")

    async def send_message(self, channel, embed):
        await self.client.send_message(channel, embed=embed)

    async def send_log(self, message: Message, lang, reason=""):
        if not self.getter:
            self.loop.call_later(5, self.send_log(message, lang, reason))
            logger.warning("Getter is not set, calling in 5 seconds...")
            return

        log_channel = await self.getter.handle_log_channel(message.server)

        if not log_channel:
            return

        author = message.author

        embed_title = self.trans.get("MSG_MOD_MSG_DELETED", lang).format(reason)

        embed = Embed(title=embed_title, description=make_dots(message.content))
        embed.set_author(name="{} ({})".format(author.name, author.id), icon_url=author.avatar_url)
        embed.add_field(name=self.trans.get("INFO_CHANNEL", lang), value=message.channel.mention)

        logger.debug("Sending logs for {}".format(message.server.name))
        await self.send_message(log_channel, embed=embed)


class Moderator:
    def __init__(self, **kwargs):
        self.client = kwargs.get("client")
        self.loop = kwargs.get("loop")
        self.handler = kwargs.get("handler")
        self.nano = kwargs.get("nano")
        self.stats = kwargs.get("stats")
        self.trans = kwargs.get("trans")

        self.checker = NanoModerator()
        self.log = LogManager(self.client, self.nano, self.loop, self.handler, self.trans)

        self.valid_commands = []

    async def on_plugins_loaded(self):
        # Collect all valid commands
        plugins = [a.get("plugin") for a in self.nano.plugins.values() if a.get("plugin")]
        self.valid_commands = [item for sub in [get_valid_commands(b) for b in plugins if get_valid_commands(b)] for item in sub]

        await self.log.get_plugin()

    async def on_message(self, message, **kwargs):
        handler = self.handler
        client = self.client
        prefix = kwargs.get("prefix")

        lang = kwargs.get("lang")

        assert isinstance(client, Client)

        if message.channel.is_private:
            return "return"

        # Muting
        if handler.is_muted(message.server, message.author.id):
            await client.delete_message(message)

            self.stats.add(SUPPRESS)
            return "return"

        # Channel blacklisting
        if handler.is_blacklisted(message.server.id, message.channel.id):
            return "return"

        # Ignore existing commands
        def is_command(content, valids):
            for a in valids:
                if str(content).startswith(str(a).replace("_", str(prefix))):
                    return True

            return False

        # Ignore the filter if user is executing a command
        if is_command(message.content, self.valid_commands):
            return

        # Spam, swearing and invite filter
        needs_spam_filter = handler.has_spam_filter(message.server)
        needs_swearing_filter = handler.has_word_filter(message.server)
        needs_invite_filter = handler.has_invite_filter(message.server)

        if needs_spam_filter:
            spam = self.checker.check_spam(message)
        else:
            spam = False

        if needs_swearing_filter:
            swearing = self.checker.check_swearing(message)
        else:
            swearing = False

        if needs_invite_filter:

            if not handler.can_use_admin_commands(message.author, message.server):
                invite = self.checker.check_invite(message)

            else:
                invite = False

        else:
            invite = False


        # Delete if necessary
        if any([spam, swearing, invite]):
            await client.delete_message(message)
            logger.debug("Message filtered")

            # Check if current channel is the logging channel
            log_channel_name = self.handler.get_log_channel(message.server)
            if log_channel_name == message.channel.name:
                return

            # Make correct messages
            if spam:
                await self.log.send_log(message, self.trans.get("MSG_MOD_SPAM", lang))

            elif swearing:
                await self.log.send_log(message, self.trans.get("MSG_MOD_SWEARING", lang))

            elif invite:
                await self.log.send_log(message, self.trans.get("MSG_MOD_INVITE", lang))

            else:
                # Lol wat
                return

            return "return"


class NanoPlugin:
    name = "Moderator"
    version = "29"

    handler = Moderator
    events = {
        "on_plugins_loaded": 5,
        "on_message": 6
        # type : importance
    }
