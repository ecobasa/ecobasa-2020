from django.test import TestCase


class HomepageTestCase(TestCase):
    def test_get(self):
        response = self.client.get("/")
        self.assertContains(response, "Ecobasa")
