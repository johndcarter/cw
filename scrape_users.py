import argparse
import Levenshtein
import csv

from functools import partial
from git import Repo


# give a set of email, will return them as an ordered list based on Levenshtein distance
def get_possible_aliases(email: str, emails: set) -> list:
    levenshtein_key = partial(Levenshtein.distance, email)
    return sorted(emails, key=levenshtein_key)[1:]  # will always find itself in list, don't return it


def main(args):
    repo = Repo(args.path_to_repo)
    email_set = set()
    for commit in repo.iter_commits(rev='develop', since='2019-01-01'):
        email_set.add(str(commit.author.email).lower())

    rows = []
    for email in email_set:
        rows.append([email, '', ','.join(get_possible_aliases(email, email_set)[0:5])])

    print(' * Writing')
    with open(args.output, mode='w') as csv_file:
        writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['Email', 'Team', 'Aliases (emails, comma separated)'])
        writer.writerows(rows)
    print(' * Writing Complete')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Build a list of users from a git repo')
    parser.add_argument('path_to_repo', type=str, help='Path to git repository')
    parser.add_argument('output', type=str, help='File to output to')
    args = parser.parse_args()
    main(args)
