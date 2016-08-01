# coding=utf-8
import steamapi

__author__ = "DefaltSimon"

# Steam plugin for AyyBot

class Steam:
    def __init__(self, apikey):
        steamapi.core.APIConnection(api_key=apikey)

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