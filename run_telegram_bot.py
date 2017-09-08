#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cherrypy
import telebot.types
from telegram_bot import bot
from config import telegram_token as API_TOKEN

WEBHOOK_HOST = '5.228.0.110'
WEBHOOK_PORT = 443  # 443, 80, 88 или 8443 
WEBHOOK_LISTEN = '0.0.0.0'  # Слушаем отовсюду
WEBHOOK_SSL_CERT = './webhook_cert.pem'  # Путь к сертификату
WEBHOOK_SSL_PRIV = './webhook_pkey.pem'  # Путь к закрытому ключу

WEBHOOK_URL_BASE = "https://{!s}:{!s}".format(WEBHOOK_HOST, WEBHOOK_PORT)
WEBHOOK_URL_PATH = "/{!s}/".format(API_TOKEN)
# Вводим здесь IP-адреса и порты, куда перенаправлять входящие запросы.
# Т.к. всё на одной машине, то используем локалхост + какие-нибудь свободные порты.
# https в данном случае не нужен, шифровать незачем.
# BOT_ADDRESS = "http://127.0.0.1:7771"


# Описываем наш сервер
class WebhookServer(object):
    @cherrypy.expose
    def index(self):
        if 'content-length' in cherrypy.request.headers and \
           'content-type' in cherrypy.request.headers and \
           cherrypy.request.headers['content-type'] == 'application/json':
            length = int(cherrypy.request.headers['content-length'])
            json_string = cherrypy.request.body.read(length)
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_messages([update.message])
            return ''
        else:
            raise cherrypy.HTTPError(403)


if __name__ == '__main__':

    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE+WEBHOOK_URL_PATH,
                    certificate=open(WEBHOOK_SSL_CERT, 'r'))    

    cherrypy.config.update({
        'server.socket_host': WEBHOOK_LISTEN,
        'server.socket_port': WEBHOOK_PORT,
        'server.ssl_module': 'builtin',
        'server.ssl_certificate': WEBHOOK_SSL_CERT,
        'server.ssl_private_key': WEBHOOK_SSL_PRIV,
        'engine.autoreload.on': False
    })
    cherrypy.quickstart(WebhookServer(), '/', {'/': {}})
