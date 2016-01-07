#!/usr/bin/env python
import logging
import random
from telegram import Updater
from config import token
from game import Game, Player
import sys
from random import randint

logger = logging.getLogger()
logger.addHandler(logging.FileHandler("/dev/stderr"))
logger.setLevel(logging.DEBUG)
logger.info("starting...")

def reply(bot, update, message):
    bot.sendMessage(chat_id=update.message.chat_id, text=message, parse_mode="Markdown")
def handle(bot, msglist):
    for chat_id, text in msglist:
        bot.sendMessage(chat_id=chat_id, text=text, parse_mode="Markdown")


class Werewolf(object):
    pass
class Seer(object):
    pass
class Witch(object):
    pass
class Villager(object):
    pass

all_roles = {
    'seer' : Seer,
    'witch' : Witch,
    'werewolf' : Werewolf,
    'villager' : Villager,
}
base_roles = ['villager', 'werewolf']
special_roles = ['seer', 'witch']

class Game(object):
    # The game object is protocol-agnostic
    # each handler returns a list of message to send and to whom
    def __init__(self, key):
        self.started = False
        self.key = key
        self.pids = {}
        self.players = {}
        self.nplayers = 0

        self.nr_werewolves = None # means default
        self.special_roles = None # means default

    def sanitize(self):
        nplayers = len(self.pids)
        if self.nr_werewolves is None:
            self.nr_werewolves = (nplayers // 8) + 1
        yield from self.broadcast("There are %d werewolves in this game." % self.nr_werewolves)
        
        if self.special_roles is None:
            self.special_roles = set(['seer'])
        for role in self.special_roles:
            yield from self.broadcast("There is a %s in this game." % role)
            
    def broadcast(self, msg):
        for (chat_id, _, _) in self.players.values():
            yield (chat_id, msg)

    def select_roles(self):
        effective_roles = ['werewolf'] * self.nr_werewolves
        effective_roles += list(self.special_roles)
        if len(effective_roles) < self.nplayers:
            effective_roles += ['villager'] * (self.nplayers - len(effective_roles))
        random.shuffle(effective_roles)
        logging.debug("Effective roles: %s", repr(effective_roles))

        for pid in self.pids.values():
            role = effective_roles[pid - 1]
            pd = self.players[pid][2]
            pd['role'] = all_roles[role]()
            pd['rolename'] = role
            yield (self.players[pid][0], "You are a %s." % role)
            
    def go(self):
        self.started = True
        yield from self.sanitize()
        yield from self.broadcast("The game has started.")
        yield from self.select_roles()
        
    def ready(self, chat_id):
        assert chat_id in self.pids

        pid = self.pids[chat_id]
        p = self.players[pid]

        p[2]['ready'] = True
        
        for opid, (ochat_id, _, _) in self.players.items():
            if opid == pid: continue
            yield (ochat_id, "Player %d is ready." % pid)
            
        all_ready = all((x[2]['ready'] for x in self.players.values()))
        if all_ready:
            yield from self.go()
        else:
            yield (chat_id, "Waiting for other players...")
        
    def add_player(self, chat_id, name):
        logger.info("New player: %s %s", chat_id, name)
        if chat_id in self.pids:
            yield (chat_id, "You are player %d in this game." % self.pids[chat_id])
            return

        self.nplayers += 1
        pid = self.nplayers

        self.pids[chat_id] = pid
        self.players[pid] = (chat_id, name, {'ready':False})

        msg = "Hello %s! You are player %d in this game." % (name, pid)
        for opid, (ochat_id, oname, _) in self.players.items():
            if opid == pid: continue
            yield (ochat_id, "Player %d (%s) has joined." % (pid, name))
            msg += "\nPlayer %d is %s." % (opid, oname)
            
        yield (chat_id, msg)
    
class GameDB(object):
    def __init__(self):
        self.db = {}
        self.active_games = {}

    def __getitem__(self, a):
        gid, key = a
        gm = self.db.get(gid, None)
        if gm is None or gm.key != key:
            return None
        return gm
        
    def make(self, key):
        for i in range(100):
            gid = hex(randint(0, 100000))[2:]
            if gid in self.db:
                continue
        if gid in self.db:
            return None, None
        gm = Game(key)
        self.db[gid] = gm
        return (gid, gm)

    def associate(self, chat_id, gm):
        self.active_games[chat_id] = gm

    def current(self, chat_id):
        return self.active_games.get(chat_id, None)

games = GameDB()

def start(bot, update, args):
    reply(bot, update, '''
This is WerewolvesBot.
Possible commands are:
/help Show this help message.
/new <password> Start a new game.
/join <key> <password> Join a game already created.
/ready Say you're ready to start.
'''.strip())
    logger.info(repr(args))

def unknown(bot, update):
    reply(bot, update, 'Sorry, I didn\'t understand that command.')

def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))

def new(bot, update, args):
    if len(args) == 0:
        reply(bot, update, "Use /new <password> to create a new game.")
        return

    pw = ' '.join(args)
    gid, gm = games.make(pw)
    if gid is None:
        reply(bot, update, "Bot is too busy, try again later.")
        return
    
    reply(bot, update, 'Game created, ask players to type: `/join %s %s`' % (gid, pw))
    reply(bot, update, 'Use /join too if you want to participate in the game too.')

def ready(bot, update):
    gm = games.current(update.message.chat_id)
    if gm is None:
        reply(bot, update, "You have not joined any game yet.")
        return

    handle(bot, gm.ready(update.message.chat_id))
    
def join(bot, update, args):
    if len(args) < 2:
        reply(bot, update, "Use /join <key> <password> to join a game.")
        return

    gid = args[0]
    pw = ' '.join(args[1:])

    gm = games[gid, pw]
    if gm is None:
        reply(bot, update, "No game found with this key or password.")
    else:
        chat_id = update.message.chat_id
        name = (update.message.from_user.first_name + " " + update.message.from_user.last_name).strip()
        handle(bot, gm.add_player(chat_id, name))
        games.associate(chat_id, gm)
    

def msg(bot, update):
    pass

if __name__ == '__main__':
    updater = Updater(token)
    dp = updater.dispatcher

    dp.addTelegramCommandHandler('start', start)
    dp.addTelegramCommandHandler('help', start)
    dp.addTelegramCommandHandler('new', new)
    dp.addTelegramCommandHandler('join', join)
    dp.addTelegramCommandHandler('ready', ready)
    dp.addUnknownTelegramCommandHandler(unknown)
    dp.addErrorHandler(error)
    dp.addTelegramMessageHandler(msg)
    
    updater.start_polling()
    updater.idle()
