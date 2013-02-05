import requests
import dateutil.parser
from functools import partial
from .util import PropertyDict, to_urlparam, to_json_string

__all__ = ['Facility', 'Registry']


class FREDError(Exception):
    pass


class RegistryAPI(object):
    """
    Basic wrapper for the Facility Registry REST API.  Raises
    requests.HTTPError whenever a non-success HTTP status code is returned.

    url -- base URL for an API endpoint, without the slash
    username, password -- credentials for HTTP Basic Authentication

    """
    def __init__(self, url, username=None, password=None):
        self.url = url
        self.auth = (username, password) if username else None

    def request(self, method, path, **kwargs):
        r = requests.request(method, self.url + path, auth=self.auth, **kwargs)

        try:
            r.raise_for_status()
        except Exception as e:
            args = list(e.args)
            args[0] = args[0] + ". Response body was: {0}".format(
                    e.response.content)
            e.args = args
            raise

        return r

    def get(self, id):
        if not id:
            raise TypeError("Tried to get a facility with a null id.")

        r = self.request('GET', '/facilities/{id}.json'.format(id=id))
        r = r.json()
        print r
        return r

    def create(self, data):
        r = self.request('POST', '/facilities.json',
                         data=to_json_string(data),
                         headers={'Content-Type': 'application/json'})
        data = r.json()
        if 'url' not in data:
            data['url'] = r.headers['Location']

        return data

    def update(self, id, data):
        if not id:
            raise TypeError("Tried to update a facility with a null id.")

        r = self.request('PUT', '/facilities/{id}.json'.format(id=id),
                         data=to_json_string(data),
                         headers={'Content-Type': 'application/json'})
        return r.json()

    def delete(self, id):
        if not id:
            raise TypeError("Tried to delete a facility with a null id.")

        r = self.request('DELETE', '/facilities/{id}.json'.format(id=id))
        return r.content

    def list(self, params=None):
        params = params or {}

        r = self.request('GET', '/facilities.json', params=params)
        return r.json()


class Registry(object):
    """
    Main Facility Registry API.  Wraps responses from the REST API as Facility
    objects and delegates to FacilityQuery for constructing facility list
    queries via the registry.facilities attribute.

    url -- base API endpoint url, without trailing slash
    username, password -- HTTP Basic Authentication credentials
    facility_class -- an optional subclass of Facility to use for results

    """
    def __init__(self, url, username=None, password=None, facility_class=None):
        self.api = RegistryAPI(url, username=username, password=password)
        self.Facility = partial(facility_class or Facility, registry=self)

    def get(self, id):
        """Get the facility with id `id` from the server."""

        properties = self.api.get(id)
        return self.Facility(is_new=False, **properties)

    def create(self, prop_dict=None, **prop_kw):
        """Create a new Facility object without sending it to the server."""

        prop_kw.update(prop_dict or {})
        return self.Facility(**prop_kw)

    def save(self, facility):
        """
        Save a facility to the server, posting all of its extended properties
        and non-null core properties.

        """
        if facility['active'] is None:
            raise FREDError("active must not be None.")
        if facility['coordinates'] is None:
            raise FREDError("coordinates must not be None.")

        if facility['id']:
            self.api.update(facility['id'], facility.to_dict())
        else:
            data = self.api.create(facility.to_dict())
            for k, v in data.items():
                facility[k] = v

    def delete(self, facility):
        """Delete `facility` from the server."""

        self.api.delete(facility['id'])

    @property
    def facilities(self):
        return FacilityQuery(self._query_function)

    def _query_function(self, params):
        results = self.api.list(params=params)

        if isinstance(results, dict):
            # temporary handling of implementations that don't follow the spec
            results = ['facilities']

        for r in results:
            yield self.Facility(**r)


class Facility(object):
    """
    registry -- Registry object to bind to for save() and delete(). If you
        create a Facility without a registry, those methods won't work.
    is_new -- whether this is a new facility that hasn't been saved to the
        registry yet

    """

    CORE_PROPERTIES = [
        'name',
        'id',
        'url',
        'identifiers',
        'coordinates',
        'active',
        'createdAt',
        'updatedAt'
    ]

    DATE_PROPERTIES = [
        'createdAt',
        'updatedAt'
    ]

    def __init__(self, registry=None, is_new=True, properties=None,
                 **core_properties):
        properties = properties or {}

        core_properties['id'] = unicode(core_properties['id'])

        # ensure required core properties exist
        core_properties['active'] = core_properties.get('active', True)
        core_properties['identifiers'] = core_properties.get('identifiers', {})

        self.registry = registry
        self.is_new = is_new
        self._deleted = False

        self.core_properties = PropertyDict(
            (p, self._convert_date(p, core_properties.pop(p, None))) 
            for p in self.CORE_PROPERTIES)

        if core_properties:
            raise ValueError("Unrecognized core properties: %s" % 
                    ", ".join(core_properties))

        # extended properties defined in the 'properties' block
        self.extended_properties = PropertyDict(
            (p, self._convert_date(p, v)) for p, v in properties.items())
    
    def delete(self):
        if not self['id']:
            raise FREDError("Tried to delete an unsaved facility.")
        if self._deleted:
            raise FREDError("Tried to delete a deleted facility.")

        self.registry.delete(self)
        self._deleted = True

    def save(self):
        if self._deleted:
            raise FREDError("Tried to save a deleted facility.")

        self.registry.save(self)
        self.is_new = False
        self.core_properties.is_modified = False
        self.extended_properties.is_modified = False

    @property
    def is_modified(self):
        return (self.is_new or self.core_properties.is_modified or
                self.extended_properties.is_modified)

    def to_dict(self):
        return dict(self.__iter__())

    def __iter__(self):
        for prop, val in self.core_properties.items():
            if val is not None:
                yield (prop, val)

        yield ('properties', self.extended_properties)

    def __getitem__(self, name):
        if name == 'properties':
            return self.extended_properties
        elif name in self.CORE_PROPERTIES:
            return self.core_properties[name]
        else:
            raise KeyError("Invalid key: %s" % name)

    def __setitem__(self, name, val):
        if self._deleted:
            raise FREDError("Tried to modify a deleted facility.")

        if name == 'properties':
            self.extended_properties = PropertyDict(val)
        elif name in self.CORE_PROPERTIES:
            self.core_properties[name] = val
        else:
            raise KeyError("Invalid key: %s" % name)

    def get_identifiers_by_agency(agency):
        """Returns the identifiers property filtered by agency as a list."""
        raise NotImplementedError()

    def get_identifiers_by_context(context):
        """Returns the identifiers property filtered by context as a list."""
        raise NotImplementedError()

    def _convert_date(self, key, val):
        if val is None:
            return val
        elif key in self.DATE_PROPERTIES:
            return dateutil.parser.parse(val)
        else:
            return val


class FacilityQuery(object):
    """
    Fluent API for constructing a facility query, including sorting, filtering,
    and partial responses.

    query_function -- a function that takes a dict of url parameters and
        and returns an iterable of Facility objects

    """
    def __init__(self, query_function):
        self.query_function = query_function

        self.filter_dict = {}
        self.sort_asc_prop_name = None
        self.sort_desc_prop_name = None
        self.sort_clauses = ()
        self.select_properties = ()

    def filter(self, filter_dict=None, **filter_kw):
        filter_kw.update(filter_dict or {})
        self.filter_dict.update(filter_kw)

        return self

    def sort(self, clauses):
        if self.is_sorted:
            raise FREDError()

        raise NotImplementedError()

    def sort_asc(self, prop):
        if self.is_sorted:
            raise FREDError()

        self.sort_asc_prop_name = prop

        return self

    def sort_desc(self, prop):
        if self.is_sorted:
            raise FREDError()

        self.sort_desc_prop = prop

        return self

    def select(self, *properties):
        self.select_properties = tuple(properties)
        return self
   
    def range(self, start=0, end=None, page_size=None):
        # todo: slicing (user-facing) and pagination (api-facing)

        return self.query_function(self.params)

    def all(self, **kwargs):
        return self.range(**kwargs)

    def __iter__(self):
        return self.all()

    @property
    def is_sorted(self):
        return (self.sort_asc_prop_name or self.sort_desc_prop_name or
                self.sort_clauses)

    @property
    def params(self):
        params = {}
        if self.select_properties:
            params['fields'] = ','.join(self.select_properties)
            params['allProperties'] = False
        else:
            params['allProperties'] = True

        if self.sort_asc_prop_name:
            params['sortAsc'] = self.sort_asc_prop_name
        if self.sort_desc_prop_name:
            params['sortDesc'] = self.sort_desc_prop_name

        params.update(self.filter_dict)

        return dict((k, to_urlparam(v)) for k, v in params.items())
