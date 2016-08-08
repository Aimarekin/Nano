# coding=utf-8

from discord import Client, Game
from asyncio import sleep
from random import shuffle

game_list = [
    "(formerly AyyBot)",
    "HI MOM!",
    "@Nano",
    "fun games",
    "with discord.py",
    "with DefaltSimon",
    "with Discord",
    "with python",
    "get a 'nano.invite'"
]

async def roll_statuses(client, time=3600):  # 3600 = 1 hour
    if not isinstance(client, Client) or not isinstance(time, int):
        assert False

    await client.wait_until_ready()

    # Shuffle list in place
    shuffle(game_list)

    await sleep(time)

    async def next_game(gm):
        await client.change_status(game=Game(name=str(gm)))

    while not client.is_closed:
        for game in game_list:

            if client.is_closed:
                break

            await next_game(game)
            await sleep(time)

        # Reshuffle when done
        shuffle(game_list)