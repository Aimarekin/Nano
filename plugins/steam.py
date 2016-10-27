# coding=utf-8
import steamapi
import configparser
import logging
from discord import Message, HTTPException
from data.utils import is_valid_command
from data.stats import MESSAGE

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

parser = configparser.ConfigParser()
parser.read("plugins/config.ini")

valid_commands = [
    "_steam user", "_steam games", "_steam help",
    "_steam friends",
]


class SteamSearch:
    def __init__(self, api_key):
        steamapi.core.APIConnection(api_key=api_key)

    @staticmethod
    def get_user(uid):
        try:
            user = steamapi.user.SteamUser(userurl=str(uid))
            return user
        except steamapi.errors.UserNotFoundError:
            return None

    @staticmethod
    def get_friends(uid):
        try:
            user = steamapi.user.SteamUser(userurl=str(uid))
            return user.name, [friend.name for friend in user.friends]
        except steamapi.errors.UserNotFoundError:
            return None, None

    @staticmethod
    def get_games(uid):
        try:
            user = steamapi.user.SteamUser(userurl=str(uid))
            return user.name, [game.name for game in user.games]
        except steamapi.errors.UserNotFoundError:
            return None, None

    @staticmethod
    def get_owned_games(uid):
        try:
            user = steamapi.user.SteamUser(userurl=str(uid))
            return user.name, [game.name for game in user.owned_games]
        except steamapi.errors.UserNotFoundError:
            return None, None


class Steam:
    def __init__(self, **kwargs):
        self.nano = kwargs.get("nano")
        self.client = kwargs.get("client")
        self.stats = kwargs.get("stats")

        key = parser.get("steam", "key")
        self.steam = SteamSearch(key)

    async def on_message(self, message, **kwargs):
        assert isinstance(message, Message)

        client = self.client
        prefix = kwargs.get("prefix")

        if not is_valid_command(message.content, valid_commands, prefix=prefix):
            return
        else:
            self.stats.add(MESSAGE)

        def startswith(*msg):
            for a in msg:
                if message.content.startswith(a):
                    return True

            return False

        if startswith(prefix + "steam"):
            if startswith(prefix + "steam friends "):
                uid = str(message.content)[len(prefix + "steam friends "):]

                # Friend search
                await client.send_typing(message.channel)
                username, friends = self.steam.get_friends(uid)

                friends = ["`" + friend + "`" for friend in friends]

                if not username:
                    await client.send_message(message.channel, "User **does not exist**.")
                    # stat.pluswrongarg()
                    return

                await client.send_message(message.channel,
                                          "*User:* **{}**\n\n*Friends:* {}".format(username, ", ".join(friends)))

            elif startswith(prefix + "steam games"):
                uid = str(message.content)[len(prefix + "steam games "):]

                # Game search
                await client.send_typing(message.channel)
                username, games = self.steam.get_owned_games(uid)

                if not username:
                    await client.send_message(message.channel, "User **does not exist**.")
                    # stat.pluswrongarg()
                    return

                games = ["`{}`".format(game) for game in games]

                try:
                    await client.send_message(message.channel,
                                              "*User:* **{}**:\n\n*Owned games:* {}".format(username, ", ".join(games)))
                except HTTPException:
                    await client.send_message(message.channel,
                                              "This message can not fit onto Discord: **user has too many games to display (lol)**")

            elif startswith(prefix + "steam user "):
                uid = str(message.content)[len(prefix + "steam user "):]

                # Basic search
                await client.send_typing(message.channel)
                steam_user = self.steam.get_user(uid)

                if not steam_user:
                    await client.send_message(message.channel, "User **does not exist**.")
                    # stat.pluswrongarg()
                    return

                info = "User: **{}**\n```css\nStatus: {}\nLevel: {}\nGames: {} owned (including free games)\nFriends: {}```\n" \
                       "Direct link: http://steamcommunity.com/id/{}/".format(steam_user.name, "Online" if steam_user.state else "Offline",
                                                                              steam_user.level, len(steam_user.games), len(steam_user.friends), uid)

                try:
                    await client.send_message(message.channel, info)

                except HTTPException:
                    await client.send_message(message.channel,
                                              "This message can not fit onto Discord: **user has too many friends to display (lol)**")

            elif startswith(prefix + "steam") or startswith(prefix + "steam help"):
                await client.send_message(message.channel,
                                          "**Steam commands:**\n`_steam user community_url`, `_steam friends community_url`, `_steam games community_url`".replace("_", prefix))


class NanoPlugin:
    _name = "Steam Commands"
    _version = 0.1

    handler = Steam
    events = {
        "on_message": 10
        # type : importance
    }
