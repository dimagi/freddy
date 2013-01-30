import datetime
import pytz
import types
import json

class PropertyDict(dict):
    """
    Dict where keys must be alphanumeric and start with a letter, and
    d.is_modified will be True if any properties have been set after
    initialization.

    todo: track actual modified properties, for partial update requests

    """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.is_modified = False

    def __setitem__(self, name, val):
        if not(name.isalnum() and name[0].isalpha()):
            raise ValueError("Can't set non-alphanumeric property.")

        dict.__setitem__(self, name, val)
        self.is_modified = True


def to_json(val):
    if isinstance(val, datetime.datetime):
        # always use UTC
        val.replace(tzinfo=pytz.utc)
        return val.isoformat()
    else:
        return str(val)


def to_json_string(data):
    return json.dumps(dict((k, to_json(v)) for k, v in data))


def to_urlparam(val):
    if isinstance(val, types.BooleanType):
        return "true" if val else "false"
    else:
        return to_json(val)
