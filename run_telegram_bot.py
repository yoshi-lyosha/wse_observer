from telegram_bot import bot
from telebot import apihelper
from config import proxies

if __name__ == '__main__':
    apihelper.proxy = proxies
    bot.polling(none_stop=True)
