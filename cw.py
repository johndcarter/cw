import argparse
import csv

from git import Repo


def main(args):
    print(f'Repo: {args.path_to_repo}')
    print(f'Matching changes to: {args.pattern}')

    repo = Repo(args.path_to_repo)

    csv_file = open(args.commits_output, mode='w')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(['datetime', 'author', 'message', 'link']) # csv headers

    commits_sorted = sorted(repo.iter_commits(rev='develop', since='2019-01-01'), key=(lambda c: c.committed_datetime))

    files_change_count = {}
    rows = []
    current = 1

    for commit in commits_sorted:
        print(f'Processing {current} of {len(commits_sorted)}')
        found = False
        for file in commit.stats.files.keys():
            if args.pattern in file:
                found = True
                files_change_count[str(file)] = files_change_count.get(str(file), 0) + 1

        if found:
            rows.append([commit.committed_datetime, commit.author, commit.message,
                         f'=HYPERLINK("{args.url_prefix}{commit.hexsha}", "{commit.hexsha}")'])

        current = current + 1

    # sort by date
    csv_writer.writerows(rows)
    csv_file.close()
    print(f'Wrote commits to: {args.commits_output}')
    print(f'Matched {len(rows)} commits of {len(commits_sorted)} ({len(rows) / len(commits_sorted) * 100.0:.2f}%)')
    print(f'Matched Range: {rows[0][0]} <-> {rows[-1][0]}')
    print(f'Queried Range: {commits_sorted[0].committed_datetime} <-> {commits_sorted[-1].committed_datetime}')

    csv_file = open(args.authors_output, mode='w')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(['author', 'commit count']) # csv headers
    rows = []

    by_committer = {}
    for commit in commits_sorted:
        by_committer[str(commit.author)] = by_committer.get(str(commit.author), 0) + 1

    for author in sorted(by_committer.keys()):
        rows.append([author, by_committer[author]])

    csv_writer.writerows(rows)
    csv_file.close()
    print(f'Wrote author counts to: {args.authors_output}')

    rows = []
    csv_file = open(args.files_output, mode='w')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(['file', 'change count'])
    for file in sorted(files_change_count.keys()):
        rows.append([file, files_change_count[file]])
    csv_writer.writerows(rows)
    csv_file.close()
    print(f'Wrote flile counts to: {args.files_output}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Change watcher')
    parser.add_argument('path_to_repo', type=str, help='Path to git repository')
    parser.add_argument('pattern', type=str, help='String to match')
    parser.add_argument('url_prefix', type=str,
                        help='What to append a SHA to build a link to the commit on github (with slash)')
    parser.add_argument('commits_output', type=str, help='CSV file to write to commit data to')
    parser.add_argument('authors_output', type=str, help='CSV file to write author info to')
    parser.add_argument('files_output', type=str, help='CSV file to file change info to')
    args = parser.parse_args()
    main(args)
