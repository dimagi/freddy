import unittest
import freddy
from dateutil.parser import parse
import datetime
import pytz
import requests
import time

def random_string():
    import random
    import string
    return ''.join([random.choice(string.ascii_uppercase + string.digits)
                    for i in range(16)])


def utcnow():
    # Resource Map doesn't handle ISO8601 timestamps with microseconds
    return datetime.datetime.utcnow().replace(
            tzinfo=pytz.utc, microsecond=0)


class TestFacilityRegistry(unittest.TestCase):
    url = None
    username = None
    password = None

    existing_facility = None
    inactive_facility_uuid = None
    inactive_facilities_count_upper_bound = None

    # a datetime.datetime such that some facilities on the server were last
    # updated before it and some after it
    updated_since_test_date = None

    def setUp(self):
        self.registry = freddy.Registry(
                self.url, username=self.username, password=self.password)

        self._created_facility_uuids = []

    def tearDown(self):
        for uuid in self._created_facility_uuids:
            self.registry.api.delete(uuid)
    
    def _create_facility(self):
        facility = self.registry.create(
            name=random_string(), coordinates=[32.1, -23.20])

        facility.save()
        self._created_facility_uuids.append(facility['uuid'])

        return facility

    def test_get_facility(self):
        identifiers = self.existing_facility.pop('identifiers')

        facility = self.registry.get(self.existing_facility['uuid'])

        self.assertTrue(facility['href'])
        self.assertIsInstance(facility['updatedAt'], datetime.datetime)
        self.assertIsInstance(facility['properties'], dict)
       
        # can't do set(list of dicts)
        self.assertTrue(
            all(id in facility['identifiers'] for id in identifiers)
                and
            all(id in identifiers for id in facility['identifiers'])
        )

        for field, value in self.existing_facility.items():
            self.assertEqual(value, facility[field])

    def test_create_facility(self):

        facility = self._create_facility()

        self.assertTrue(facility['uuid'])
        self.assertTrue(facility['createdAt'])
        self.assertTrue(facility['updatedAt'])

        r = requests.get(facility['href'])
        #r.raise_for_status()

        created_at = utcnow() - datetime.timedelta(minutes=1)
        same_facility = self.registry.get(facility['uuid'])
        self.assertLess(created_at, same_facility['createdAt'])
        self.assertLess(created_at, same_facility['updatedAt'])
        for k, v in same_facility:
            if (k not in ('createdAt', 'updatedAt') and
                k != 'properties'):  # test server creates default properties?
                self.assertEqual(v, facility[k])

    def test_update_facility(self):
        facility = self._create_facility()
        self.assertFalse(facility.is_modified)

        facility['name'] = random_string()
        self.assertTrue(facility.is_modified)

        facility.save()

        self.assertFalse(facility.is_modified)

        same_facility = self.registry.get(facility['uuid'])
        self.assertEqual(facility['name'], same_facility['name'])

    def test_update_existing_facility(self):
        facility = self.registry.get(self.existing_facility['uuid'])
        old_name = facility['name']

        new_name = facility['name'] + ' ' + random_string()
        facility['name'] = new_name

        facility.save()
        self.assertEqual(facility['name'], new_name)

        same_facility = self.registry.get(facility['uuid'])
        self.assertEqual(same_facility['name'], new_name)

        same_facility['name'] = old_name
        same_facility.save()

    def test_delete_facility(self):
        facility = self._create_facility()
        facility.delete()

        with self.assertRaises(freddy.FREDError):
            facility['name'] = 'foo'

        with self.assertRaises(freddy.FREDError):
            facility.save()

        with self.assertRaises(freddy.FREDError):
            facility.delete()

        with self.assertRaises(requests.HTTPError):
            self.registry.get(facility['uuid'])

        with self.assertRaises(requests.HTTPError):
            self.registry.api.delete(facility['uuid'])

        self._created_facility_uuids = []

    def test_filter_by_inactive(self):
        facilities = list(self.registry.facilities.filter(active=False).all())

        self.assertTrue(any(f['uuid'] == self.inactive_facility_uuid
                            for f in facilities))

        self.assertGreater(
                self.inactive_facilities_count_upper_bound, len(facilities))

    def test_inactive_facilities_iteration(self):
        for f in self.registry.facilities.filter(active=False):
            if f['uuid'] == self.inactive_facility_uuid:
                return

        self.fail("inactive facility {0} not found".format(
                self.inactive_facility_uuid))

    @unittest.expectedFailure
    def test_get_facility_partial_response(self):
        facilities = self.registry.facilities.filter(
            active=False
        ).select('href', 'createdAt')

        for f in facilities:
            self.assertEqual(None, f['name'])
            self.assertTrue(f['createdAt'])
            self.assertTrue(f['href'])

    def test_filter_by_updated_since(self):
        date = self.updated_since_test_date

        all_facilities = list(self.registry.facilities.all())
        facilities = list(self.registry.facilities.filter(updatedSince=date))

        self.assertLess(len(facilities), len(all_facilities))
        self.assertTrue(all(f['updatedAt'] >= date for f in facilities))

    def test_filter_that_returns_empty_resultset_format(self):
        """ResourceMap was returning {} instead of {facilities: []}"""

        time.sleep(2)
        date = utcnow() - datetime.timedelta(seconds=1)

        list(self.registry.facilities.filter(updatedSince=date))


class TestDHIS2FacilityRegistry(TestFacilityRegistry):
    url = 'http://apps.dhis2.org/dev/api-fred/v1'
    username = 'system'
    password = 'System123'

    existing_facility = {
        'uuid': 'b1c9eff6-92e0-465b-8e33-71012171eeb2',
        'name': " Panderu MCHP",
        'createdAt': parse("2012-02-17T14:54:39.987+0000"),
        'identifiers': [
            {
                "id": "OU_222702",
                "context": "DHIS2_CODE",
                "agency": "DHIS2"
            },
            {
                'agency': 'DHIS2',
                'context': 'DHIS2_UID',
                'id': 'ueuQlqb8ccl'
            }
        ]
    }

    inactive_facility_uuid = "5d9fbd1d-a2f5-441d-9238-60ae94f327b0"
    inactive_facilities_count_upper_bound = 10

    updated_since_test_date = parse("2013-03-21T18:09:52")


class TestResourceMapFacilityRegistry(TestFacilityRegistry):
    url = 'http://resmap-stg.instedd.org/collections/713/fred_api/v1'
    username = 'mwhite@dimagi.com'
    password = 'password'

    existing_facility = {
        "uuid": "97911",
        "name": "test facility 1",
        "createdAt": parse("2013-02-05T03:25:27Z"),
        'identifiers': [],
        'coordinates': [90.0, 10.0]
    }

    updated_since_test_date = parse("2013-02-05T04:55:59Z")


if __name__ == '__main__':
    # remove abstract parameterized testcase from scope so it doesn't get
    # tested
    del TestFacilityRegistry

    unittest.main()
