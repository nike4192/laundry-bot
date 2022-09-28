
from sqlalchemy.orm import selectinload

from lib.constants import UserRole
from lib.models import async_session, session, User, AppointmentData, SummaryData
from lib.misc import timedelta_to_str
from lib.forms.appointment import AppointmentForm

import asyncio
from datetime import datetime, timedelta
from sqlalchemy.types import DateTime
from sqlalchemy import select, func

from app import application


async def main():
    now_dt = datetime.now()
    now_rdt = now_dt - \
        timedelta(seconds=now_dt.second,
                  microseconds=now_dt.microsecond)

    # REMIND ALL MODERATORS
    stmt = select(User) \
        .where(
            User.role == UserRole.moderator) \
        .options(
            selectinload(User.reminders))

    moderators = (await session.scalars(stmt)).unique().all()
    for moderator in moderators:
        for reminder in moderator.reminders:
            reminder_td = timedelta(seconds=reminder.seconds)
            book_rdt = now_rdt + reminder_td
            stmt = select(func.count()).where(
                AppointmentData.book_date == book_rdt.date(),
                AppointmentData.book_time == book_rdt.time()
            )
            appointments_count = (await session.scalars(stmt)).unique().one_or_none()
            if appointments_count:
                stmt = select(SummaryData) \
                    .where(SummaryData.summary_date == book_rdt.date())
                for summary_data in (await session.scalars(stmt)).unique().all():
                    if summary_data.message_id is not None:
                        await application.bot.send_message(
                            chat_id=summary_data.message.user.chat_id,
                            reply_to_message_id=summary_data.message.id,
                            parse_mode='Markdown',
                            text=f'🔔 Через *%s* назначены стирки - %s' % (
                                timedelta_to_str(reminder_td), appointments_count)
                        )

    # REMIND ALL USERS
    stmt = select(AppointmentData) \
        .where(
            AppointmentData.book_date is not None,
            AppointmentData.book_time is not None,
            AppointmentData.message) \
        .options(
            selectinload(AppointmentData.message))

    expired_datas = []
    datas = (await session.scalars(stmt)).unique().all()
    for data in datas:
        if data.message_id is not None and bool(data.appointments):
            book_dt = datetime.combine(data.book_date, data.book_time)
            if now_rdt >= book_dt:  # EXPIRED
                expired_datas.append(data)
            else:
                user = data.message.user
                for reminder in user.reminders:  # REMINDERS
                    reminder_td = timedelta(seconds=reminder.seconds)
                    notify_dt = book_dt - reminder_td
                    if now_rdt == notify_dt:
                        await application.bot.send_message(
                            chat_id=user.chat_id,
                            reply_to_message_id=data.message.id,
                            parse_mode='Markdown',
                            text=f'🔔 Через *%s* назначена ваша стирка' % (timedelta_to_str(reminder_td),)
                        )

    await asyncio.gather(*[
        AppointmentForm(data.message.user, data).close(1, application.bot)
        for data in expired_datas
    ])

if __name__ == '__main__':
    asyncio.run(main())
