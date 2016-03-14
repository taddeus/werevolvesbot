#!/usr/bin/env python
import logging
import random
import telegram
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
    for entry in msglist:
        if len(entry) < 3:
            bot.sendMessage(chat_id=entry[0], text=entry[1], parse_mode="Markdown")
        else:
            rm = telegram.ReplyKeyboardMarkup(entry[2], one_time_keyboard=True)
            bot.sendMessage(chat_id=entry[0], text=entry[1], parse_mode="Markdown", reply_markup=rm)

class Werewolf(object):
    pass
class Seer(object):
    pass
class Witch(object):
    pass
class Villager(object):
    pass

base_roles = ['villager', 'werewolf']
special_roles = ['seer', 'witch']

class Player(object):
    def __init__(self, pid, chat_id, name):
        self.pid = pid
        self.chat_id = chat_id
        self.name = name
        self.initialize()

    def initialize(self):
        self.alive = True
        self.ready = False
        self.role = None        

        
    def __str__(self):
        return "Player %d (%s)" % (self.pid, self.name)

class Game(object):
    # The game object is protocol-agnostic
    # each handler returns a list of message to send and to whom

    # cycle is:
    # - initialize
    # - let players configure or join (leave not supported yet), wait for ready
    # - go, select roles, announce roles
    
    def __init__(self, key):
        self.key = key
        self.pids = {}
        self.players = {}
        self.nplayers = 0

        self.nr_werewolves = None # means default
        self.special_roles = None # means default

        self.initialize()
        
    def initialize(self):
        self.started = False
        for p in self.players.values():
            p.initialize()
        
    def sanitize(self):
        if self.nr_werewolves is None:
            self.nr_werewolves = (self.nplayers // 8) + 1
        yield from self.broadcast("There are %d werewolves in this game." % self.nr_werewolves)
        
        if self.special_roles is None:
            self.special_roles = set(['seer'])
        for role in self.special_roles:
            yield from self.broadcast("There is a %s in this game." % role)
            
    def broadcast(self, msg):
        for p in self.players.values():
            yield (p.chat_id, msg)

    def broadcast_others(self, pid, msg):
        yield from self.broadcast_if(lambda p: p.pid != pid, msg)
            
    def broadcast_if(self, cnd, msg):
        for opid, op in self.players.items():
            if cnd(op):
                yield (op.chat_id, msg)

    def select_roles(self):
        
        effective_roles = ['werewolf'] * self.nr_werewolves
        effective_roles += list(self.special_roles)
        if len(effective_roles) < self.nplayers:
            effective_roles += ['villager'] * (self.nplayers - len(effective_roles))
        effective_roles = effective_roles[:self.nplayers]
        random.shuffle(effective_roles)
        logging.debug("Effective roles: %s", repr(effective_roles))

        for pid in self.pids.values():
            role = effective_roles[pid - 1]
            p = self.players[pid]
            p.role = role
            yield (p.chat_id, "You are a %s." % role)

    def conclude(self):
        msg = []
        for p in self.players.values():
            msg.append("%s was a %s." % (p, p.role))
        yield from self.broadcast('\n'.join(msg))
        
        self.initialize()
        yield from self.broadcast("A new game is ready to start. Configure, invite new players or enter `/ready`.")
            
    def check_state(self):
        # "If at any time the number of alive wolves is equal to or greater
        # than the number of alive non-wolves, the wolves win. If there are
        # no wolves left alive, the villagers win."
        alive = sum((1 for p in self.players.values() if p.alive))
        nr_wolves = sum((1 for p in self.players.values() if p.alive and p.role == 'werewolf'))
        if nr_wolves >= (alive - nr_wolves):
            yield from self.broadcast("The game has ended: the werewolves win.")
            yield from self.conclude()
        if nr_wolves == 0:
            yield from self.broadcast("The game has ended: the villagers win.")
            yield from self.conclude()
        
    def vote(self, chat_id, pid):
        pass
            
    def go(self):
        self.started = True
        yield from self.sanitize()
        yield from self.broadcast("The game has started.")
        yield from self.select_roles()
        yield from self.check_state()
        
    def ready(self, chat_id):
        assert chat_id in self.pids

        pid = self.pids[chat_id]
        p = self.players[pid]

        p.ready = True
        
        yield from self.broadcast_others(pid, "%s is ready." % p)
            
        all_ready = all((p.ready for p in self.players.values()))
        if all_ready:
            yield from self.go()
        else:
            yield (chat_id, "Waiting for other players...")

    def is_started(self):
        return self.started
            
    def add_player(self, chat_id, name):

        assert chat_id not in self.pids

        self.nplayers += 1
        pid = self.nplayers

        self.pids[chat_id] = pid
        
        p = Player(pid, chat_id, name)
        self.players[pid] = p

        logger.info("New player: %s", p)

        msg = "Hello %s! You are player %d in this game." % (name, pid)
        for opid, op in self.players.items():
            if opid == pid: continue
            yield (p.chat_id, "%s has joined." % p)
            msg += "\n%s is already there." % op
            
        yield (chat_id, msg)
        yield (chat_id, "Enter `/ready` when you are, but only after all players have joined.", [['/ready']])

    def player_dies(self, pid):
        p = self.players[pid]
        assert p.alive
        p.alive = False
        yield (p.chat_id, "You have died.")
        yield from self.broadcast_others(pid, "%s has died." % p)
        
    
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

    def deassociate(self, chat_id):
        del self.active_games[chat_id]
        
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
/1 /2 /3 ... vote for player (during game only).
'''.strip())
    logger.info(repr(args))

def unknown(bot, update):
    assert update.message.text[0] == '/'
    cmd = update.message.text.split(' ', 1)[0][1:]
    pid = None
    try:
        pid = int(cmd)
    except:
        pass
    if pid is None:
        reply(bot, update, 'Sorry, I didn\'t understand that command.')
        return
        
    gm = games.current(update.message.chat_id)
    if gm is None:
        reply(bot, update, "You have not joined any game yet.")
        return
    if not gm.is_started():
        reply(bot, update, "Game has not started yet.")
        return

    handle(bot, gm.vote(update.message.chat_id, pid))

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
    reply(bot, update, 'Use `/join` too if you want to participate yourself.')

def ready(bot, update):
    gm = games.current(update.message.chat_id)
    if gm is None:
        reply(bot, update, "You have not joined any game yet.")
        return
    if gm.is_started():
        reply(bot, update, "Game already started.")
        return

    handle(bot, gm.ready(update.message.chat_id))

def leave(bot, update):
    chat_id = update.message.chat_id
    gm = games.current(chat_id)
    if gm is None:
        reply(bot, update, "You're not currently in a game.")
    else:
        handle(bot, gm.player_leaves(chat_id))
        games.deassociate(chat_id)
    
def join(bot, update, args):
    if len(args) < 2:
        reply(bot, update, "Use /join <key> <password> to join a game.")
        return

    gm = games.current(update.message.chat_id)
    if gm is not None:
        reply(bot, update, "You are already in a game. Use `/leave` before you join a new game.")
        return
    
    gid = args[0]
    pw = ' '.join(args[1:])

    gm = games[gid, pw]
    if gm is None:
        reply(bot, update, "No game found with this key or password.")
    else:
        if gm.is_started():
            reply(bot, update, "Game already started, cannot join any more.")
            return
        chat_id = update.message.chat_id
        name = (update.message.from_user.first_name + " " + update.message.from_user.last_name).strip()
        handle(bot, gm.add_player(chat_id, name))
        games.associate(chat_id, gm)
    

def msg(bot, update):
    bot.sendMessage(update.message.chat_id, text="hai", reply_markup=telegram.ReplyKeyboardMarkup([["/1 td", "/2 foo"]]))

if __name__ == '__main__':
    updater = Updater(token)
    dp = updater.dispatcher

    dp.addTelegramCommandHandler('start', start)
    dp.addTelegramCommandHandler('help', start)
    dp.addTelegramCommandHandler('new', new)
    dp.addTelegramCommandHandler('join', join)
    dp.addTelegramCommandHandler('ready', ready)
    dp.addTelegramCommandHandler('leave', leave)
    dp.addUnknownTelegramCommandHandler(unknown)
    dp.addErrorHandler(error)
    dp.addTelegramMessageHandler(msg)
    
    updater.start_polling()
    updater.idle()
