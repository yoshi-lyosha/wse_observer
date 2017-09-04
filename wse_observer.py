import requests
from bs4 import BeautifulSoup as BeS
import re
import os
import sys
import errno
import model
import logging
import datetime


# TODO: перепилить логирование, больше детальности: кто что где как сделал
# TODO: оптимизировать количество переходов на сайт. мне не нравится что это занимает так много времени
# TODO: узнать сколько живёт сессия
# TODO: Логгирование для дебаг-режима - в стдаут, продакшн - в файл
# TODO: кэшировать что-нибудь по-возможности
# TODO: рефактор под многопользовательский режим. лоадить куки под конкретного юзера. все реквесты под конкретных.


class WSEObserver:
    """
    Класс для логина/логаута/получения расписания с ресурса под названием Wall Street English

    """
    proxies = {}
    wsis_index_url = 'http://www.wsistudents.com/'
    wsis_personal_page_url = 'http://www.wsistudents.com/splash.jhtml'
    redirect_page_url = 'http://www.wsistudents.com/switch2supersds.jhtml'
    schedule_page_url = 'http://sdszone1.e-wsi.com/inhome/review.jhtml'
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

    def registration(self, login, password):
        """
        Создание нового студента в бд и пустых куки для него
        :param login: логин студента для портала WSE
        :param password: пароль студента для портала WSE
        :return:
        """
        self.logging.info('Создаём нового юзера')
        new_student = model.WSEStudent.create(wse_login=login, wse_password=password)
        model.WSECookie.create(wse_student=new_student)
        return new_student

    def update_student_password(self, student, new_password):
        """
        Редактирование пароля студента для портала WSE
        :param student: студент
        :param new_password: новый пароль для портала WSE
        :return:
        """
        self.logging.info('Редактируем пароль существующего юзера')
        student.wse_password = new_password
        student.save()

    def update_student_username(self, student, new_username):
        """
        Редактирование логина для портала WSE
        :param student: студент
        :param new_username: новый логина для портала WSE
        :return:
        """
        self.logging.info('Редактируем логин существующего юзера')
        student.wse_login = new_username
        student.save()

    def delete_student_data(self, student):
        """
        Удаление студента и всего, что может быть с ним связано
        :param student: студент
        :return:
        """
        self.logging.info('Удаляем существующего юзера')
        student_cookies = model.WSECookie.get(wse_student=student)
        student_schedule = model.WSESchedule.select().where(model.WSESchedule.wse_student == student)
        student_cookies.delete_instance()
        [student_schedule_field.delete_instance() for student_schedule_field in student_schedule]
        student.delete_instance()

    def _update_student_cookie(self, student, new_wsis_cookie=None, new_schedule_cookie=None):
        """
        Обновление кук студента в базе данных
        :param student: студент
        :param new_wsis_cookie: куки для портала wsis
        :param new_schedule_cookie: куки для портала с расписанием
        :return:
        """
        self.logging.debug('Сохраняем куки')
        student_cookie = model.WSECookie.get(wse_student=student)
        if new_wsis_cookie:
            student_cookie.wsis_cookie = new_wsis_cookie
        if new_schedule_cookie:
            student_cookie.schedule_cookie = new_schedule_cookie
        student_cookie.save()

    def _get_student_wsis_cookie(self, student):
        self.logging.debug('Достаём куки студента для стартовой страницы')
        return model.WSECookie.get(wse_student=student).wsis_cookie

    def _get_student_schedule_cookie(self, student):
        self.logging.debug('Достаём куки студента для расписания')
        return model.WSECookie.get(wse_student=student).schedule_cookie

    def _get_login_data(self, user):
        self.logging.debug('Достаём из бд креды и генерим словарь для формы логина')
        login_data = dict(self.wsis_login_data)
        login_data['username'] = user.wse_login
        login_data['password'] = user.wse_password
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

    def _post_login_request(self, login_data, login_url):
        """
        Отправляет POST реквест для логина
        :param login_url: урл для логина
        :param login_data: словарь с информацией для логина
        :return: POST реквест логина
        """
        self.logging.debug('Совершаем POST-запрос на логин')
        login_post_request = requests.post(login_url, proxies=self.proxies, data=login_data)
        return login_post_request

    def login(self, student):
        self.logging.info('Начинаем логиниться')
        self.logging.debug('Проверяем не залогинен ли уже/валидность кук')
        index_page_request = requests.get(self.wsis_index_url,
                                          cookies=self._get_student_wsis_cookie(student),
                                          proxies=self.proxies)
        if 'WELCOME TO YOUR WALL STREET ENGLISH' in index_page_request.text:
            self.logging.debug('Не залогинен')
            index_page_request = requests.get(self.wsis_index_url, proxies=self.proxies)
            index_page_html = index_page_request.text
            self._post_login_request(self._get_login_data(student), self._get_login_url(index_page_html))
            wsis_cookie = dict(index_page_request.cookies)
            self._update_student_cookie(student, new_wsis_cookie=wsis_cookie)
            self.logging.info('Логин завершён')
        else:
            self.logging.info('Уже залогинен')

    def _get_personal_page_request(self, student):
        """
        GET реквест перехода на персональную страницу ресурса WSIStudents
        :return: реквест
        """
        self.logging.debug('Запрос персональной страницы')
        personal_page_request = requests.get(self.wsis_personal_page_url,
                                             cookies=self._get_student_wsis_cookie(student),
                                             proxies=self.proxies)
        return personal_page_request

    def _get_logout_url(self, index_html):
        """
        Получить logout_url с персональной страницы пользователя
        :return: logout_url либо None
        """
        self.logging.debug('Получаем из персональной страницы урл для разлогина')
        index_soup = BeS(index_html, 'html.parser')
        logout_url = self.wsis_index_url + index_soup.find(id="headerWrapper").a.get('href')
        self.logging.debug('Урл для разлогина получен')
        return logout_url

    def _post_logout_request(self, student, logout_url):
        """
        Отправляет POST реквест для логаута
        :param logout_url: урл для логаута
        :return: POST реквест логаута
        """
        self.logging.debug('Совершаем POST-запрос на логаут')
        logout_post_request = requests.post(logout_url,
                                            cookies=self._get_student_wsis_cookie(student),
                                            proxies=self.proxies)
        return logout_post_request

    def logout(self, student):
        self.logging.info('Начинаем логаут')
        self.logging.debug('Проверяем не разлогинен ли уже')
        index_page_request = requests.get(self.wsis_index_url,
                                          cookies=self._get_student_wsis_cookie(student),
                                          proxies=self.proxies)
        index_page_html = index_page_request.text
        if 'WELCOME TO YOUR WALL STREET ENGLISH' in index_page_html:
            self.logging.info('Уже разлогинен')
        else:
            self.logging.debug('Не разлогинен')
            self._post_logout_request(student, self._get_logout_url(index_page_html))
            self.logging.info('Логин завершён')

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

    def _find_schedule_fields_list_in_html(self, schedule_html):
        """
        Функция для парсинга расписания в html
        :param schedule_html: хтмл страница с расписанием
        :return:
        """
        self.logging.debug('Парсим страницу с расписанием')

        schedule_soup = BeS(schedule_html, 'html.parser')
        schedule_table = schedule_soup.body.find_all('table')[2]
        tr_list = schedule_table.find_all('tr')
        schedule_fields_list = []

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

            schedule_fields_list.append(schedule_field)
        return schedule_fields_list

    def print_schedule(self, student):
        """
        Функция для печати расписания
        :return:
        """

        schedule_fields_list = self.get_schedule_fields_list(student)
        self.logging.info('Печатаем расписание')

        for number, schedule_field in enumerate(schedule_fields_list, 1):
            print('********{}********'.format(number))
            print('Тип...............{}'.format(schedule_field['lesson_type']))
            print('Дата..............{}'.format(schedule_field['date']))
            print('Время.............{}'.format(schedule_field['time']))
            print('Занятие, уровни...{}'.format(schedule_field['unit']))
            print('Описание занятия..{}'.format(schedule_field['description']))

    def get_schedule_fields_list(self, student):
        self.logging.info('Получаем расписание')
        schedule_page_request = requests.get(self.schedule_page_url,
                                             cookies=self._get_student_schedule_cookie(student),
                                             proxies=self.proxies )
        if '/system_error.jhtml' in schedule_page_request.text:
            self.logging.info('Не залогинены')
            self.login(student)
        redirect_page_request = requests.get(self.redirect_page_url,
                                             cookies=self._get_student_wsis_cookie(student),
                                             proxies=self.proxies)
        schedule_cookie = self._get_schedule_cookie_from_redirect_script(redirect_page_request.text)
        self._update_student_cookie(student, new_schedule_cookie=schedule_cookie)
        schedule_page_request = requests.get(self.schedule_page_url,
                                             cookies=self._get_student_schedule_cookie(student),
                                             proxies=self.proxies)
        schedule_fields_list = self._find_schedule_fields_list_in_html(schedule_page_request.text)
        return schedule_fields_list

    def _get_schedule_cookie_from_redirect_script(self, redirect_html):
        self.logging.debug('Извлекаем из скрипта редиректа новые куки')
        redirect_page_soup = BeS(redirect_html, 'html.parser')
        schedule_cookie = {}
        redirect_script = redirect_page_soup.find('script')
        var_redirectsessionid_pattern = r'var redirectSessionId = \'(.*)\''
        schedule_cookie['JSESSIONID'] = re.search(var_redirectsessionid_pattern, redirect_script.text).group(1)
        return schedule_cookie

# TODO: get_schedule -> update_schedule


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
        print(e)
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
    wsis = WSEObserver(logger)
    wsis.proxies = user_proxies
    user = model.WSEStudent.get(id=1)
    # wsis.login(user)
    wsis.print_schedule(user)
    # wsis.logout(user)
