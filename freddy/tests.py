import unittest
from . import Registry
from dateutil.parser import parse
import datetime

INACTIVE_FACILITY_ID = 'cdmkMyYv04T'


class TestFacilityRegistry(unittest.TestCase):
    
    def setUp(self):
        self.registry = Registry('http://apps.dhis2.org/dev/api-fred/v1/',
                username='system', password='System123')

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

    def test_filter_inactive_facilities(self):
        facilities = self.registry.facilities.filter(active=False).all()
        
        id = INACTIVE_FACILITY_ID

        self.assertTrue(any(f['id'] == id for f in facilities))

    def test_facilities_iteration(self):
        for f in self.registry.facilities.filter(active=False):
            if f['id'] == INACTIVE_FACILITY_ID:
                self.assertTrue(True)
                return

        self.assertTrue(False)

    def test_get_facility_partial_response(self):
        return  # server error (probably)

        facilities = self.registry.facilities.filter(
            active=False
        ).select('url', 'createdAt')

        for f in facilities:
            self.assertEqual(None, f['name'])


if __name__ == '__main__':
    unittest.main()

