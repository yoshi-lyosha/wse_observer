import requests
from bs4 import BeautifulSoup as BeS
import re
import os
import sys
import errno
import json
import logging
from collections import namedtuple


# TODO: оптимизировать количество переходов на сайт. мне не нравится что это занимает так много времени
# TODO: узнать сколько живёт сессия
# TODO: Логгирование для дебаг-режима - в стдаут, продакшн - в файл
# TODO: искать айди сессии не в хтмл, а в куках сразу
# TODO: кэшировать что-нибудь по-возможности
# TODO: рефактор под многопользовательский режим. лоадить куки под конкретного юзера. все реквесты под конкретных.


class CookieStorage:
    @staticmethod
    def cookie_load():
        """
        Загружает словарь с куками из файлика

        :return:
        cookie - словарь с куками
        """
        if not os.path.exists('cookie.json'):
            logging.debug('Создаём файл для кук')
            with open('cookie.json', 'w') as cookie_file:
                json.dump({}, cookie_file)
        logging.debug('Подгружаем куки')
        with open('cookie.json') as cookie_file:
            cookie = json.load(cookie_file)
        return cookie

    @staticmethod
    def cookie_save(cookie):
        """Сохраняет словарь с куками из файлика

        :param cookie: словарь с куками
        """
        logging.debug('Сохраняем куки')
        with open('cookie.json', 'w') as cookie_file:
            json.dump(cookie, cookie_file)
        return None


class Wsis:
    """
    Класс для логина/логаута/получения расписания с ресурса под названием Wall Street English

    """
    proxies = {}
    wsis_index_url = 'http://www.wsistudents.com/'
    wsis_personal_page_url = 'http://www.wsistudents.com/splash.jhtml'
    redirect_page_url = 'http://www.wsistudents.com/switch2supersds.jhtml'
    schedule_page_url = 'http://sdszone1.e-wsi.com//inhome/review.jhtml'
    wsis_login_data = {
        '_D:username': ' ',
        '_D:password': ' ',
        'reqFromEwsi0': 'ewsi',
        'redirecturl': '',
        '/atg/userprofiling/ProfileFormHandler.loginSuccessURL': 'splash.jhtml',
        '_D:/atg/userprofiling/ProfileFormHandler.loginSuccessURL': ' ',
        '/atg/userprofiling/ProfileFormHandler.login': 'Accept',
        '_D:/atg/userprofiling/ProfileFormHandler.login': ' '
    }

    def __init__(self, _logging):
        self.logging = _logging

    def _get_login_data(self, user_login_data):
        self.logging.debug('Генерим данные для логина')
        login_data = dict(self.wsis_login_data)
        login_data.update(user_login_data)
        return login_data

    def _get_login_url(self, index_html):
        """
        Получает урл для логина из action поля form из html

        :param index_html: хтмл для обработки
        :return: агрумент action поля form
        """
        self.logging.debug('Извлекаем поле form action из index.html')
        index_soup = BeS(index_html, 'html.parser')
        form_action_field = index_soup.form.get('action')
        login_url = self.wsis_index_url + form_action_field
        return login_url

    def _post_login_request(self, login_url, login_data):
        """
        Отправляет POST реквест для логина
        :param login_url: урл для логина
        :param login_data: словарь с информацией для логина
        :return: POST реквест логина
        """
        self.logging.debug('Совершаем POST-запрос на логин')
        login_post_request = requests.post(login_url, proxies=self.proxies, data=login_data)
        return login_post_request

    def _login_and_save_session_id_cycle(self, login_data):
        """
        Цикл из трёх попыток логина и сохранения кук
        :param login_data: словарь с информацией для логина
        :return: True если логин удался, False если нет
        """
        for try_to_login in range(1, 4):
            self.logging.debug('Пытаемся залогиниться, попытка {} из 3'.format(try_to_login))
            index_page_request = requests.get(self.wsis_index_url, proxies=self.proxies)
            index_html = index_page_request.text
            login_post_request = self._post_login_request(self._get_login_url(index_html), login_data)
            if login_post_request.status_code == 200:
                self.logging.debug('POST запрос для логина прошёл успешно')
                cookie = dict(index_page_request.cookies)
                CookieStorage.cookie_save(cookie)
                return True
            else:
                self.logging.warning('Логин не удался. Статус запроса {}'.format(login_post_request.status_code))
        else:
            self.logging.error('Не удалось залогиниться')
            return False

    def login(self, user_login_data):
        """
        Функция для логина на сайт
        :param user_login_data: словарь с кредами юзера для логина
        :return: True если логин удался, False если нет
        """
        self.logging.info('Начинаем логиниться')
        self.logging.debug('Проверяем не залогинен ли уже')
        personal_page_request = self._get_personal_page_request()
        if personal_page_request.status_code == 200:
            self.logging.info('Уже залогинен')
            return True
        else:
            self.logging.debug('Не залогинен')
            login_data = self._get_login_data(user_login_data)
            self._login_and_save_session_id_cycle(login_data)
            if self._get_personal_page_request().status_code == 200:
                self.logging.info('Логин прошёл успешно')
                return True
            else:
                self.logging.error('Логин не удался, возможно, данные указаны неправильно')
                return False

    def _get_personal_page_request(self):
        """
        GET реквест перехода на персональную страницу ресурса WSIStudents
        :return: реквест
        """
        self.logging.debug('Запрос персональной страницы')
        cookie = CookieStorage.cookie_load()
        personal_page_request = requests.get(self.wsis_personal_page_url, proxies=self.proxies, cookies=cookie)
        return personal_page_request

    def _get_logout_url(self):
        """
        Получить logout_url с персональной страницы пользователя
        :return: logout_url либо None
        """
        self.logging.debug('Получаем из персональной страницы урл для разлогина')
        personal_page_request = self._get_personal_page_request()
        if personal_page_request.status_code == 200:
            final_html = personal_page_request.content
            final_soup = BeS(final_html, 'html.parser')
            logout_url = self.wsis_index_url + final_soup.find(id="headerWrapper").a.get('href')
            self.logging.debug('Урл для разлогина получен')
            return logout_url
        else:
            self.logging.error('Нет доступа к персональной странице для разлогина')
            return None

    def _post_logout_request(self, logout_url):
        """
        Отправляет POST реквест для логаута
        :param logout_url: урл для логаута
        :return: POST реквест логаута
        """
        self.logging.debug('Совершаем POST-запрос на логаут')
        cookie = CookieStorage.cookie_load()
        logout_post_request = requests.post(logout_url, proxies=self.proxies, cookies=cookie)
        return logout_post_request

    def _logout_cycle(self):
        """
        Цикл из трёх попыток логаута
        :return: True если логаут прошёл, False если нет
        """
        for try_to_logout in range(1, 4):
            self.logging.debug('Пытаемся разлогиниться, попытка {} из 3'.format(try_to_logout))

            logout_url = self._get_logout_url()
            logout_post_request = self._post_logout_request(logout_url)
            if logout_post_request.status_code == 200:
                self.logging.debug('POST запрос для логаута прошёл успешно')
                return True
            else:
                self.logging.warning('Логаут не удался. Статус запроса {}'.format(logout_post_request.status_code))
        else:
            self.logging.debug('Не удалось сделать логаут')
            return False

    def logout(self):
        """
        Функция для логаута из ресурс
        :return: True если логаут прошёл, False если нет
        """
        self.logging.info('Начинаем логаут')
        self.logging.debug('Проверяем не разлогинен ли уже')
        personal_page_request = self._get_personal_page_request()
        if personal_page_request.status_code == 200:
            self.logging.debug('Залогинен, начинаю логаут')
            logout_result = self._logout_cycle()
            if logout_result:
                self.logging.info('Логаут прошёл успешно')
            else:
                self.logging.error('Не удалось сделать логаут')
        else:
            self.logging.info('Уже разлогинен')
            return True

    def _get_schedule_page_request(self):
        """
        GET реквест перехода на страницу с расписанием ресурса WSIStudents
        :return: реквест
        """
        self.logging.debug('Запрос страницы с расписанием')
        cookie = CookieStorage.cookie_load()
        redirect_page_request = requests.get(self.redirect_page_url, proxies=self.proxies, cookies=cookie)
        if redirect_page_request.status_code == 200:
            redirect_page_soup = BeS(redirect_page_request.text, 'html.parser')
            shedule_cookie = {}
            redirect_script = redirect_page_soup.find('script')
            var_redirectsessionid_pattern = r'var redirectSessionId = \'(.*)\''
            shedule_cookie['JSESSIONID'] = re.search(var_redirectsessionid_pattern, redirect_script.text).group(1)
            self.logging.debug('Получены куки для получения расписания')
            schedule_page_request = requests.get(self.schedule_page_url, proxies=self.proxies, cookies=shedule_cookie)
            return schedule_page_request
        else:
            self.logging.error('Запрос страницы с расписанием прошёл неуспешно :с')
            return False

    def _get_schedule_from_html(self, schedule_html):
        """
        Функция для парсинга расписания в html
        :param schedule_html: хтмл страница с расписанием
        :return:
        """
        self.logging.debug('Парсим страницу с расписанием')

        schedule_soup = BeS(schedule_html, 'html.parser')
        schedule_table = schedule_soup.body.find_all('table')[2]
        tr_list = schedule_table.find_all('tr')
        schedule = []

        for tr in tr_list[1:-1]:
            schedule_field = dict()

            td_list = tr.find_all('td')

            lesson_pattern = r'(\w+)'
            date_pattern = r'(\d{2}/\d{2}/\d{4})'
            time_pattern = r'(\d{2}:\d{2}\s* - \s*\d{2}:\d{2})'
            unit_pattern = r'([\w\+]+)\s?,?'
            description_pattern = r'(\w+)+'

            lesson_type = re.findall(lesson_pattern, td_list[1].text.replace('\n', ''))
            date = re.findall(date_pattern, td_list[2].text.replace('\n', ''))
            time = re.findall(time_pattern, td_list[2].text.replace('\n', ''))
            unit = re.findall(unit_pattern, td_list[3].text.replace('\n', ''))
            description = re.findall(description_pattern, td_list[4].text.replace('\n', ''))

            schedule_field['lesson_type'] = ' '.join(word for word in lesson_type)
            schedule_field['date'] = ' '.join(word for word in date)
            schedule_field['time'] = ' '.join(word for word in time)
            schedule_field['unit'] = ' '.join(word for word in unit)
            schedule_field['description'] = ' '.join(word for word in description)

            schedule.append(schedule_field)
        return schedule

    def _print_schedule(self, schedule_list):
        self.logging.debug('Печатаем расписание')

        for number, schedule_field in enumerate(schedule_list, 1):
            print('********{}********'.format(number))
            print('Тип...............{}'.format(schedule_field['lesson_type']))
            print('Дата..............{}'.format(schedule_field['date']))
            print('Время.............{}'.format(schedule_field['time']))
            print('Занятие, уровни...{}'.format(schedule_field['unit']))
            print('Описание занятия..{}'.format(schedule_field['description']))

    def get_schedule(self):
        """
        Функция для получения расписания
        :return:
        """
        self.logging.info('Получаем расписание')
        schedule_page_request = self._get_schedule_page_request()
        if not schedule_page_request:
            return False

        elif schedule_page_request.status_code == 200:
            schedule_html = schedule_page_request.text
            schedule = self._get_schedule_from_html(schedule_html)
            self._print_schedule(schedule)


def get_logger(level):
    _logger = logging.getLogger()
    ch = logging.StreamHandler()

    if 'debug' in level.lower():
        _logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
    elif 'info' in level.lower():
        _logger.setLevel(logging.INFO)
        ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s [%(levelname)s]  %(message)s')
    ch.setFormatter(formatter)

    _logger.addHandler(ch)
    return _logger


def _get_proxies_from_config():
    try:
        from config import proxies
        return proxies
    except ImportError:
        proxies = {}
        return proxies


def _get_user_data_from_config():
    try:
        from config import user_data
        return user_data
    except Exception as e:
        print(e, 'from config')
        sys.exit(errno.ENOENT)


def _create_config_file():
    http_proxy = input('Enter http proxy: ')
    https_proxy = input('Enter https proxy: ')
    _proxies = {'http': http_proxy, 'https': https_proxy}
    username = input('Enter username: ')
    password = input('Enter password: ')
    _user_data = {'username': username, 'password': password}
    with open('config.py', 'w') as config_file:
        config_file.write('proxies = ' + str(_proxies) + '\n')
        config_file.write('user_data = ' + str(_user_data) + '\n')

    return _proxies, _user_data


def get_data_from_config():
    if os.path.exists('config.py'):
        _proxies = _get_proxies_from_config()
        _user_data = _get_user_data_from_config()
        return _proxies, _user_data
    else:
        return _create_config_file()


if __name__ == '__main__':
    user_proxies, user_data = get_data_from_config()
    logger = get_logger('info')
    wsis = Wsis(logger)
    wsis.proxies = user_proxies
    wsis.login(user_data)
    wsis.get_schedule()
    wsis.logout()
