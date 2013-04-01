import requests
from functools import partial
from .util import PropertyDict, to_urlparam, to_json_string

__all__ = ['Facility', 'Registry']


# These functions encapsulate differences between JSON representations of a
# facility for different provider implementations as we move towards a
# finalized version of the API.
def transform_incoming_data(data, url):
    if 'resmap' in url:
        data['uuid'] = data.pop('id')
        data['href'] = data.pop('url')

    return data

def transform_outgoing_data(data, url):
    if 'resmap' in url:
        if 'uuid' in data:
            data['id'] = data.pop('uuid')
        if 'href' in data:
            data['url'] = data.pop('href')

        data.pop('createdAt', None)
        data.pop('updatedAt', None)
        data.pop('url', None)
        data.pop('id', None)
    
    return data


class FredError(Exception):
    pass

class FredHttpError(FredError):
    pass

class FredAuthenticationError(FredHttpError):
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
            from pprint import pformat

            args = list(e.args)
            args[0] = (args[0] + "\n\nRequest was:\n\n{0} {1}\n\n{2}".format(
                           method, self.url + path, pformat(kwargs)) +
                            "\n\nResponse body was: \n\n{0}".format(
                                e.response.content))

            if e.response.status_code == 401:
                exception_class = FredAuthenticationError
            else:
                exception_class = FredHttpError

            exc = exception_class(*args)
            exc.response = e.response

            try:
                exc.fred_error_info = e.response.json()
            except Exception:
                exc.fred_error_info = None

            raise exc

        return r

    def get(self, id):
        if not id:
            raise TypeError("Tried to get a facility with a null id.")

        r = self.request('GET', '/facilities/{id}.json'.format(id=id))
        data = r.json()

        return transform_incoming_data(data, self.url)

    def create(self, data):
        data = transform_outgoing_data(data, self.url)

        r = self.request('POST', '/facilities.json',
                         data=to_json_string(data),
                         headers={'Content-Type': 'application/json'})
        data = r.json()
        if 'href' not in data:
            data['href'] = r.headers['Location']

        return transform_incoming_data(data, self.url)

    def update(self, id, data):
        data = transform_outgoing_data(data, self.url)

        if not id:
            raise TypeError("Tried to update a facility with a null id.")

        r = self.request('PUT', '/facilities/{id}.json'.format(id=id),
                         data=to_json_string(data),
                         headers={'Content-Type': 'application/json'})

        return transform_incoming_data(r.json(), self.url)

    def delete(self, id):
        if not id:
            raise TypeError("Tried to delete a facility with a null id.")

        r = self.request('DELETE', '/facilities/{id}.json'.format(id=id))
        return r.content

    def list(self, params=None):
        params = params or {}

        r = self.request('GET', '/facilities.json', params=params)
        json = r.json()
        json['facilities'] = [transform_incoming_data(f, self.url) for f in json['facilities']]

        return json


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

        data = self.api.get(id)

        return self.Facility(new=False, **data)

    def create(self, prop_dict=None, **prop_kw):
        """Create a new Facility object without sending it to the server."""

        prop_kw.update(prop_dict or {})
        return self.Facility(**prop_kw)

    def save(self, facility):
        """Save a facility to the server."""

        if facility['active'] is None:
            raise FredError("active must not be None.")
        if facility['coordinates'] is None:
            raise FredError("coordinates must not be None.")

        data = facility.to_dict()
        uuid = data.get('uuid')

        if uuid:
            return self.api.update(uuid, data)
        else:
            return self.api.create(data)

    def delete(self, facility):
        """Delete `facility` from the server."""

        self.api.delete(facility['uuid'])

    @property
    def facilities(self):
        return FacilityQuery(self._query_function)

    def _query_function(self, params, partial=False):
        results = self.api.list(params=params)['facilities']

        for r in results:
            yield self.Facility(partial=partial, **r)


class Facility(object):
    """
    registry -- Registry object to bind to for save() and delete(). If you
        create a Facility without a registry, those methods won't work.
    new -- whether this is a new facility that hasn't been saved to the
        registry yet
    partial -- whether this is data from a facility list partial response with
        only some fields

    The remaining keyword arguments are properties of the facility as defined
    in the Facility Registry API spec with defaults of None, except for active
    which has a default of True.

    """

    DATE_PROPERTIES = (
        'createdAt',
        'updatedAt'
    )

    EXTENDED_DATE_PROPERTIES = ()

    def __init__(self, registry=None, new=True, partial=False, **kwargs):
        self.registry = registry
        self._new = new
        self._partial = partial
        self._deleted = False
        
        self.data = self._get_property_dict(**kwargs)
        
    def delete(self):
        if not self['uuid']:
            raise FredError("Tried to delete an unsaved facility.")
        if self._deleted:
            raise FredError("Tried to delete a deleted facility.")

        self.registry.delete(self)
        self._deleted = True

    def save(self):
        if self._deleted:
            raise FredError("Tried to save a deleted facility.")
        # remove once partial updates is implemented
        if self._partial:
            raise FredError("Tried to save a partial response facility.")

        data = self.registry.save(self)
        self.data = self._get_property_dict(**data)
        self._new = False

    @property
    def is_touched(self):
        return (self._new or self.data.is_touched)

    @property
    def is_modified(self):
        return (self._new or self.data.is_modified)

    def to_dict(self):
        return dict(self.__iter__())

    def __iter__(self):
        for prop, val in self.data.items():
            if val is not None:
                yield (prop, val)

    def __getitem__(self, name):
        return self.data[name]

    def __setitem__(self, name, val):
        if self._deleted:
            raise FredError("Tried to modify a deleted facility.")

        if name == 'properties':
            raise FredError("Can't reassign the extended properties property.")

        self.data[name] = val

    def get_identifiers(self, agency=None, context=None):
        """
        Returns a list of identifiers matching agency and context.

        """
        return [id for id in self['identifiers']
                if ((agency == id['agency'] or agency is None) and
                    (context == id['context'] or context is None))]

    def _get_property_dict(self, uuid=None, name=None, href=None,
                           identifiers=None, coordinates=None, active=True,
                           createdAt=None, updatedAt=None, properties=None):
        properties = PropertyDict(
            properties or {},
            date_properties=self.EXTENDED_DATE_PROPERTIES)

        return PropertyDict({
            'uuid': unicode(uuid) if uuid else uuid,
            'name': name,
            'href': href,
            'identifiers': identifiers or [],
            'coordinates': coordinates,
            'active': active,
            'createdAt': createdAt,
            'updatedAt': updatedAt,
            'properties': properties
        }, date_properties=self.DATE_PROPERTIES)


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

        self._executed = False

    def filter(self, filter_dict=None, **filter_kw):
        filter_kw.update(filter_dict or {})
        self.filter_dict.update(filter_kw)

        return self

    def sort(self, clauses):
        if self.is_sorted:
            raise FredError()

        raise NotImplementedError()

    def sort_asc(self, prop):
        if self.is_sorted:
            raise FredError()

        self.sort_asc_prop_name = prop

        return self

    def sort_desc(self, prop):
        if self.is_sorted:
            raise FredError()

        self.sort_desc_prop = prop

        return self

    def select(self, *properties):
        self.select_properties = tuple(properties)
        return self

    def range(self, start=None, end=None, page_size=None):
        if self._executed:
            raise FredError("Tried to re-execute an executed query.")

        start = start or 0
        page_size = page_size or (end - start if end else 'off')

        params = self.params
        params.update({
            'offset': start,
            'limit': page_size
        })

        self._executed = True

        return self.query_function(params, partial=self.select_properties)

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
