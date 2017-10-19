import re
import sys
import model
import telebot
import traceback

from telebot import types
from datetime import datetime
from wse_observer import WSEObserver, get_logger
from config import telegram_token, proxies, admin_id

bot = telebot.TeleBot(telegram_token)
logger = get_logger('info')
wsis = WSEObserver(logger)
wsis.proxies = proxies

user_dict = {}


# TODO: следующая итерация - обработать исключения, если креды невалидны


def send_exception_to_admin(foo):
    def wrapper(message):
        try:
            foo(message)
        except Exception:
            exc_info = sys.exc_info()
            bot.send_message(admin_id,
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
            registration_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            registration_markup.row('/start')
            bot.send_message(message.chat.id, 'You are not registered!', reply_markup=registration_markup)
    return wrapper


def generate_keyboard_markup():
    markup_for_new_user = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup_for_new_user.row('Get schedule')
    markup_for_new_user.row('Change username', 'Change password')
    return markup_for_new_user


@bot.message_handler(commands=['start'])
def registration(message):
    tg_user = model.TelegramUser.select().where(model.TelegramUser.chat_id == message.chat.id)
    if tg_user:
        bot.send_message(message.chat.id, 'You is already registered!', reply_markup=generate_keyboard_markup())
    else:
        bot.send_message(message.chat.id, 'Welcome to WSE Schedule observer!\n'
                                          'Firstly, you need to enter your credentials')
        msg = bot.reply_to(message, 'Enter your WSE username', reply_markup=types.ForceReply())
        bot.register_for_reply(msg, login_get_step)


def login_get_step(message):
    try:
        user_dict[message.chat.id] = {'wse_username': message.text}
        msg = bot.reply_to(message, 'Enter your WSE password', reply_markup=types.ForceReply())
        bot.register_for_reply(msg, password_get_step)
    except Exception as e:
        bot.reply_to(message, 'Failed: {}'.format(e))


def password_get_step(message):
    try:
        user_dict[message.chat.id]['wse_password'] = message.text
        new_student = wsis.registration(user_dict[message.chat.id]['wse_username'],
                                        user_dict[message.chat.id]['wse_password'])
        model.TelegramUser.create(wse_student=new_student, chat_id=message.chat.id)
        keyboard_markup = generate_keyboard_markup()
        bot.send_message(message.chat.id, "A new student was registered!", reply_markup=keyboard_markup)
    except Exception as e:
        bot.reply_to(message, 'Failed: {}'.format(e))


@bot.message_handler(regexp='Change password')
@is_registered_student
def change_password(message):
    msg = bot.reply_to(message, 'Enter new password', reply_markup=types.ForceReply())
    bot.register_for_reply(msg, change_password_step)


def change_password_step(message):
    new_password = message.text
    wse_student = model.WSEStudent.get(id=model.TelegramUser.get(chat_id=message.chat.id).wse_student_id)
    wsis.update_student_password(wse_student, new_password)
    bot.send_message(message.chat.id, 'Student\'s password was changed successfully!',
                     reply_markup=generate_keyboard_markup())


@bot.message_handler(regexp='Change username')
@is_registered_student
def change_student_username(message):
    msg = bot.reply_to(message, 'Enter new student username', reply_markup=types.ForceReply())
    bot.register_for_reply(msg, change_student_username_step)


def change_student_username_step(message):
    student_new_username = message.text
    wse_student = model.WSEStudent.get(id=model.TelegramUser.get(chat_id=message.chat.id).wse_student_id)
    wsis.update_student_username(wse_student, student_new_username)
    bot.send_message(message.chat.id, 'Student\'s username was changed successfully!',
                     reply_markup=generate_keyboard_markup())


@bot.message_handler(commands=['delete_student'])
@is_registered_student
def delete_student(message):
    tg_user = model.TelegramUser.get(chat_id=message.chat.id)
    wse_student = model.WSEStudent.get(id=tg_user.wse_student_id)
    wsis.delete_student_data(wse_student)
    tg_user.delete_instance()
    registration_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    registration_markup.row('/start')
    bot.send_message(message.chat.id, "Student deleted.", reply_markup=registration_markup)


@bot.message_handler(regexp='Get schedule')
@is_registered_student
def get_schedule(message):
    # TODO: функция слишком большая. пофиксить
    wse_student = model.WSEStudent.get(id=model.TelegramUser.get(chat_id=message.chat.id).wse_student_id)

    logging_in = wsis.login(wse_student)
    if logging_in:
        schedule_fields_list = wsis.get_schedule_fields_list(wse_student)
        if schedule_fields_list == 'Error':
            bot.send_message(message.chat.id, 'Unexpected error: contact the developer\n'
                                              '@yoshi-lyosha')
        else:
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
    else:
        bot.send_message(message.chat.id, 'Wrong username/password.\n'
                                          'Or error in this bot. If so: contact the developer\n'
                                          '@yoshi-lyosha')


if __name__ == '__main__':
    from telebot import apihelper
    from config import proxies
    apihelper.proxy = proxies
    bot.polling(none_stop=True)
