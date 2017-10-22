# coding=utf-8
import configparser
import logging

# External library available here: https://github.com/DefaltSimon/TMDbie
import tmdbie
from discord import errors
from typing import Union

from data.stats import MESSAGE
from data.utils import is_valid_command, IgnoredException
from data.confparser import get_config_parser

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

parser = get_config_parser()

commands = {
    "_imdb search": {"desc": "Searches for a film/series/person and displays general info", "use": "[command] [film/series/person name]", "alias": "_tmdb search"},
    "_imdb trailer": {"desc": "Gives you a link to the trailer of a film/series.", "use": "[command] [film/series/person name]", "alias": "_tmdb trailer"},
    "_imdb plot": {"desc": "Displays more plot info about a film/series.", "use": "[command] [film/series/person name]", "alias": "_tmdb plot"},
    "_imdb rating": {"desc": "Displays different ratings for the film/series.", "use": "[command] [film/series/person name]", "alias": "_tmdb rating"},
    "_imdb help": {"desc": "Displays available commands regarding IMDb.", "use": "[command]", "alias": "_tmdb help"},
    "_imdb": {"desc": "Displays all kinds of film/series info. (Powered by https://www.themoviedb.org)\nSubcommands: `search` `trailer` `plot` `rating` `help`"},
    "_tmdb": {"desc": "Displays all kinds of film/series info. (Powered by https://www.themoviedb.org)\nSubcommands: `search` `trailer` `plot` `rating` `help`"},
}

valid_commands = commands.keys()


class TMDb:
    def __init__(self, **kwargs):
        self.client = kwargs.get("client")
        self.nano = kwargs.get("nano")
        self.stats = kwargs.get("stats")
        self.loop = kwargs.get("loop")
        self.trans = kwargs.get("trans")

        try:
            self.tmdb = tmdbie.Client(api_key=parser.get("tmdb", "api-key"))
        except (configparser.NoSectionError, configparser.NoOptionError):
            log.critical("Missing api key for tmdb, disabling plugin...")
            raise RuntimeError

    async def _imdb_search(self, name, message, lang) -> Union[tmdbie.Movie, tmdbie.TVShow, tmdbie.Person]:
        if not name:
            await message.channel.send(self.trans.get("MSG_IMDB_NEED_TITLE", lang))
            raise IgnoredException

        try:
            data = await self.tmdb.search_multi(name)
        except tmdbie.TMDbException:
            await message.channel.send(self.trans.get("MSG_IMDB_ERROR2", lang))
            raise

        # Check validity
        if not data:
            await message.channel.send(self.trans.get("MSG_IMDB_NORESULTS", lang))
            raise IgnoredException

        return data

    # noinspection PyUnresolvedReferences
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

        # !imdb
        if startswith(prefix + "imdb", prefix + "tmdb"):
            # The process can take some time so we show that something is happening
            await message.channel.trigger_typing()

            cut = message.content[len(prefix + "imdb "):]

            try:
                subcommand, argument = cut.split(" ", maxsplit=1)
            # In case there are no parameters
            except ValueError:
                # Check if no subcommand - valid
                # If there's a subcommand, but no argument, fail
                if not cut.strip(" "):
                    await message.channel.send(trans.get("MSG_IMDB_INVALID_USAGE", lang).format(prefix))
                    return

                else:
                    subcommand, argument = cut, ""

            # !imdb plot
            if subcommand == "plot":
                data = await self._imdb_search(argument, message, lang)

                # Check type
                if data.media_type not in ["tv", "movie"]:
                    await message.channel.send(trans.get("MSG_IMDB_CANTPERSON", lang))
                    return

                # Try to send
                try:
                    info = trans.get("MSG_IMDB_PLOT", lang).format(data.title, data.overview)

                    await message.channel.send(info)
                except AttributeError:
                    await message.channel.send(trans.get("MSG_IMDB_PLOT_MISSING", lang))

            # !imdb search
            elif subcommand == "search":
                data = await self._imdb_search(argument, message, lang)

                # Check type
                if data.media_type in ["tv", "movie"]:
                    info = []

                    # Step-by-step adding - some data might be missing
                    try:
                        media_type = trans.get("MSG_IMDB_SERIES", lang) if data.media_type == "tv" else ""

                        info.append("**{}** {}\n".format(data.title, media_type))
                    except AttributeError:
                        pass

                    try:
                        genres = "`{}`".format("`, `".join(data.genres))
                        info.append(trans.get("MSG_IMDB_GENRES", lang).format(genres))
                    except AttributeError:
                        pass

                    try:
                        info.append(trans.get("MSG_IMDB_AVGRATING", lang).format(data.vote_average))
                    except AttributeError:
                        pass

                    if data.media_type == "tv":
                        try:
                            info.append(trans.get("MSG_IMDB_SEASONS", lang).format(len(data.seasons)))
                        except AttributeError:
                            pass

                    try:
                        info.append(trans.get("MSG_IMDB_SUMMARY", lang).format(data.overview))
                    except AttributeError:
                        pass

                    try:
                        if data.poster:
                            info.append(trans.get("MSG_IMDB_POSTER", lang).format(data.poster))
                    except AttributeError:
                        pass

                    # Compile together info that is available
                    media_info = "\n".join(info)

                else:
                    await message.channel.send(trans.get("MSG_IMDB_PERSON_NOT_SUPPORTED", lang))
                    return

                # Send the details
                try:
                    await message.channel.send(media_info)
                except errors.HTTPException:
                    await message.channel.send(trans.get("MSG_IMDB_ERROR", lang))

            # !imdb trailer
            elif subcommand == "trailer":
                data = await self._imdb_search(argument, message, lang)

                try:
                    await message.channel.send(trans.get("MSG_IMDB_TRAILER", lang).format(data.title, data.trailer))
                except AttributeError:
                    await message.channel.send(trans.get("MSG_IMDB_TRAILER_MISSING", lang))

            # !imdb rating
            elif subcommand == "rating":
                data = await self._imdb_search(argument, message, lang)

                try:
                    content = trans.get("MSG_IMDB_RATINGS", lang).format(data.title, data.vote_average)
                    await message.channel.send(content)
                except AttributeError:
                    await message.channel.send(trans.get("MSG_IMDB_RATINGS_MISSING", lang))

            # !imdb help
            elif subcommand == "help":
                await message.channel.send(trans.get("MSG_IMDB_HELP", lang).replace("_", prefix))

            # If no argument is passed
            else:
                await message.channel.send(trans.get("MSG_IMDB_INVALID_USAGE", lang).format(prefix))


class NanoPlugin:
    name = "TMDb Commands"
    version = "18"

    handler = TMDb
    events = {
        "on_message": 10
        # type : importance
    }
