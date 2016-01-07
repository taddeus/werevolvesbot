#!/usr/bin/env python
import logging
from telegram import Updater
from config import token
from game import Game, Player

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

games = {}


def start(bot, update):
    reply(bot, update, '''
This is WerewolvesBot.
Possible commands are:
/help Show this help message.
/new <players> <werewolves> Start a new game.
/quit Quit the current game.
'''.strip())


def unknown(bot, update):
    reply(bot, update, 'Sorry, I didn\'t understand that command.')


def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))


def new(bot, update, args):
    chat_id = update.message.chat_id

    if chat_id in games:
        reply(bot, update, 'There is still a game in progress, use /quit to '
                           'end the current game first.')
    elif len(args) == 2 and args[0].isdigit() and args[1].isdigit():
        reply(bot, update, 'Starting a new game with %d players of which %d '
                           'are werewolves.')
        games[chat_id] = Game(int(args[0]), int(args[1]))
    else:
        reply(bot, update, 'Please specify the number of players and '
                           'werevolves.')


def reply(bot, update, message):
    bot.sendMessage(chat_id=update.message.chat_id, text=message)


def quit(bot, update, args):
    chat_id = update.message.chat_id

    if chat_id in games:
        del games[chat_id]
        reply(bot, update, 'Removed current game.')
    else:
        reply(bot, update, 'No game in progress.')


if __name__ == '__main__':
    updater = Updater(token)
    dp = updater.dispatcher

    dp.addTelegramCommandHandler('start', start)
    dp.addTelegramCommandHandler('help', start)
    dp.addTelegramCommandHandler('new', new)
    dp.addTelegramCommandHandler('quit', quit)
    dp.addUnknownTelegramCommandHandler(unknown)
    dp.addErrorHandler(error)

    updater.start_polling()
    updater.idle()
