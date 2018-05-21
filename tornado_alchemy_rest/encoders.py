from __future__ import absolute_import

from datetime import datetime, timedelta
from json import JSONEncoder, JSONDecoder
import enum
from aiopg.sa.result import RowProxy

class TimeDeltaJSONEncoder(JSONEncoder):
    """
    Converts a python object, where datetime and timedelta objects are converted
    into objects that can be decoded using the DateTimeAwareJSONDecoder.

    Adapted from `gist <https://gist.github.com/majgis/4200488>`_
    """

    def default(self, obj):
        if isinstance(obj, timedelta):
            return {
                'seconds': obj.total_seconds(),
                }

        else:
            return JSONEncoder.default(self, obj)



class DateTimeAwareJSONEncoder(JSONEncoder):
    """
    Converts a python object, where datetime and timedelta objects are converted
    into objects that can be decoded using the DateTimeAwareJSONDecoder.

    Adapted from `gist <https://gist.github.com/majgis/4200488>`_
    """

    def default(self, obj):
        if isinstance(obj, enum.IntEnum) or isinstance(obj, enum.Enum):
            return obj.value
        if isinstance(obj, RowProxy):
            return {
                k: obj[k] for k in obj.keys()
            }
        if isinstance(obj, datetime):
            return obj.timestamp()

        elif isinstance(obj, timedelta):
            return {
                '__type__' : 'timedelta',
                'days': obj.days,
                'hours': obj.seconds // 3600,
                'minutes': (obj.seconds // 60) % 60,
                'seconds': obj.seconds,
                'microseconds': obj.microseconds,
                }

        else:
            return JSONEncoder.default(self, obj)


class DateTimeAwareJSONDecoder(JSONDecoder):
    """
    Converts a json string, where datetime and timedelta objects were converted
    into objects using the DateTimeAwareJSONEncoder, back into a python object.
    """

    def __init__(self, **kwargs):
        JSONDecoder.__init__(self, object_hook=self.dict_to_object, **kwargs)

    def dict_to_object(self, d):
        if '__type__' not in d:
            return d

        type = d.pop('__type__')
        if type == 'datetime':
            return datetime(**d)
        elif type == 'timedelta':
            return timedelta(**d)
        else:
            # Oops... better put this back together.
            d['__type__'] = type
            return d

