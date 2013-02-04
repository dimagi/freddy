import unittest
import freddy
from dateutil.parser import parse
import datetime
import pytz
import requests

INACTIVE_FACILITY_ID = 'cdmkMyYv04T'


def random_string():
    import random
    import string
    return random.choice(['asdf', 'hjkl', 'qwe', 'weurio', 'oyrewiuwer',
        'werer'])
    return ''.join([random.choice(string.ascii_uppercase + string.digits)
                    for i in range(16)])


def utcnow():
    return datetime.datetime.utcnow().replace(tzinfo=pytz.utc)


class TestFacilityRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = freddy.Registry(
            'http://apps.dhis2.org/dev/api-fred/v1',
            username='system', password='System123')

        self._created_facility_ids = []

    def tearDown(self):
        for id in self._created_facility_ids:
            self.registry.api.delete(id)

    def test_get_facility(self):
        id = 'ueuQlqb8ccl'
        name = " Panderu MCHP"
        createdAt = parse("2012-02-17T14:54:39.987+0000")
        identifiers = [{
            "id": "OU_222702",
            "context": "DHIS2_CODE",
            "agency": "DHIS2"
        }]

        facility = self.registry.get(id)

        self.assertEqual(id, facility['id'])
        self.assertIn(id, facility['url'])
        self.assertEqual(name, facility['name'])
        self.assertEqual(createdAt, facility['createdAt'])
        self.assertIsInstance(facility['updatedAt'], datetime.datetime)
        self.assertEqual(identifiers, facility['identifiers'])
        self.assertEqual(4, facility['properties']['level'])
    
    def _create_facility(self):
        facility = self.registry.create(
            name=random_string(), coordinates=[32.1, -23.20])

        facility.save()
        self._created_facility_ids.append(facility['id'])

        return facility

    def test_create_facility(self):

        facility = self._create_facility()
        self.assertTrue(facility['id'])
        self.assertIsNone(facility['createdAt'])
        self.assertIsNone(facility['updatedAt'])

        r = requests.get(facility['url'])
        r.raise_for_status()

        created_at = utcnow() - datetime.timedelta(minutes=1)
        same_facility = self.registry.get(facility['id'])
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

        same_facility = self.registry.get(facility['id'])
        self.assertEqual(facility['name'], same_facility['name'])

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
            self.registry.get(facility['id'])

        with self.assertRaises(requests.HTTPError):
            self.registry.api.delete(facility['id'])

        self._created_facility_ids = []

    def test_filter_by_inactive(self):
        facilities = list(self.registry.facilities.filter(active=False).all())
        
        id = INACTIVE_FACILITY_ID

        self.assertTrue(any(f['id'] == id for f in facilities))
        self.assertGreater(10, len(facilities))

    def test_facilities_iteration(self):
        for f in self.registry.facilities.filter(active=False):
            if f['id'] == INACTIVE_FACILITY_ID:
                self.assertTrue(True)
                return

        self.assertTrue(False)

    def test_get_facility_partial_response(self):
        return  # server error

        facilities = self.registry.facilities.filter(
            active=False
        ).select('url', 'createdAt')

        for f in facilities:
            self.assertEqual(None, f['name'])
            self.assertTrue(f['createdAt'])
            self.assertTrue(f['url'])

    def test_filter_by_updated_since(self):
        date = utcnow() - datetime.timedelta(days=200)

        all_facilities = list(self.registry.facilities.all())
        facilities = list(self.registry.facilities.filter(updatedSince=date))

        self.assertLess(len(facilities), len(all_facilities))
        self.assertTrue(all(f['updatedAt'] >= date for f in facilities))

    def test_filter_that_returns_empty_resultset(self):
        date = utcnow() - datetime.timedelta(seconds=1)

        list(self.registry.facilities.filter(updatedSince=date))


if __name__ == '__main__':
    unittest.main()
