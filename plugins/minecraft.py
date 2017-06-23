# coding=utf-8
import logging
from json import loads, JSONDecodeError

import aiohttp
from discord import Client, Message

from data.stats import MESSAGE, WRONG_ARG, IMAGE_SENT
from data.utils import is_valid_command

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# CONSTANTS
ITEM_ID_PAIR = 1
ITEM_ID = 2
ITEM_NAME = 3

commands = {
    "_mc": {"desc": "Searches for items and displays their details", "use": "[command] [item name or id:meta]", "alias": "_minecraft"},
    "_minecraft": {"desc": "Searches for items and displays their details", "use": "[command] [item name or id:meta]", "alias": "_mc"},
}

valid_commands = commands.keys()


class McItems:
    url = "http://minecraft-ids.grahamedgecombe.com/items.json"

    def __init__(self, loop):
        # Gets a fresh copy of items at each startup.
        self.data = None
        loop.run_until_complete(self.request_data())

    async def request_data(self):
        log.info("Requesting JSON data from minecraft-ids.grahamedgecombe.com")
        async with aiohttp.ClientSession() as session:
            async with session.get(McItems.url) as resp:
                raw_data = await resp.text()

                try:
                    self.data = loads(raw_data)
                except JSONDecodeError as e:
                    log.critical("Could not load JSON: {}".format(e))


    def id_to_data(self, num):
        if len(str(num).split(":")) > 1:
            idd = str(num).split(":")[0]
            meta = str(num).split(":")[1]
        else:
            idd = num
            meta = 0

        for item in self.data:
            if int(item.get("type")) == int(idd):
                if int(item.get("meta")) == int(meta):
                    return item

    def name_to_data(self, name):
        for c, item in enumerate(self.data):
            if item.get("name").lower() == str(name).lower():
                return self.data[c]

    def group_to_list(self, group):
        items = []
        for item in self.data:
            if str(item.get("type")) == str(group):
                items.append(item)

        return items

    def id_to_pic(self, num):
        if num > len(self.data):
            return None

        data = self.data[num]

        with open("plugins/mc/{}-{}.png".format(num, data.get("metadata"))) as pic:
            return pic

    def get_group_by_name(self, name):
        data = None

        # Group(ify)
        if str(name).lower() == "wool":
            data = self.group_to_list(35)
        elif str(name).lower() == "stone":
            data = self.group_to_list(1)
        elif str(name).lower() == "wood plank":
            data = self.group_to_list(5)
        elif str(name).lower() == "sapling":
            data = self.group_to_list(6)
        elif str(name).lower() == "sand":
            data = self.group_to_list(12)
        elif str(name).lower() == "wood":
            data = self.group_to_list(17)
        elif str(name).lower() == "leaves":
            data = self.group_to_list(18)
        elif str(name).lower() == "sponge":
            data = self.group_to_list(19)
        elif str(name).lower() == "sandstone":
            data = self.group_to_list(24)
        elif str(name).lower() == "flower":
            data = self.group_to_list(38)
        elif str(name).lower() == "double slab":
            data = self.group_to_list(43)
        elif str(name).lower() == "slab":
            data = self.group_to_list(44)
        elif str(name).lower() == "stained glass":
            data = self.group_to_list(95)
        elif str(name).lower() == "monster egg":
            data = self.group_to_list(97)
        elif str(name).lower() == "stone brick":
            data = self.group_to_list(98)
        elif str(name).lower() == "double wood slab":
            data = self.group_to_list(125)
        elif str(name).lower() == "wood slab":
            data = self.group_to_list(126)
        elif str(name).lower() == "quartz block":
            data = self.group_to_list(155)
        elif str(name).lower() == "stained clay":
            data = self.group_to_list(159)
        elif str(name).lower() == "stained glass pane":
            data = self.group_to_list(160)
        elif str(name).lower() == "prismarine":
            data = self.group_to_list(168)
        elif str(name).lower() == "carpet":
            data = self.group_to_list(171)
        elif str(name).lower() == "plant":
            data = self.group_to_list(175)
        elif str(name).lower() == "sandstone":
            data = self.group_to_list(179)
        elif str(name).lower() == "fish":
            data = self.group_to_list(349)
        elif str(name).lower() == "dye":
            data = self.group_to_list(351)
        elif str(name).lower() == "egg":
            data = self.group_to_list(383)
        elif str(name).lower() == "head":
            data = self.group_to_list(397)

        return data


class Minecraft:
    def __init__(self, **kwargs):
        self.handler = kwargs.get("handler")
        self.nano = kwargs.get("nano")
        self.client = kwargs.get("client")
        self.stats = kwargs.get("stats")
        self.loop = kwargs.get("loop")
        self.trans = kwargs.get("trans")

        self.mc = McItems(self.loop)

    async def on_message(self, message, **kwargs):
        prefix = kwargs.get("prefix")
        client = self.client
        mc = self.mc

        trans = self.trans
        lang = kwargs.get("lang")

        assert isinstance(client, Client)
        assert isinstance(message, Message)

        if not is_valid_command(message.content, valid_commands, prefix=prefix):
            return
        else:
            self.stats.add(MESSAGE)

        def startswith(*msg):
            for a in msg:
                if message.content.startswith(a):
                    return True

            return False

        if startswith(prefix + "mc", prefix + "minecraft"):
            if startswith(prefix + "mc help", prefix + "minecraft help"):
                # Help message
                await client.send_message(message.channel, trans.get("MSG_MC_HELP", lang).replace("_", prefix))
                return

            elif startswith(prefix + "mc "):
                item_name = message.content[len(prefix + "mc "):]
            elif startswith(prefix + "minecraft "):
                item_name = message.content[len(prefix + "minecraft "):]

            else:
                return

            # Determines if arg is id or name
            if len(str(item_name).split(":")) > 1:
                item_type = ITEM_ID_PAIR

            else:
                try:
                    int(item_name)
                    item_type = ITEM_ID
                except ValueError:
                    item_type = ITEM_NAME

            try:
                # Requests item data from minecraft module
                if item_type == ITEM_ID_PAIR or item_type == ITEM_ID:
                    data = mc.id_to_data(item_name)
                else:
                    # Check for groupings
                    if mc.get_group_by_name(item_name):
                        data = mc.get_group_by_name(item_name)

                    else:
                        data = mc.name_to_data(str(item_name))
            except ValueError:
                await client.send_message(message.channel, trans.get("ERROR_INVALID_CMD_ARGUMENTS", lang))
                return

            if not data:
                await client.send_message(message.channel, trans.get("MSG_MC_NO_ITEMS", lang))
                self.stats.add(WRONG_ARG)
                return

            if not isinstance(data, list):
                details = trans.get("MSG_MC_DETAILS", lang).format(data.get("name"), data.get("type"), data.get("meta"))

                # Details are uploaded simultaneously with the picture
                try:
                    with open("plugins/mc/{}-{}.png".format(data.get("type"), data.get("meta") or 0), "rb") as pic:
                        await client.send_file(message.channel, pic, content=details)
                        self.stats.add(IMAGE_SENT)
                except FileNotFoundError:
                    await client.send_message(message.channel, details)
                    self.stats.add(IMAGE_SENT)

            else:
                combined = []
                for item in data:
                    details = trans.get("MSG_MC_DETAILS", lang).format(item.get("name"), item.get("type"), item.get("meta"))
                    combined.append(details)

                await client.send_message(message.channel, "".join(combined))


class NanoPlugin:
    name = "Minecraft Commands"
    version = "0.1.2"

    handler = Minecraft
    events = {
        "on_message": 10
        # type : importance
    }
