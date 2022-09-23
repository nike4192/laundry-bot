
import inspect
import re
from datetime import datetime, date, time, timedelta

import locales
import lib.constants as const
from lib.models import Washer, UserRole

from telegram.ext import ContextTypes



def time_to_str(t: time):
    return '%s:%s' % (
        str(t.hour).zfill(2),
        str(t.minute).zfill(2))


def timedelta_to_str(td: timedelta):
    pieces = []
    if td.days:
        pieces.append(f'{td.days} д.')
    if td.seconds:
        units = td.seconds
        if units >= 3600:
            pieces.append(f'{units // 3600} ч.')
            units -= units // 3600 * 3600
        if units >= 60:
            pieces.append(f'{units // 60} мин.')
            units -= units // 60 * 60
        if units:
            pieces.append(f'{units} сек.')

    return ' '.join(pieces)


def date_to_str(d: date):
    days_delta = d - date.today()
    if 0 <= days_delta.days < len(locales.ru['shift_days']):
        days_additional = locales.ru['shift_days'][days_delta.days]
    else:
        days_additional = locales.ru['weekdays'][d.weekday()]
    return '%s.%s.%s (%s)' % (
        str(d.day).zfill(2),
        str(d.month).zfill(2),
        d.year,
        days_additional)


def gen_available_dates(user_role: UserRole):
    now_dt = datetime.now()
    d = now_dt.date()
    td = timedelta(days=1)

    available_weekdays = const.available_weekdays[user_role]
    last_t = sorted(const.available_time)[-1]
    if now_dt.time() > last_t:  # Not available times
        d += td
    for i in range(const.available_days):
        while d.weekday() not in available_weekdays:
            d += td
        yield d
        d += td


def date_button_to_str(d: date):
    return '%s.%s (%s)' % (
        str(d.day).zfill(2),
        str(d.month).zfill(2),
        locales.ru['short_weekdays'][d.weekday()]
    )


def washers_to_str(washers: list[Washer]):
    washers = [
        w.name
        for w in sorted(washers, key=lambda w: w.name)
    ]
    return ', '.join(washers)


def aggregate_appointment_slots(slots: list[tuple[int, int]]):
    levels = [
        (True, const.WASHER_IS_ALREADY_BOOKED),
        (True, const.WASHER_IS_AVAILABLE),
        (False, const.WASHER_IS_ALREADY_BOOKED),
        (False, const.APPOINTMENT_IS_PASSED)
    ]

    for level in levels:
        if level in slots:
            return level


# https://core.telegram.org/bots/api#markdownv2-style
def md2_escape(s):
    special_characters = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    return re.sub('(%s)' % '|'.join(map(re.escape, special_characters)), r'\\\1', s)


def get_locale_by_path(path):
    # TODO: language_code in User
    # for arg in args:
    #     if isinstance(arg, ContextTypes.DEFAULT_TYPE):
    #         auth_user = arg.user_data['auth_user']
    #         getattr(locales, auth_user.language_code)
    #         ...
    l = locales.ru
    for p in path:
        l = l[p]
    return l


def append_locale_arg(*path):
    def decorator(func):
        def wrapper(*args, **kwargs):
            return func(*args, get_locale_by_path(path), **kwargs)

        async def async_wrapper(*args, **kwargs):
            return await func(*args, get_locale_by_path(path), **kwargs)

        return async_wrapper if inspect.iscoroutinefunction(func) else wrapper
    return decorator