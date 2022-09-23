
from datetime import timedelta

import locales
import lib.constants as const
from lib.forms.base import BaseAction, BaseForm
from lib.models import session, User, ReminderData, Reminder
from lib.misc import timedelta_to_str

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from sqlalchemy import select


class ReminderAction(BaseAction):
    def __init__(self):
        super().__init__('Уведомления', 'Выберите за сколько вас предупредить')

    def reply_markup(self, user: User, data: ReminderData, state: int):
        keyboard = []
        for reminder_td in const.reminder_timedelta:
            total_seconds = int(reminder_td.total_seconds()) # ROUNDING: float -> int
            _, reason = self.is_available_slot(user, data, total_seconds)
            sign_char = '✅' if reason else None
            keyboard_button = InlineKeyboardButton(
                (sign_char + ' ' if sign_char else '') + timedelta_to_str(reminder_td),
                callback_data=' '.join([str(state), str(total_seconds)])
            )
            keyboard.append(keyboard_button)
        return InlineKeyboardMarkup([keyboard])

    @staticmethod
    def is_available_slot(user: User, data: ReminderData, value):
        stmt = select(Reminder).filter(
            Reminder.seconds == int(value),
            Reminder.user == user
        )
        reminder = session.scalars(stmt).one_or_none()
        return True, bool(reminder)

    def item_stringify(self, data: ReminderData):
        if data.reminders:
            reminders = [
                timedelta_to_str(timedelta(seconds=reminder.seconds))
                for reminder in sorted(data.reminders, key=lambda r: r.seconds)
            ]
            return '\n- ' + '\n- '.join(reminders)
        else:
            return '...'

    def button_handler(self, user: User, data: ReminderData, value: str) -> tuple[bool, str]:
        _, reason = self.is_available_slot(user, data, value)

        if reason:
            stmt = select(Reminder).filter(
                Reminder.seconds == int(value),
                Reminder.user == user
            )
            reminder = session.scalars(stmt).one()
            session.delete(reminder)
            session.commit()
            return True, ''
        else:
            reminder = Reminder(
                seconds=int(value),
                user=user,
                data=data
            )
            session.add(reminder)
            session.commit()
            return True, ''


class ReminderForm(BaseForm):
    actions = [
        ReminderAction()
    ]

    closed_text = locales.ru['reminder_form']['closed_title']
    finished_text = locales.ru['reminder_form']['finished_title']

    def __init__(self, user: User, data: ReminderData = None):
        if data is None:
            data = ReminderData()
            session.add(data)
            session.commit()
        super().__init__(user, data)

    def find_exists_datas(self, data: ReminderData):
        stmt = select(ReminderData).where(
            ReminderData.state == data.state,
            ReminderData.message_id is not None
        )
        return [d
            for d in session.scalars(stmt).all()
            if  d.message_id is not None and
                d.message.user == self.user and
                d != data
        ]

    @property
    def finished(self):
        return bool(self.data.reminders)
