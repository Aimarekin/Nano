# coding=utf-8
import logging
import time
from datetime import timedelta, datetime
from random import randint

from discord import Message, Embed, Forbidden

from data.stats import MESSAGE, PING
from data.utils import is_valid_command, add_dots

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

#####
# Commons plugin
# Mostly simple commands like !ping and !quote
#####

quotes = [
    "You miss 100% of the shots you don’t take. –Wayne Gretzky",
    "The most difficult thing is the decision to act, the rest is merely tenacity. –Amelia Earhart",
    "Twenty years from now you will be more disappointed by the things that you didn’t do than by the ones you did do, so throw off the bowlines, sail away from safe harbor, catch the trade winds in your sails.  Explore, Dream, Discover. –Mark Twain",
    "Life is 10% what happens to me and 90% of how I react to it. –Charles Swindoll",
    "Eighty percent of success is showing up. –Woody Allen",
    "The best time to plant a tree was 20 years ago. The second best time is now. –Chinese Proverb",
    "Winning isn’t everything, but wanting to win is. –Vince Lombardi",
    "I’ve learned that people will forget what you said, people will forget what you did, but people will never forget how you made them feel. –Maya Angelou",
    "The two most important days in your life are the day you are born and the day you find out why. –Mark Twain",
    "People often say that motivation doesn’t last. Well, neither does bathing.  That’stm why we recommend it daily. –Zig Ziglar",
    "Everything you’ve ever wanted is on the other side of fear. –George Addair",
    "We can easily forgive a child who is afraid of the dark; the real tragedy of life is when men are afraid of the light. –Plato",
    "When I was 5 years old, my mother always told me that happiness was the key to life.  When I went to school, they asked me what I wanted to be when I grew up.  I wrote down ‘happy’.  They told me I didn’t understand the assignment, and I told them they didn’t understand life. –John Lennon",
    "When one door of happiness closes, another opens, but often we look so long at the closed door that we do not see the one that has been opened for us. –Helen Keller",
    "Life is not measured by the number of breaths we take, but by the moments that take our breath away. –Maya Angelou",
    "Too many of us are not living our dreams because we are living our fears. –Les Brown",
    "I didn’t fail the test. I just found 100 ways to do it wrong. –Benjamin Franklin",
    "A person who never made a mistake never tried anything new. –Albert Einstein",
    "A truly rich man is one whose children run into his arms when his hands are empty. –Unknown",
    "If you want your children to turn out well, spend twice as much time with them, and half as much money. –Abigail Van Buren",
    "It does not matter how slowly you go as long as you do not stop. –Confucius",
    "You can’t use up creativity.  The more you use, the more you have. –Maya Angelou",
    "Do what you can, where you are, with what you have. –Teddy Roosevelt",
    "You may be disappointed if you fail, but you are doomed if you don’t try. –Beverly Sills",
    "The human race has one really effective weapon, and that is laughter. –Mark Twain",
    "A great artist can paint a great picture on a small canvas. –Charles Dudley Warner",
    "The present time has one advantage over every other - it is our own. –Charles Caleb Colton",
    "Age does not protect you from love. But love, to some extent, protects you from age. –Anais Nin",
    "A fool can throw a stone in a pond that 100 wise men can not get out. –Saul Bellow",
    "The secret of happiness is something to do. –John Burroughs"]

commands = {
    "_hello": {"desc": "Welcomes a **mentioned** person, or if no mentions are present, you.", "use": "[command] [mention]", "alias": None},
    "_uptime": {"desc": "Tells you for how long I have been running.", "use": None, "alias": None},
    "_github": {"desc": "Link to my project on GitHub.", "use": None, "alias": None},
    "_ping": {"desc": "Just to check if I'm alive. fyi: I love ping-pong.", "use": None, "alias": None},
    "_roll": {"desc": "Replies with a random number in range from 0 to your number.", "use": "[command] [number]", "alias": "_rng"},
    "_rng": {"desc": "Replies with a random number in range from 0 to your number.", "use": "[command] [number]", "alias": "_roll"},
    "_dice": {"desc": "Rolls the dice\nDice expression example: `5d6` - rolls five dices with six sides, `1d9` - rolls one dice with nine sides", "use": "[command] [dice expression]", "alias": None},
    "_decide": {"desc": "Decides between different choices so you don't have to.", "use": "[command] word1|word2|word3|...", "alias": None},
    "_8ball": {"desc": "Answers your questions. 8ball style.", "use": "[command] [question]", "alias": None},
    "_quote": {"desc": "Brightens your day with a random quote.", "use": None, "alias": None},
    "_invite": {"desc": "Gives you a link to invite Nano to another (your) server.", "use": None, "alias": "nano.invite"},
    "nano.invite": {"desc": "Gives you a link to invite Nano to another (your) server.", "use": None, "alias": "_invite"},
    "_avatar": {"desc": "Gives you the avatar url of a mentioned person", "use": "[command] [mention or name]", "alias": None},
    "_say": {"desc": "Says something (#channel is optional)", "use": "[command] (#channel) [message]", "alias": None},
    "nano.info": {"desc": "A little info about me.", "use": None, "alias": "_ayybot"},
    "_nano": {"desc": "A little info about me.", "use": None, "alias": "nano.info"},
}

valid_commands = commands.keys()



class Commons:
    def __init__(self, **kwargs):
        self.client = kwargs.get("client")
        self.loop = kwargs.get("loop")
        self.handler = kwargs.get("handler")
        self.nano = kwargs.get("nano")
        self.stats = kwargs.get("stats")
        self.trans = kwargs.get("trans")

        self.pings = {}
        self.getter = None
        self.resolve_user = None

    async def on_plugins_loaded(self):
        self.getter = self.nano.get_plugin("server").get("instance")
        self.resolve_user = self.nano.get_plugin("admin").get("instance").resolve_user

    async def log_say_command(self, message, content, prefix, lang):
        log_channel = await self.getter.handle_log_channel(message.guild)

        if not log_channel:
            return

        embed = Embed(title=self.trans.get("MSG_LOGPOST_SAY", lang).format(prefix), description=add_dots(content, 350))
        embed.set_author(name="{} ({})".format(message.author.name, message.author.id), icon_url=message.author.avatar_url)
        embed.add_field(name=self.trans.get("INFO_CHANNEL", lang), value=message.channel.mention)

        await self.client.send_message(log_channel, embed=embed)

    @staticmethod
    def at_everyone_filter(content, author, guild):
        # See if the user is allowed to do @everyone
        ok = False
        for role in author.roles:
            if role.permissions.mention_everyone:
                ok = True
                break

        if guild.owner == author:
            ok = True

        # Removes mentions if user doesn't have the permission to mention
        if not ok:
            content = str(content).replace("@everyone", "").replace("@here", "")

        return content

    async def on_message(self, message, **kwargs):
        client = self.client
        trans = self.trans

        prefix = kwargs.get("prefix")
        lang = kwargs.get("lang")

        # Custom commands registered for the server
        server_commands = self.handler.get_custom_commands(message.guild.id)

        if server_commands:
            # Checks for server specific commands
            for command in server_commands.keys():
                # UPDATE 2.1.4: not .startswith anymore!
                if str(message.content) == command:
                    # Maybe same replacement logic in the future update?
                    # TODO implement advanced replacement logic
                    await client.send_message(message.channel, server_commands.get(command))
                    self.stats.add(MESSAGE)

                    return

        # if server_commands:
        #     # According to tests, .startswith is faster than slicing, wtf
        #     pass
        #
        #     for k in server_commands.keys():
        #         if message.content.startswith(k):
        #             # TODO parse logic
        #             pass


        # Check if this is a valid command
        if not is_valid_command(message.content, commands, prefix=prefix):
            return
        else:
            self.stats.add(MESSAGE)

        def startswith(*matches):
            for match in matches:
                if message.content.startswith(match):
                    return True

            return False

        # COMMANDS

        # !hello
        if startswith(prefix + "hello"):
            if len(message.mentions) >= 1:
                await client.send_message(message.channel, trans.get("INFO_HI", lang).format(message.mentions[0].mention))
            elif len(message.mentions) == 0:
                await client.send_message(message.channel, trans.get("INFO_HI", lang).format(message.author.mention))

        # !uptime
        elif startswith(prefix + "uptime"):
            d = datetime(1, 1, 1) + timedelta(seconds=time.time() - self.nano.boot_time)
            uptime = trans.get("MSG_UPTIME", lang).format(d.day - 1, d.hour, d.minute, d.second)

            await client.send_message(message.channel, uptime)

        # !nano, nano.info
        elif startswith((prefix + "nano", "nano.info")):
            await client.send_message(message.channel, trans.get("INFO_GENERAL", lang).replace("<version>", self.nano.version))

        # !github
        elif startswith(prefix + "github"):
            await client.send_message(message.channel, trans.get("INFO_GITHUB", lang))

        # !roll [number]
        elif startswith(prefix + "roll", prefix + "rng "):
            if startswith(prefix + "roll"):
                num = message.content[len(prefix + "roll "):]
            else:
                num = message.content[len(prefix + "rng "):]

            if not num.isnumeric():
                await client.send_message(message.channel, trans.get("ERROR_NOT_NUMBER", lang))
                return

            rn = randint(0, int(num))
            result = "**{}**. {}".format(rn, "**GG**" if rn == int(num) else "")

            await client.send_message(message.channel, trans.get("MSG_ROLL", lang).format(message.author.mention, result))

        # !dice [dice expression: 5d6 + 1d8]
        elif startswith(prefix + "dice"):
            cut = message.content[len(prefix + "dice "):]

            # Defaults to a normal dice
            if not cut:
                dice_types = ["1d6"]
            else:
                dice_types = [a.strip(" ") for a in cut.split("+")]

            results = []
            tt = 0
            for dice in dice_types:
                try:
                    times, sides = dice.split("d")
                    times, sides = int(times), int(sides)
                except ValueError:
                    await client.send_message(message.channel, trans.get("MSG_DICE_INVALID", lang))
                    return

                total = 0
                for _ in range(times):
                    total += randint(1, sides)

                tt += total

                results.append(trans.get("MSG_DICE_ENTRY", lang).format(dice, total))

            await client.send_message(message.channel, trans.get("MSG_DICE_RESULTS", lang).format(message.author.mention, "\n".join(results), tt))

        # !ping
        elif startswith(prefix + "ping"):
            base_time = datetime.now() - message.timestamp
            base_taken = int(divmod(base_time.total_seconds(), 60)[1] * 1000)

            a = await client.send_message(message.channel, trans.get("MSG_PING_MEASURING", lang))
            self.pings[a.id] = [time.monotonic(), message.channel.id, base_taken]

            await client.add_reaction(a, "\U0001F44D")
            self.stats.add(PING)

        # !decide [item1]|[item2]|etc...
        elif startswith(prefix + "decide"):
            cut = str(message.content)[len(prefix + "decide "):].strip(" ")

            if not cut:
                await client.send_message(message.channel, trans.get("MSG_DECIDE_NO_ARGS", lang))
                return

            if len(cut.split("|")) == 1:
                await client.send_message(message.channel, trans.get("MSG_DECIDE_SPECIAL", lang).format(cut))

            else:
                split = cut.split("|")
                rn = randint(0, len(split) - 1)
                await client.send_message(message.channel, trans.get("MSG_DECIDE_NORMAL", lang).format(split[rn]))

        # !8ball
        elif startswith(prefix + "8ball"):
            eight_ball = [a.strip(" ") for a in trans.get("MSG_8BALL_STRINGS", lang).split("|")]
            answer = eight_ball[randint(0, len(eight_ball) - 1)]

            await client.send_message(message.channel, trans.get("MSG_8BALL", lang).format(answer))

        # !quote
        elif startswith(prefix + "quote"):
            chosen = str(quotes[randint(0, len(quotes) - 1)])

            # Find the part where the author is mentioned
            place = chosen.rfind("–")
            await client.send_message(message.channel, "{}\n- __{}__".format(chosen[:place], chosen[place+1:]))

        # !invite
        elif startswith(prefix + "invite", "nano.invite"):
            # ONLY FOR TESTING - if nano beta is active
            if startswith("nano.invite.make_real"):
                application = await client.application_info()

                # Most of the permissions that Nano uses
                perms = "1543765079"
                url = "<https://discordapp.com/oauth2/" \
                      "authorize?client_id={}&scope=bot&permissions={}>".format(application.id, perms)

                await client.send_message(message.channel, trans.get("INFO_INVITE", lang).replace("<link>", url))
                return

            await client.send_message(message.channel, trans.get("INFO_INVITE", lang).replace("<link>", "<http://invite.nanobot.pw>"))

        # !avatar
        elif startswith(prefix + "avatar"):
            name = message.content[len(prefix + "avatar "):]

            if not name:
                member = message.author
            else:
                member = await self.resolve_user(name, message, lang)

            url = member.avatar_url

            if url:
                await client.send_message(message.channel, trans.get("MSG_AVATAR_OWNERSHIP", lang).format(member.name, url))
            else:
                await client.send_message(message.channel, trans.get("MSG_AVATAR_NONE", lang).format(member.name))

        # !say (#channel) [message]
        elif startswith(prefix + "say"):
            if not self.handler.is_mod(message.author, message.guild):
                await client.send_message(message.channel, trans.get("PERM_MOD", lang))
                return "return"

            content = str(message.content[len(prefix + "say "):]).strip(" ")

            if not content:
                await client.send_message(message.channel, trans.get("ERROR_INVALID_CMD_ARGUMENTS", lang))
                return

            if len(message.channel_mentions) != 0:
                channel = message.channel_mentions[0]
                content = content.replace(channel.mention, "").strip(" ")
            else:
                channel = message.channel

            content = self.at_everyone_filter(content, message.author, message.guild)

            try:
                await client.send_message(channel, content)
                await self.log_say_command(message, content, prefix, lang)
            except Forbidden:
                await client.send_message(message.channel, trans.get("MSG_SAY_NOPERM", lang).format(channel.id))

    async def on_reaction_add(self, reaction, _, **kwargs):
        if reaction.message.id in self.pings.keys():
            data = self.pings.pop(reaction.message.id)
            lang = kwargs.get("lang")

            delta = round((time.monotonic() - int(data[0])) * 100, 2)
            msg = await self.client.get_message(self.client.get_channel(data[1]), reaction.message.id)

            await self.client.edit_message(msg, self.trans.get("MSG_PING_RESULT", lang).format(data[2], delta))
            await self.client.clear_reactions(msg)


class NanoPlugin:
    name = "Common Commands"
    version = "23"

    handler = Commons
    events = {
        "on_message": 10,
        "on_reaction_add": 10,
        "on_plugins_loaded": 5,
        # type : importance
    }
