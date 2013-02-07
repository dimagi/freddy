import datetime
import dateutil.parser
import pytz
import types
import json


class ChangeTrackingDict(dict):
    """
    A dictionary that tracks what values are added, touched, modified, and
    deleted after its initial creation.

    """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

        self.added_keys = set()
        self.touched_keys = set()
        self.modified_keys = set()
        self.deleted_keys = set()

        self.latest_values = {}

    def __setitem__(self, name, val):
        try:
            dict.__getitem__(self, name)
        except KeyError:
            self.added_keys.add(name)

        self.touched_keys.add(name)

        if dict.__getitem__(self, name) != val:
            self.modified_keys.add(name)

        dict.__setitem__(self, name, val)

    def __delitem__(self, name):
        if name in self.added_keys:
            self.added_keys.remove(name)
            self.touched_keys.remove(name)
            self.modified_keys.remove(name)
        else:
            self.deleted_keys.add(name)
            self.touched_keys.add(name)
            self.modified_keys.add(name)

        dict.__delitem__(self, name)

    @property
    def is_touched(self):
        return (self.touched_keys or self.deleted_keys or
                any(isinstance(v, ChangeTrackingDict) and v.is_touched
                    for v in self.items()))

    @property
    def is_modified(self):
        return (self.modified_keys or self.deleted_keys or
                any(isinstance(v, ChangeTrackingDict) and v.is_modified
                    for v in self.items()))

    def get_changes(self, include_touched=False):
        """
        Returns a tuple of two values:
        1. dict of changed values
        2. tuple of deleted keys

        include_touched -- whether to include values that have been set but
            were identical to the existing value

        """

        keys = self.touched_keys if include_touched else self.modified_keys
        return dict((k, self[k]) for k in keys), self.deleted_keys


class PropertyDict(ChangeTrackingDict):
    """
    A dictionary that only allows alphanumeric keys and automatically parses
    dates when setting values for keys specified in the date_properties
    argument.

    """
    def __init__(self, *args, **kwargs):
        self.date_properties = kwargs.pop('date_properties', {})

        convert = lambda d: dict((k, self._parse_date(k, v))
                                 for k, v in d.items())

        if args:
            args = (convert(args[0]),)
        if kwargs:
            kwargs = convert(kwargs)

        return super(PropertyDict, self).__init__(*args, **kwargs)

    def _parse_date(self, key, val):
        if (val is not None and key in self.date_properties and
            not isinstance(val, datetime.datetime)):
            return dateutil.parser.parse(val)
        else:
            return val

    def __setitem__(self, name, val):
        if not(name.isalnum() and name[0].isalpha()):
            raise TypeError("Can't set non-alphanumeric property.")

        val = self._parse_date(name, val)
        super(PropertyDict, self).__setitem__(name, val)


def to_json(val):
    if isinstance(val, datetime.datetime):
        # always use UTC
        val.replace(tzinfo=pytz.utc)
        return val.isoformat()
    else:
        return val


def to_json_string(data):
    return json.dumps(dict((k, to_json(v)) for k, v in data.items()))


def to_urlparam(val):
    if isinstance(val, types.BooleanType):
        return "true" if val else "false"
    else:
        return to_json(val)
