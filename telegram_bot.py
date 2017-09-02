import telebot
import sys
import traceback
from config import telegram_token
from wsis_observer import Wsis, get_data_from_config, get_logger

bot = telebot.TeleBot(telegram_token)
user_proxies, user_data = get_data_from_config()
logger = get_logger('info')
wsis = Wsis(logger)
wsis.proxies = user_proxies


def exception_handler(foo):
    def wrapper(message):
        try:
            foo(message)
        except Exception:
            exc_info = sys.exc_info()
            bot.send_message(message.chat.id,
                             '```\n{}```'.format(''.join(traceback.format_exception(*exc_info))),
                             parse_mode='Markdown')
            del exc_info
    return wrapper


@bot.message_handler(commands=['get_schedule'], content_types=["text"])
@exception_handler
def get_schedule(message):
    wsis.login(user_data)
    schedule_list = wsis.get_schedule()
    wsis.logout()

    outcoming_msg = str()
    for number, schedule_field in enumerate(schedule_list, 1):
        outcoming_msg += '********{}********\n'.format(number)
        outcoming_msg += 'Тип...............{}\n'.format(schedule_field['lesson_type'])
        outcoming_msg += 'Дата..............{}\n'.format(schedule_field['date'])
        outcoming_msg += 'Время.............{}\n'.format(schedule_field['time'])
        outcoming_msg += 'Занятие, уровни...{}\n'.format(schedule_field['unit'])
        outcoming_msg += 'Описание занятия..{}\n\n'.format(schedule_field['description'])

    bot.send_message(message.chat.id,
                     '```\n' + outcoming_msg + '```',
                     parse_mode='Markdown')
