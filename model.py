from peewee import (Model, SqliteDatabase,
                    CharField, ForeignKeyField, DateField, TimeField)
from playhouse.fields import PickledField

db = SqliteDatabase('wse.db')


class WSEStudent(Model):

    wse_login = CharField()
    wse_password = CharField()

    class Meta:
        database = db


class WSESchedule(Model):
    wse_student = ForeignKeyField(WSEStudent, related_name='student_schedule')
    lesson_type = CharField()
    lesson_date = CharField()
    lesson_time = CharField()
    lesson_levels = CharField()
    lesson_description = CharField()

    class Meta:
        database = db


class WSECookie(Model):
    wse_student = ForeignKeyField(WSEStudent, related_name='student_cookie')
    wsis_cookie = PickledField(default={})
    schedule_cookie = PickledField(default={})

    class Meta:
        database = db


class TelegramUser(Model):
    chat_id = CharField()
    wse_student = ForeignKeyField(WSEStudent, related_name='tg_user')

    class Meta:
        database = db
