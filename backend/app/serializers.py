from datetime import datetime
from sqlalchemy.inspection import inspect


def record(obj, exclude=()):
    result = {}
    for prop in inspect(type(obj)).column_attrs:
        key = prop.key
        if key in exclude:
            continue
        value = getattr(obj, key)
        result[key] = value.isoformat() if isinstance(value, datetime) else value
    return result


def user_record(user):
    return record(user, ('password_hash',))
