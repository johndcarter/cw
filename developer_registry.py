import csv
import unittest


class DeveloperRegistry(object):

    # makes a friendly name from an email
    # in general, will just take everything before the @
    # but will drop anything before a + to compensate for anonymous github emails
    # will fallback to the whole string if parsing breaks down
    def make_name_from_email(email: str) -> str:
        plus_index = email.find('+')
        plus_index = 0 if plus_index == -1 else plus_index + 1
        at_index = email.find('@')
        at_index = len(email) if at_index == -1 else at_index
        return email[plus_index:at_index]

    class DeveloperID(object):
        def __init__(self, emails: list):
            self.name = DeveloperRegistry.make_name_from_email(emails[0])
            self.emails = set(emails)

        def matches_email(self, email: str) -> bool:
            return email in self.emails

        def add_email(self, email: str):
            self.emails.add(email)

        def __str__(self):
            return f'{self.name} : {",".join(self.emails)}'

    def __init__(self):
        self.teams = {}

    def set_team_for_developer(self, dev_id: DeveloperID, team: str):
        dev_tuple = self.find_developer_by_email(list(dev_id.emails)[0])
        if dev_tuple:
            self.teams[dev_tuple[1]].remove(dev_tuple[0])

        if team not in self.teams:
            self.teams[team] = []

        self.teams[team].append(dev_id)

    def find_developer_by_email(self, email) -> (DeveloperID, str):
        for (team_name, team_members) in self.teams.items():
            for developer_id in team_members:
                if developer_id.matches_email(email):
                    return developer_id, team_name
        return None

    def load_from_csv(self, filename):
        with open(filename) as csvfile:
            csv_reader = csv.reader(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for row in csv_reader:
                email_list = [row[0]]
                if row[2]:
                    email_list = email_list + row[2].split(',')
                self.set_team_for_developer(DeveloperRegistry.DeveloperID(email_list), row[1])


class TestDeveloperRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = DeveloperRegistry()
        self.alice = DeveloperRegistry.DeveloperID(['alice@restaurant.com'])
        self.bob = DeveloperRegistry.DeveloperID(['bob@dogs.com'])
        self.carol = DeveloperRegistry.DeveloperID(['carol@christmas.com', 'anonymous@remailer.com'])

    def test_make_name_from_email(self):
        self.assertEqual('alice', DeveloperRegistry.make_name_from_email('123+alice@email.ca'))
        self.assertEqual('bob', DeveloperRegistry.make_name_from_email('bob@test.com'))
        self.assertEqual('carol', DeveloperRegistry.make_name_from_email('carol'))

    def test_developer_id(self):
        alice = DeveloperRegistry.DeveloperID(['123+alice@email.ca', 'alice124@contact.com'])
        self.assertEqual('alice', alice.name)
        self.assertTrue(alice.matches_email('123+alice@email.ca'))
        self.assertTrue(alice.matches_email('alice124@contact.com'))
        self.assertEqual(2, len(alice.emails))

        alice.add_email('a@a.ca')
        self.assertTrue(alice.matches_email('a@a.ca'))
        self.assertEqual(3, len(alice.emails))

    def test_add_developers_to_teams(self):
        self.registry.set_team_for_developer(self.alice, 'alpha')
        self.registry.set_team_for_developer(self.bob, 'beta')
        self.registry.set_team_for_developer(self.carol, 'alpha')

        (_, team) = self.registry.find_developer_by_email('alice@restaurant.com')
        self.assertEqual('alpha', team)
        (_, team) = self.registry.find_developer_by_email('anonymous@remailer.com')
        self.assertEqual('alpha', team)

        self.assertEqual(2, len(self.registry.teams['alpha']))
        self.assertEqual(1, len(self.registry.teams['beta']))

        self.registry.set_team_for_developer(self.bob, 'alpha')

        self.assertEqual(3, len(self.registry.teams['alpha']))
        self.assertEqual(0, len(self.registry.teams['beta']))

        self.registry.set_team_for_developer(self.alice, 'alpha-prime')
        self.assertEqual(2, len(self.registry.teams['alpha']))
        self.assertEqual(0, len(self.registry.teams['beta']))
        self.assertEqual(1, len(self.registry.teams['alpha-prime']))

        (_, team) = self.registry.find_developer_by_email('alice@restaurant.com')
        self.assertEqual('alpha-prime', team)