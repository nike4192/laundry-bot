
from datetime import datetime, date, time

import locales
import lib.misc as misc
import lib.constants as const
from lib.misc import append_locale_arg
from lib.forms.base import BaseAction, BaseForm
from lib.models import session, User, AppointmentData, Appointment, Washer, Message

from sqlalchemy import func
from sqlalchemy.future import select
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


class DateAppointmentAction(BaseAction):
    def __init__(self):
        super().__init__('Дата', 'Выберите дату')

    @staticmethod
    async def is_available_slot(user: User, data: AppointmentData, value: str):
        tmp = data.book_date
        data.book_date = date.fromisoformat(value)

        slots = [
            await TimeAppointmentAction.is_available_slot(user, data, t.isoformat())
            for t in const.available_time
        ]

        data.book_date = tmp  # Required after temporarily changes
        return misc.aggregate_appointment_slots(slots)

    async def reply_markup(self, user: User, data: AppointmentData, state: int):
        available_dates = list(misc.gen_available_dates(user.role))

        keyboard = []
        for d in available_dates:
            is_available, reason = await self.is_available_slot(user, data, d.isoformat())
            sign_char = const.WASHER_SIGN_CHARS[reason][is_available]
            keyboard_button = InlineKeyboardButton(
                    (sign_char + ' ' if sign_char else '') +
                    misc.date_button_to_str(d),
                    callback_data=' '.join([str(state), d.isoformat()]))
            keyboard.append([keyboard_button])
        return InlineKeyboardMarkup(keyboard)

    def item_stringify(self, data: AppointmentData):
        return misc.date_to_str(data.book_date)

    @append_locale_arg('appointment_form', 'date_action')
    async def button_handler(self, user: User, data: AppointmentData, value: str, locale: dict) -> tuple[bool, str]:
        is_available, reason = await self.is_available_slot(user, data, value)
        if is_available:
            data.book_date = date.fromisoformat(value)
            await session.commit()
            return True, ''
        else:
            if reason == const.WASHER_IS_ALREADY_BOOKED:
                return False, locale['washer_is_already_booked']
            elif reason == const.APPOINTMENT_IS_PASSED:
                return False, locale['appointment_is_passed']


class TimeAppointmentAction(BaseAction):
    def __init__(self):
        super().__init__('Время', 'Выберите время')

    @staticmethod
    async def is_available_slot(user: User, data: AppointmentData, value: str):
        washers = (await session.scalars(select(Washer))).all()

        tmp = data.book_time
        data.book_time = time.fromisoformat(value)
        slots = [
            (await WashersAppointmentAction.is_available_slot(user, data, washer.id))[:2]
            for washer in washers
        ]

        data.book_time = tmp  # Required after temporarily changes

        return misc.aggregate_appointment_slots(slots)

    async def reply_markup(self, user: User, data: AppointmentData, state: int):
        keyboard = []
        now_dt = datetime.now()
        for t in const.available_time:
            book_dt = datetime.combine(data.book_date, t)
            if now_dt < book_dt:
                is_available, reason = await self.is_available_slot(user, data, t.isoformat())
                sign_char = const.WASHER_SIGN_CHARS[reason][is_available]
                keyboard_button = InlineKeyboardButton(
                    (sign_char + ' ' if sign_char else '') +
                    '%s:%s' % (
                        str(t.hour).zfill(2),
                        str(t.minute).zfill(2)),
                    callback_data=' '.join([str(state), t.isoformat()]))
                keyboard.append([keyboard_button])
        return InlineKeyboardMarkup(keyboard)

    def item_stringify(self, data: AppointmentData):
        return misc.time_to_str(data.book_time)

    @append_locale_arg('appointment_form', 'time_action')
    async def button_handler(self, user: User, data: AppointmentData, value: str, locale: dict) -> tuple[bool, str]:
        is_available, reason = await self.is_available_slot(user, data, value)
        if is_available:
            data.book_time = time.fromisoformat(value)
            await session.commit()
            return True, ''
        else:
            if reason == const.WASHER_IS_ALREADY_BOOKED:
                return False, locale['washer_is_already_booked']
            elif reason == const.APPOINTMENT_IS_PASSED:
                return False, locale['appointment_is_passed']


class WashersAppointmentAction(BaseAction):
    def __init__(self):
        super().__init__('Стиральные машины', 'Выберите стиральные машины')

    async def reply_markup(self, user: User, data: AppointmentData, state: int):
        washers = (await session.scalars(select(Washer))).all()

        keyboard = []
        for washer in washers:
            is_available, reason = (await self.is_available_slot(user, data, washer.id))[:2]
            sign_char = const.WASHER_SIGN_CHARS[reason][is_available]
            keyboard_button = InlineKeyboardButton(
                (sign_char + ' ' if sign_char else '') + washer.name,
                callback_data=' '.join([str(state), str(washer.id)])
            )
            keyboard.append(keyboard_button)
        return InlineKeyboardMarkup([keyboard])

    def item_stringify(self, data: AppointmentData):
        if data.washers:
            return misc.washers_to_str(data.washers)
        else:
            return '...'

    @staticmethod
    async def is_available_slot(user: User, data: AppointmentData, value):
        stmt = select(Appointment).where(
            Appointment.book_date == data.book_date,
            Appointment.book_time == data.book_time,
            Appointment.washer_id == int(value))
        appointment = (await session.scalars(stmt)).one_or_none()
        if not appointment:
            washer = await session.get(Washer, int(value))
            if not washer.available:
                return False, const.WASHER_IS_NOT_AVAILABLE, None
            else:
                return True, const.WASHER_IS_AVAILABLE, None
        else:
            if appointment.passed:
                return False, const.APPOINTMENT_IS_PASSED, None
            else:
                return appointment.user_id == user.id, \
                       const.WASHER_IS_ALREADY_BOOKED, \
                       (appointment if appointment.user_id == user.id else None)

    @append_locale_arg('appointment_form', 'washer_action')
    async def button_handler(self, user: User, data: AppointmentData, value: str, locale: dict) -> tuple[bool, str]:
        is_available, reason, appointment = await self.is_available_slot(user, data, value)

        if is_available:
            if reason == const.WASHER_IS_AVAILABLE:
                stmt = select(func.count()) \
                    .where(
                        Appointment.user_id == user.id,
                        Appointment.passed == False)
                planned_appointments_count = (await session.scalars(stmt)).one()
                if planned_appointments_count >= const.max_book_washers:
                    return False, locale['max_book_washers'] % const.max_book_washers
                session.add(
                    Appointment(
                        user=user,
                        data=data,
                        book_date=data.book_date,
                        book_time=data.book_time,
                        washer_id=int(value)))
                await session.commit()
                return True, ''
            elif reason == const.WASHER_IS_ALREADY_BOOKED:
                await session.delete(appointment)
                await session.commit()
                await session.refresh(data)  # Update relationships
                return True, ''
        else:  # Not available
            locale_key = const.WASHER_REASON_LOCALE_MAP[reason]
            return False, locale[locale_key]


class AppointmentForm(BaseForm):
    actions = [
        DateAppointmentAction(),
        TimeAppointmentAction(),
        WashersAppointmentAction()
    ]

    __data_class__ = AppointmentData

    passed_text = locales.ru['appointment_form']['passed_title']
    closed_text = locales.ru['appointment_form']['closed_title']
    finished_text = locales.ru['appointment_form']['finished_title']

    def __init__(self, user: User, data: AppointmentData):
        super().__init__(user, data)

    async def find_exists_datas(self, data: AppointmentData):
        stmt = select(AppointmentData) \
            .where(
                AppointmentData.book_date == data.book_date,
                AppointmentData.book_time == data.book_time,
                AppointmentData.state == data.state) \
            .where(
                AppointmentData.message_id == Message.id,
                Message.user_id == self.user.id,
                AppointmentData.id != data.id)

        return (await session.scalars(stmt)).unique().all()

    @property
    def finished(self):
        return bool(self.data.washers)
