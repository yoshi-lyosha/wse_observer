import requests
from bs4 import BeautifulSoup as BeS
import re
import json
import logging
from collections import OrderedDict, defaultdict


# TODO: достать печенье из супа
# TODO: узнать сколько живёт сессия
# TODO: создавать файл для кук, если его нету
# TODO: Логгирование для дебаг-режима - в стдаут
# TODO: искать айди сессии не в хтмл, а в куках сразу
# TODO: кэшировать кое-что

# TODO: рефактор под многопользовательский режим. лоадить куки под конкретного юзера. все реквесты под конкретных.


def cookie_load():
    """
    Загружает словарь с куками из файлика

    :return:
    cookie - словарь с куками
    """
    logging.info('Подгружаем куки')
    with open('cookie.json') as cookie_file:
        cookie = json.load(cookie_file)
    logging.info(cookie)
    return cookie


def cookie_save(cookie):
    """Сохраняет словарь с куками из файлика

    :param cookie: словарь с куками
    """
    logging.info('Сохраняем куки')
    logging.info(cookie)
    with open('cookie.json', 'w') as cookie_file:
        json.dump(cookie, cookie_file)
    return None


def get_form_action_field(index_html):
    """
    Получает агрумент action поля form из html

    :param index_html: хтмл для обработки
    :return: агрумент action поля form
    """
    logging.info('Извлекаем поле form action из index.html')
    index_soup = BeS(index_html, 'html.parser')
    form_action_field = index_soup.form.get('action')
    return form_action_field


def get_cookie_from_form_action_field(form_action_field):
    """
    Получает JSESSIONID из form_action_field

    :param form_action_field: агрумент action поля form
    :return: словарь кук с JSESSIONID в нём
    """
    logging.info('Получаем JSESSIONID для куки')
    cookie = dict()
    jsession_id_re = r'jsessionid=(.*)\?'
    cookie['JSESSIONID'] = re.findall(jsession_id_re, form_action_field)[0]
    return cookie


def post_login_request(login_url, login_data):
    """
    Отправляет POST реквест для логина
    :param login_url: урл для логина
    :param login_data: словарь с информацией для логина
    :return: POST реквест логина
    """
    logging.info('Совершаем POST-запрос на логин')
    login_post_request = requests.post(login_url, data=login_data)
    return login_post_request


def login_and_save_session_id(index_url, login_data):
    """
    Цикл из трёх попыток логина и сохранения кук
    :param index_url: урл для логина
    :param login_data: словарь с информацией для логина
    :return: True если логин удался, False если нет
    """
    for try_to_login in range(1, 4):
        logging.info('Пытаемся залогиниться, попытка {} из 3'.format(try_to_login))
        index_html = requests.get(index_url).text
        form_action_field = get_form_action_field(index_html)
        login_url = index_url + form_action_field
        login_post_request = post_login_request(login_url, login_data)
        if login_post_request.status_code == 200:
            logging.info('POST запрос для логина прошёл успешно')
            cookie = get_cookie_from_form_action_field(form_action_field)
            cookie_save(cookie)
            return True
        else:
            logging.warning('Логин не удался. Статус запроса {}'.format(login_post_request.status_code))
    else:
        logging.error('Не удалось залогиниться')
        return False


def login_controller(index_url, login_data):
    """
    Функция для логина на сайт
    :param index_url: урл для логина
    :param login_data: словарь с информацией для логина
    :return: True если логин удался, False если нет
    """
    logging.info('Начинаем логиниться')
    logging.info('Проверяем не залогинен ли уже')
    personal_page_request = get_personal_page_request()
    if personal_page_request.status_code == 200:
        logging.info('Уже залогинен')
        return True
    else:
        logging.info('Не залогинен')
        login_and_save_session_id(index_url, login_data)
        if get_personal_page_request().status_code == 200:
            logging.info('Логин прошёл успешно')
            return True
        else:
            logging.error('Логин не удался, возможно, данные указаны неправильно')
            return False


def get_personal_page_request():
    """
    GET реквест перехода на персональную страницу ресурса WSIStudents
    :return: реквест
    """
    logging.info('Запрос персональной страницы')
    cookie = cookie_load()
    personal_page_url = 'http://www.wsistudents.com/splash.jhtml'
    personal_page_request = requests.get(personal_page_url, cookies=cookie)
    return personal_page_request


def get_logout_url(index_url):
    """
    Получить logout_url с персональной страницы пользователя
    :param index_url: урл для сложения с logout_url
    :return: logout_url либо None
    """
    logging.info('Получаем из персональной страницы урл для разлогина')
    personal_page_request = get_personal_page_request()
    if personal_page_request.status_code == 200:
        final_html = personal_page_request.content
        final_soup = BeS(final_html, 'html.parser')
        logout_url = index_url + final_soup.find(id="headerWrapper").a.get('href')
        logging.info('Урл для разлогина получен')
        logging.debug('{}'.format(logout_url))
        return logout_url
    else:
        logging.error('Что-то пошло не так')
        return None


def post_logout_request(logout_url):
    """
    Отправляет POST реквест для логаута
    :param logout_url: урл для логаута
    :return: POST реквест логаута
    """
    logging.info('Совершаем POST-запрос на логаут')
    logging.info('Необходимы куки для логаута')
    cookie = cookie_load()
    logout_post_request = requests.post(logout_url, cookies=cookie)
    return logout_post_request


def logout(index_url):
    """
    Цикл из трёх попыток логаута
    :param index_url: урл
    :return: True если логаут прошёл, False если нет
    """
    for try_to_logout in range(1, 4):
        logging.info('Пытаемся разлогиниться, попытка {} из 3'.format(try_to_logout))

        logout_url = get_logout_url(index_url)
        logout_post_request = post_logout_request(logout_url)
        if logout_post_request.status_code == 200:
            logging.info('POST запрос для логаута прошёл успешно')
            logging.info('Логаут прошёл успешно')
            return True
        else:
            logging.warning('Логаут не удался. Статус запроса {}'.format(logout_post_request.status_code))
    else:
        logging.error('Не удалось сделать логаут')
        return False


def logout_controller(index_url):
    """
    Функция для логаута из ресурс
    :param index_url: урл ресурса
    :return: True если логаут прошёл, False если нет
    """
    logging.info('Начинаем логаут')
    logging.info('Проверяем не разлогинен ли уже')
    personal_page_request = get_personal_page_request()
    if personal_page_request.status_code == 200:
        logging.info('Залогинен, начинаю логаут')
        logout_result = logout(index_url)
        return logout_result
    else:
        logging.info('Уже разлогинен')
        return True


def get_schedule_page_request():
    """
    GET реквест перехода на страницу с расписанием ресурса WSIStudents
    :return: реквест
    """
    logging.info('Запрос страницы с расписанием')
    cookie = cookie_load()

    redirect_page_url = 'http://www.wsistudents.com/switch2supersds.jhtml'
    redirect_page_request = requests.get(redirect_page_url, cookies=cookie)
    if redirect_page_request.status_code == 200:
        redirect_page_soup = BeS(redirect_page_request.text, 'html.parser')
        shedule_cookie = {}
        redirect_script = redirect_page_soup.find('script')
        var_redirectsessionid_pattern = r'var redirectSessionId = \'(.*)\''
        shedule_cookie['JSESSIONID'] = re.search(var_redirectsessionid_pattern, redirect_script.text).group(1)
        print(shedule_cookie)

        schedule_page_url = 'http://sdszone1.e-wsi.com//inhome/review.jhtml'
        schedule_page_request = requests.get(schedule_page_url, cookies=shedule_cookie)
        return schedule_page_request
    else:
        print('ne vishlo')
        return False

def get_schedule_from_html(schedule_html):
    schedule_soup = BeS(schedule_html, 'html.parser')
    schedule_table = schedule_soup.body.find_all('table')[2]
    tr_list = schedule_table.find_all('tr')
    for tr in tr_list[1:-1]:

        td_list = tr.find_all('td')
        type_pattern = r'(\w+)'
        date_pattern = r'(\d{2}/\d{2}/\d{4})'
        time_pattern = r'(\d{2}:\d{2}\s* - \s*\d{2}:\d{2})'
        unit_pattern = r'([\w\+]+)\s?,?'
        description_pattern = r'(\w+)+'
        print(re.findall(type_pattern, td_list[1].text.replace('\n', '')))
        print(re.findall(date_pattern, td_list[2].text.replace('\n', '')))
        print(re.findall(time_pattern, td_list[2].text.replace('\n', '')))
        print(re.findall(unit_pattern, td_list[3].text.replace('\n', '')))
        print(re.findall(description_pattern, td_list[4].text.replace('\n', '')))


def get_schedule():
    schedule_page_request = get_schedule_page_request()
    if not schedule_page_request:
        return False

    elif schedule_page_request.status_code == 200:
        schedule_html = schedule_page_request.text
        get_schedule_from_html(schedule_html)


if __name__ == '__main__':
    wsis_index_url = 'http://www.wsistudents.com/'
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

    logging.basicConfig(format=u'%(asctime)s [%(levelname)s]  %(message)s', level=logging.INFO)

    wsis_login_data['username'] = input('Enter your username: ')
    wsis_login_data['password'] = input('Enter your password: ')

    login_controller(wsis_index_url, wsis_login_data)
    get_schedule()
    logout_controller(wsis_index_url)
