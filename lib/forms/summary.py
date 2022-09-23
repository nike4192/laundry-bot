
from datetime import date
from itertools import zip_longest

from sqlalchemy import select, func
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from lib import misc
from lib.models import User, SummaryData, AppointmentData, session, Appointment
from lib.forms.base import BaseMessage, BaseAction, BaseForm


class SummaryDateAction(BaseAction, BaseMessage):
    def __init__(self):
        super().__init__('Дата', 'Выберите дату')

    def text(self, data: SummaryData):
        return '📅 ' + self.action_text

    def reply_markup(self, user: User, data: SummaryData, state: int):
        keyboard = []
        available_dates = list(misc.gen_available_dates(user.role))

        stmt = select(func.count()) \
            .where(Appointment.book_date.in_(available_dates)) \
            .group_by(Appointment.book_date)
        appointment_group_counts = session.scalars(stmt).all()

        for d, appointments_count in zip_longest(available_dates, appointment_group_counts):
            date_str = misc.date_button_to_str(d)
            keyboard_button = InlineKeyboardButton(
                    '%s - %d' % (date_str, appointments_count)
                    if appointments_count else date_str,
                    callback_data=' '.join([str(state), d.isoformat()]))
            keyboard.append([keyboard_button])
        return InlineKeyboardMarkup(keyboard)

    def button_handler(self, user: User, data: SummaryData, value: str) -> tuple[bool, str]:
        data.summary_date = date.fromisoformat(value)
        return True, ''


class SummaryInfoMessage(BaseMessage):

    parse_mode = 'MarkdownV2'

    def text(self, data: SummaryData):
        summary_date = data.summary_date

        stmt = select(AppointmentData) \
            .filter(
                AppointmentData.book_date == summary_date) \
            .order_by(
                AppointmentData.book_date,
                AppointmentData.book_time)

        datas = session.scalars(stmt).all()

        # book_date
        msg_txt = misc.md2_escape(misc.date_to_str(summary_date)) + '\n\n'
        accum_t = None
        for data in datas:
            if data.washers:
                if accum_t != data.book_time:
                    accum_t = data.book_time
                    # book_time
                    msg_txt += ('~%s~' if data.expired else '*%s*') % \
                               (misc.time_to_str(accum_t)) + \
                               '\n'
                # user
                msg_txt += ' \- '.join([
                    # username
                    '\- @%s ' % misc.md2_escape(data.message.user.username) +
                    # last_name and first_name
                    '||%s %s||' % (
                        misc.md2_escape(data.message.user.last_name),
                        misc.md2_escape(data.message.user.first_name)
                    ),
                    # washers
                    '\(%s\)\n' % misc.washers_to_str(data.washers)
                ])

        return msg_txt


class SummaryForm(BaseForm):
    actions = [
        SummaryDateAction(),
        SummaryInfoMessage()
    ]

    def __init__(self, user: User, data: SummaryData = None):
        if data is None:
            data = SummaryData()
            session.add(data)
            session.commit()
        super().__init__(user, data)
        print(self.data, self.data.state)


    def find_exists_datas(self, data: SummaryData):
        stmt = select(SummaryData).where(
            SummaryData.summary_date == data.summary_date)
        return [d
            for d in session.scalars(stmt).all()
            if  d.message_id is not None and
                d.message.user == self.user and
                d != data
        ]

    def text(self):
        if issubclass(self.active_action.__class__, BaseMessage):
            if self.closed:
                return '⌛'  # Sticker in MarkdownV2
            else:
                return self.active_action.text(self.data)
        else:
            return super(SummaryForm, self).text()