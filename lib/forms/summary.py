
from datetime import date
from itertools import zip_longest

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from lib import misc
from lib.models import User, SummaryData, AppointmentData, Appointment, Message
from lib.forms.base import BaseMessage, BaseAction, BaseForm


class SummaryDateAction(BaseAction, BaseMessage):
    def __init__(self):
        super().__init__('Дата', 'Выберите дату')

    async def text(self, session, data: SummaryData):
        return '📅 ' + self.action_text

    async def reply_markup(self, session: AsyncSession, user: User, data: SummaryData, state: int):
        keyboard = []
        available_dates = list(misc.gen_available_dates(user.role))

        for d in available_dates:
            stmt = select(func.count()).where(Appointment.book_date == d)
            appointments_count = (await session.scalars(stmt)).unique().one_or_none()
            date_str = misc.date_button_to_str(d)
            keyboard_button = InlineKeyboardButton(
                    '%s - %d' % (date_str, appointments_count)
                    if appointments_count else date_str,
                    callback_data=' '.join([str(state), d.isoformat()]))
            keyboard.append([keyboard_button])
        return InlineKeyboardMarkup(keyboard)

    async def button_handler(self, session: AsyncSession, user: User, data: SummaryData, value: str) -> tuple[bool, str]:
        data.summary_date = date.fromisoformat(value)
        return True, ''


class SummaryInfoMessage(BaseMessage):

    parse_mode = 'MarkdownV2'

    async def text(self, session: AsyncSession, data: SummaryData):
        summary_date = data.summary_date

        stmt = select(AppointmentData, User) \
            .where(
                AppointmentData.book_date == summary_date,
                AppointmentData.message_id == Message.id,
                Message.user_id == User.id) \
            .order_by(
                AppointmentData.book_date,
                AppointmentData.book_time)

        # book_date
        msg_txt = misc.md2_escape(misc.date_to_str(summary_date)) + '\n\n'
        accum_t = None
        for data, user in (await session.execute(stmt)).unique().fetchall():
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
                    '\- @%s ' % misc.md2_escape(user.username) +
                    # last_name and first_name
                    '||%s %s||' % (
                        misc.md2_escape(user.last_name),
                        misc.md2_escape(user.first_name)
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

    __data_class__ = SummaryData

    async def find_exists_datas(self, session: AsyncSession, data: SummaryData):
        stmt = select(SummaryData) \
            .where(
                SummaryData.summary_date == data.summary_date) \
            .where(
                SummaryData.message_id == Message.id,
                Message.user_id == self.user.id,
                SummaryData.id != data.id)

        return (await session.execute(stmt)).scalars().all()
