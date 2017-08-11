# coding=utf-8
import asyncio
import gc
import logging
import os
import time
from datetime import datetime, timedelta

import discord
import psutil

from data.stats import MESSAGE
from data.utils import is_valid_command, log_to_file, is_disabled

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Might be implemented someday
# BOT_FARM_RATIO = 0.55
# BOT_FARM_MIN_MEMBERS = 40

FAILPROOF_TIME_WAIT = 2.5

commands = {
    "_debug": {"desc": "Displays EVEN MORE stats about Nano.", "use": None, "alias": None},
    "_status": {"desc": "Displays current status: server, user and channel count.", "use": None, "alias": "nano.status"},
    "nano.status": {"desc": "Displays current status: server, user and channel count.", "use": None, "alias": "_status"},
    "_stats": {"desc": "Some stats like message count and stuff like that.", "use": None, "alias": "nano.stats"},
    "nano.stats": {"desc": "Some stats like message count and stuff like that.", "use": None, "alias": "_stats"},
    "_prefix": {"desc": "No use whatsoever, but jk here you have it.", "use": None, "alias": None},
    "nano.prefix": {"desc": "Helps you figure out the prefix.", "use": None, "alias": None},
    "_members": {"desc": "Lists all members on the server.", "use": None, "alias": None},
    "_server": {"desc": "Shows info about current server.", "use": None, "alias": None}
}

valid_commands = commands.keys()


class ServerManagement:
    def __init__(self, **kwargs):
        self.client = kwargs.get("client")
        self.loop = kwargs.get("loop")
        self.handler = kwargs.get("handler")
        self.nano = kwargs.get("nano")
        self.stats = kwargs.get("stats")
        self.trans = kwargs.get("trans")

        # Debug
        self.lt = time.time()
        self.bans = {}

    async def handle_log_channel(self, guild):
        chan = self.handler.get_var(guild.id, "logchannel")

        if is_disabled(chan):
            return None

        return discord.utils.find(lambda m: m.id == chan, guild.channels)

    async def handle_def_channel(self, guild, channel_id):
        if is_disabled(channel_id):
            return await self.default_channel(guild)
        else:
            chan = discord.utils.find(lambda c: c.id == channel_id, guild.channels)
            if not chan:
                log_to_file("Custom channel does not exist anymore: {} ({})".format(guild.name, guild.id))
                return await self.default_channel(guild)
            else:
                return chan

    @staticmethod
    async def default_channel(guild):
        # Try to find #general or one that starts with general
        chan = discord.utils.find(lambda c: c.name == "general", guild.text_channels)
        if chan:
            return chan

        # Else, return the topmost one
        top = sorted(guild.text_channels, key=lambda a: a.position)[0]
        return top

    @staticmethod
    async def send_message_failproof(channel, message=None, embed=None):
        try:
            await channel.send(content=message, embed=embed)
        except discord.HTTPException:
            await asyncio.sleep(FAILPROOF_TIME_WAIT)
            await channel.send(content=message, embed=embed)
            raise

    @staticmethod
    def make_logchannel_embed(user, action, color=discord.Color(0x2e75cc)):
        # Color: Nano's dark blue color
        return discord.Embed(description="ID: {}".format(user.id), color=color).set_author(name="{} {}".format(user.name, action), icon_url=user.avatar_url)

    async def on_message(self, message, **kwargs):
        client = self.client
        trans = self.trans

        prefix = kwargs.get("prefix")
        lang = kwargs.get("lang")

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

        # !status
        if startswith(prefix + "status"):
            server_count = 0
            members = 0
            channels = 0

            # Iterate though servers and add up things
            for guild in client.guilds:

                server_count += 1
                members += int(guild.member_count)
                channels += len(guild.channels)

            embed = discord.Embed(name=trans.get("MSG_STATUS_STATS", lang), colour=discord.Colour.dark_blue())

            embed.add_field(name=trans.get("MSG_STATUS_SERVERS", lang), value=trans.get("MSG_STATUS_SERVERS_L", lang).format(server_count), inline=True)
            embed.add_field(name=trans.get("MSG_STATUS_USERS", lang), value=trans.get("MSG_STATUS_USERS_L", lang).format(members), inline=True)
            embed.add_field(name=trans.get("MSG_STATUS_CHANNELS", lang), value=trans.get("MSG_STATUS_CHANNELS_L", lang).format(channels), inline=True)

            await message.channel.send("**Stats**", embed=embed)

        # !debug
        elif startswith(prefix + "debug", prefix + "stats more"):
            # Some more debug data

            # Ratelimit every 360 seconds
            if ((self.lt - time.time()) < 360) and not self.handler.is_bot_owner(message.author.id):
                return

            self.lt = time.time()

            # CPU
            cpu = psutil.cpu_percent(interval=0.3)

            # RAM
            def get_ram_usage():
                nano_process = psutil.Process(os.getpid())
                return round(nano_process.memory_info()[0] / float(2 ** 20), 1)  # Converts to MB

            mem_before = get_ram_usage()
            # Attempt garbage collection
            gc.collect()

            mem_after = get_ram_usage()
            garbage = round(mem_after - mem_before, 2)

            # OTHER
            d = datetime(1, 1, 1) + timedelta(seconds=time.time() - self.nano.boot_time)
            uptime = trans.get("MSG_DEBUG_UPTIME_L", lang).format(d.day - 1, d.hour, d.minute, d.second)

            nano_version = self.nano.version
            discord_version = discord.__version__

            reminders = self.nano.get_plugin("reminder").get("instance").reminder.get_reminder_amount()
            polls = self.nano.get_plugin("voting").get("instance").vote.get_vote_amount()

            embed = discord.Embed(colour=discord.Colour.green())

            embed.add_field(name=trans.get("MSG_DEBUG_VERSION", lang), value=nano_version)
            embed.add_field(name=trans.get("MSG_DEBUG_DPY", lang), value=discord_version)
            embed.add_field(name=trans.get("MSG_DEBUG_RAM", lang), value=trans.get("MSG_DEBUG_GC", lang).format(mem_after, abs(garbage)))
            embed.add_field(name=trans.get("MSG_DEBUG_CPU", lang), value=trans.get("MSG_DEBUG_CPU_L", lang).format(cpu))
            embed.add_field(name=trans.get("MSG_DEBUG_REMINDERS", lang), value=str(reminders))
            embed.add_field(name=trans.get("MSG_DEBUG_VOTES", lang), value=str(polls))

            # Redis db stats
            redis_mem = self.handler.db_info("memory").get("used_memory_human")
            embed.add_field(name=trans.get("MSG_DEBUG_R_MEM", lang), value=redis_mem)

            redis_size = self.handler.db_size()
            embed.add_field(name=trans.get("MSG_DEBUG_R_KEYS", lang), value=redis_size)

            embed.add_field(name=trans.get("MSG_DEBUG_UPTIME", lang), value=uptime)

            await message.channel.send(trans.get("MSG_DEBUG_INFO", lang), embed=embed)

        # !stats
        elif startswith(prefix + "stats"):
            file = self.stats.get_data()

            messages = file.get("msgcount")
            wrong_args = file.get("wrongargcount")
            sleeps = file.get("timesslept")
            wrong_permissions = file.get("wrongpermscount")
            helps = file.get("peoplehelped")
            votes = file.get("votesgot")
            pings = file.get("timespinged")
            imgs = file.get("imagessent")

            embed = discord.Embed(colour=discord.Colour.gold())

            embed.add_field(name=trans.get("MSG_STATS_MSGS", lang), value=messages)
            embed.add_field(name=trans.get("MSG_STATS_ARGS", lang), value=wrong_args)
            embed.add_field(name=trans.get("MSG_STATS_PERM", lang), value=wrong_permissions)
            embed.add_field(name=trans.get("MSG_STATS_HELP", lang), value=helps)
            embed.add_field(name=trans.get("MSG_STATS_IMG", lang), value=imgs)
            embed.add_field(name=trans.get("MSG_STATS_VOTES", lang), value=votes)
            embed.add_field(name=trans.get("MSG_STATS_SLEPT", lang), value=sleeps)
            embed.add_field(name=trans.get("MSG_STATS_PONG", lang), value=pings)
            embed.add_field(name=trans.get("MSG_STATS_IMG", lang), value=imgs)

            await message.channel.send(trans.get("MSG_STATS_INFO", lang), embed=embed)

        # !prefix
        elif startswith(prefix + "prefix"):
            await message.channel.send(trans.get("MSG_PREFIX_OHYEAH", lang))

        # nano.prefix
        elif startswith("nano.prefix"):
            await message.channel.send(trans.get("MSG_PREFIX", lang).format(prefix))

        # !members
        elif startswith(prefix + "members"):
            ls = [member.name for member in message.guild.members]
            amount = len(ls)

            members = trans.get("MSG_MEMBERS_LIST", lang).format(", ".join(["`{}`".format(mem) for mem in ls])) + \
                      trans.get("MSG_MEMBERS_TOTAL", lang).format(amount)

            if len(members) > 2000:
                # Only send the number if the message is too long.
                await message.channel.send(trans.get("MSG_MEMBERS_AMOUNT", lang).format(amount))

            else:
                await message.channel.send(members)

        # !server
        elif startswith(prefix + "server"):
            user_count = message.guild.member_count
            users_online = len([user.id for user in message.guild.members if user.status == user.status.online])

            v_level = message.guild.verification_level
            if v_level == v_level.none:
                v_level = trans.get("MSG_SERVER_VL_NONE", lang)
            elif v_level == v_level.low:
                v_level = trans.get("MSG_SERVER_VL_LOW", lang)
            elif v_level == v_level.medium:
                v_level = trans.get("MSG_SERVER_VL_MEDIUM", lang)
            else:
                v_level = trans.get("MSG_SERVER_VL_HIGH", lang)

            text_chan = len(message.guild.text_channels)
            voice_chan = len(message.guild.voice_channels)
            channels = text_chan + voice_chan

            # Teal Blue
            embed = discord.Embed(colour=discord.Colour(0x3F51B5), description=trans.get("MSG_SERVER_ID", lang).format(message.guild.id))

            if message.guild.icon:
                embed.set_author(name=message.guild.name, icon_url=message.guild.icon_url)
                embed.set_thumbnail(url=message.guild.icon_url)
            else:
                embed.set_author(name=message.guild.name)

            embed.set_footer(text=trans.get("MSG_SERVER_DATE_CREATED", lang).format(message.guild.created_at))

            embed.add_field(name=trans.get("MSG_SERVER_MEMBERS", lang).format(user_count),
                            value=trans.get("MSG_SERVER_MEMBERS_L", lang).format(users_online))

            embed.add_field(name=trans.get("MSG_SERVER_CHANNELS", lang).format(channels),
                            value=trans.get("MSG_SERVER_CHANNELS_L", lang).format(voice_chan, text_chan))

            embed.add_field(name=trans.get("MSG_SERVER_VL", lang), value=v_level)
            embed.add_field(name=trans.get("MSG_SERVER_ROLES", lang),
                            value=trans.get("MSG_SERVER_ROLES_L", lang).format(len(message.guild.roles) - 1))

            embed.add_field(name=trans.get("MSG_SERVER_OWNER", lang),
                            value=trans.get("MSG_SERVER_OWNER_L", lang).format(message.guild.owner.name,
                                                                               message.guild.owner.discriminator,
                                                                               message.guild.owner.id))

            await message.channel.send(trans.get("MSG_SERVER_INFO", lang), embed=embed)

    async def on_member_join(self, member, **kwargs):
        lang = kwargs.get("lang")

        # TODO make more dynamic
        replacement_logic = {
            ":user": member.mention,
            ":username": member.name,
            ":server": member.guild.name
        }

        welcome_msg = str(self.handler.get_var(member.guild.id, "welcomemsg"))

        # Replacement logic
        for trigg, repl in replacement_logic.items():
            welcome_msg = welcome_msg.replace(trigg, repl)

        log_c = await self.handle_log_channel(member.guild)
        def_c = await self.handle_def_channel(member.guild, self.handler.get_defaultchannel(member.guild))

        # Ignore if disabled
        if log_c:
            embed = self.make_logchannel_embed(member, self.trans.get("EVENT_JOIN", lang))
            await self.send_message_failproof(log_c, embed=embed)
        
        if not is_disabled(welcome_msg):
            await self.send_message_failproof(def_c, welcome_msg)

    async def on_member_ban(self, guild, member, **kwargs):
        self.bans[member.id] = time.time()

        lang = kwargs.get("lang")

        replacement_logic = {
            ":user": member.mention,
            ":username": member.name,
            ":server": guild.name}

        ban_msg = str(self.handler.get_var(guild.id, "banmsg"))

        for trigg, repl in replacement_logic.items():
            ban_msg = ban_msg.replace(trigg, repl)

        log_c = await self.handle_log_channel(guild)
        def_c = await self.handle_def_channel(guild, self.handler.get_defaultchannel(guild))

        # Ignore if disabled
        if log_c:
            embed = self.make_logchannel_embed(member, self.trans.get("EVENT_BAN", lang))
            await self.send_message_failproof(log_c, embed=embed)

        if not is_disabled(ban_msg):
            await self.send_message_failproof(def_c, ban_msg)

    async def on_member_remove(self, member, **kwargs):
        if member.id in self.bans.keys():
            self.bans.pop(member.id)
            return

        lang = kwargs.get("lang")

        replacement_logic = {
            ":user": member.mention,
            ":username": member.name,
            ":server": member.guild.name}

        leave_msg = str(self.handler.get_var(member.guild.id, "leavemsg"))

        for trigg, repl in replacement_logic.items():
            leave_msg = leave_msg.replace(trigg, repl)

        log_c = await self.handle_log_channel(member.guild)
        def_c = await self.handle_def_channel(member.guild, self.handler.get_defaultchannel(member.guild))

        # Ignore if disabled
        if log_c:
            embed = self.make_logchannel_embed(member, self.trans.get("EVENT_LEAVE", lang))
            await self.send_message_failproof(log_c, embed=embed)
        
        if not is_disabled(leave_msg):
            await self.send_message_failproof(def_c, leave_msg)

    async def on_server_join(self, guild, **kwargs):
        # Always 'en'
        lang = kwargs.get("lang")
        # Say hi to the server
        await self.send_message_failproof(await self.default_channel(guild), self.trans.get("EVENT_SERVER_JOIN", lang))

        # Create server settings
        self.handler.server_setup(guild)

    async def on_server_remove(self, guild, **_):
        # Deletes server data
        self.handler.delete_server(guild.id)

        # Log
        log_to_file("Removed from guild: {}".format(guild.name))

    async def on_ready(self):
        await self.client.wait_until_ready()

        # Delay in case servers are still being received
        await asyncio.sleep(10)

        log.info("Checking guild vars...")
        for guild in self.client.guilds:
            if not self.handler.server_exists(guild.id):
                self.handler.server_setup(guild)

            self.handler.check_server_vars(guild)
        log.info("Done.")

        log.info("Checking for non-used guild data...")
        server_ids = [s.id for s in self.client.guilds]
        self.handler.check_old_servers(server_ids)
        log.info("Done.")


class NanoPlugin:
    name = "Moderator"
    version = "26"

    handler = ServerManagement
    events = {
        "on_message": 10,
        "on_ready": 11,
        "on_member_join": 10,
        "on_member_ban": 10,
        "on_member_remove": 10,
        "on_server_join": 9,
        "on_server_remove": 9,
        # type : importance
    }
