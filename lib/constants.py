
import enum
from datetime import time, timedelta

class UserRole(enum.Enum):
    user = 0
    moderator = 1
    employee = 2

error_visible_duration = 2 # In seconds
max_book_washers = 2
available_days = 5  # Showed buttons in washer select

reminder_timedelta = [
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=3),
    timedelta(days=1)
]

available_weekdays = {
    UserRole.user:      {0, 1, 3, 4, 5},    # Mon, Tue, Thu, Fri, Sat
    UserRole.moderator: {0, 1, 2, 3, 4, 5}, # Mon, Tue, Wed, Thu, Fri, Sat
    UserRole.employee:  {0, 1, 2, 3, 4, 5}  # Mon, Tue, Wed, Thu, Fri, Sat
}

available_time = [
    time(10, 0),
    time(14, 0),
    time(18, 0),
    time(20, 0)
]

SELF_ALREADY_AUTHORIZED, \
OTHER_ALREADY_AUTHORIZED, \
AUTH_SUCCESSFUL, \
AUTH_NOT_FOUND = range(0, 4)

AUTH_REASON_LOCALE_MAP = {
    AUTH_SUCCESSFUL: 'successful',
    SELF_ALREADY_AUTHORIZED: 'self_already_authorized',
    OTHER_ALREADY_AUTHORIZED: 'other_already_authorized',
    AUTH_NOT_FOUND: 'not_found'
}

WASHER_IS_AVAILABLE, \
WASHER_IS_ALREADY_BOOKED, \
WASHER_IS_NOT_AVAILABLE, \
APPOINTMENT_IS_PASSED = range(0, 4)

WASHER_SIGN_CHARS = {  # not_available, available
    WASHER_IS_AVAILABLE:      [None, None],
    WASHER_IS_ALREADY_BOOKED: ['❌', '✅'],
    WASHER_IS_NOT_AVAILABLE:  ['🔧', None],
    APPOINTMENT_IS_PASSED:    ['⌛', None]
}
