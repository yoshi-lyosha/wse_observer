import re
import sys
import model
import telebot
import traceback

from datetime import datetime
from config import telegram_token
from wse_observer import WSEObserver, get_data_from_config, get_logger

bot = telebot.TeleBot(telegram_token)
user_proxies, student_data = get_data_from_config()
logger = get_logger('info')
wsis = WSEObserver(logger)
wsis.proxies = user_proxies

# TODO: следующая итерация - весь доступный функционал по кнопкам


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


def is_registered_student(foo):
    def wrapper(message):
        tg_user = model.TelegramUser.select().where(model.TelegramUser.chat_id == message.chat.id)
        if tg_user:
            foo(message)
        else:
            bot.send_message(message.chat.id, 'You are not registered!')
    return wrapper


@bot.message_handler(commands=['test'])
def test(message):
    bot.send_message(message.chat.id, '{}'.format(message.chat.id))


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Welcome!\n\n"
                                      "You need to register first\n"
                                      "/registration wse_student_username wse_password\n\n"
                                      "wse_student_username - your username for Wall Street English;\n"
                                      "wse_password - your password")


@bot.message_handler(commands=['change_student_password'])
@is_registered_student
def change_password(message):
    password_pattern = r'/change_student_password (?P<wse_password>\S+)'
    password_in_message = re.search(password_pattern, message.text)
    if password_in_message:
        new_password = password_in_message.group('wse_password')
        wse_student = model.WSEStudent.get(id=model.TelegramUser.get(chat_id=message.chat.id).wse_student_id)
        wsis.update_student_password(wse_student, new_password)
        bot.send_message(message.chat.id, 'Student\'s password was changed successfully!')
    else:
        bot.send_message(message.chat.id, 'Try again.')


@bot.message_handler(commands=['change_student_username'])
@is_registered_student
def change_student_username(message):
    student_username_pattern = r'/change_student_username (?P<wse_username>\S+)'
    student_username_in_message = re.search(student_username_pattern, message.text)
    if student_username_in_message:
        student_new_username = student_username_in_message.group('wse_username')
        wse_student = model.WSEStudent.get(id=model.TelegramUser.get(chat_id=message.chat.id).wse_student_id)
        wsis.update_student_username(wse_student, student_new_username)
        bot.send_message(message.chat.id, 'Student\'s username was changed successfully!')
    else:
        bot.send_message(message.chat.id, 'Try again.')


@bot.message_handler(commands=['registration'])
def registration(message):
    tg_user = model.TelegramUser.select().where(model.TelegramUser.chat_id == message.chat.id)
    if tg_user:
        bot.send_message(message.chat.id, 'Already registered!')
    else:
        credentials_pattern = r'/registration (?P<wse_student_username>\S+) (?P<wse_password>\S+)'
        credentials_in_message = re.search(credentials_pattern, message.text)
        if credentials_in_message:
            new_student = wsis.registration(credentials_in_message.group('wse_student_username'),
                                            credentials_in_message.group('wse_password'))
            model.TelegramUser.create(wse_student=new_student, chat_id=message.chat.id)
            bot.send_message(message.chat.id, "A new student was registered!")
        else:
            bot.send_message(message.chat.id, 'Try again.')


@bot.message_handler(commands=['get_schedule'], content_types=["text"])
@is_registered_student
@exception_handler
def get_schedule(message):
    wse_student = model.WSEStudent.get(id=model.TelegramUser.get(chat_id=message.chat.id).wse_student_id)
    schedule_fields_list = wsis.get_schedule_fields_list(wse_student)

    outcoming_msg = str()  # заготовка для сообщения с расписанием
    for number, schedule_field in enumerate(schedule_fields_list, 1):
        # парсим строку со временем, считаем длительность занятия
        time_pattern = r'(?P<start_time>\d{2}:\d{2}) - (?P<finish_time>\d{2}:\d{2})'
        parsed_time = re.search(time_pattern, schedule_field['time'])
        start_time = datetime.strptime(parsed_time.group('start_time'), '%H:%M')
        finish_time = datetime.strptime(parsed_time.group('finish_time'), '%H:%M')
        schedule_field['lesson_duration_minutes'] = (finish_time - start_time).seconds // 60
        # выводим дату красиво
        beautiful_date = datetime.strptime(schedule_field['date'], '%d/%m/%Y').strftime('%A %d/%b')
        schedule_field['beautiful_date'] = beautiful_date

        outcoming_msg += '*********{}*********\n'.format(number)
        outcoming_msg += 'Type..........{}\n'.format(schedule_field['lesson_type'])
        outcoming_msg += 'Date..........{}\n'.format(schedule_field['beautiful_date'])
        outcoming_msg += 'Time..........{}\n'.format(start_time.strftime('%H:%M'))
        outcoming_msg += 'Duration......{} min\n'.format(schedule_field['lesson_duration_minutes'])
        outcoming_msg += 'Unit..........{}\n'.format(schedule_field['unit'])
        outcoming_msg += 'Description...{}\n\n'.format(schedule_field['description']) \
            if schedule_field['description'] else '\n'  # часто нет описания
    if outcoming_msg:
        bot.send_message(message.chat.id,
                         '```\n' + outcoming_msg + '```',
                         parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, 'Your schedule is empty')
