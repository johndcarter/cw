import argparse
import csv

from developer_registry import DeveloperRegistry
from git import Repo
from networkx import nx_pydot
import networkx as nx
from networkx.drawing.nx_pydot import write_dot
import matplotlib.pyplot as plt


def main(args):
    print(f'Repo: {args.path_to_repo}')
    print(f'Matching changes to: {args.pattern}')

    repo = Repo(args.path_to_repo)
    teams = DeveloperRegistry()
    print(f'Loading team data from: {args.team_csv}')
    teams.load_from_csv(args.team_csv)
    for k, v in teams.teams.items():
        print(f'\t{k} : {len(v)} members')

    print(f'Loaded {len(teams.teams)} teams')

    csv_file = open(args.commits_output, mode='w')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(['datetime', 'author', 'message', 'link'])  # csv headers

    commits_sorted = sorted(repo.iter_commits(rev='develop', since='2020-03-01'), key=(lambda c: c.committed_datetime))

    files_change_count = {}
    who_changed = {}
    rows = []
    current = 1

    for commit in commits_sorted:
        print(f'Processing {current} of {len(commits_sorted)}')
        found = False
        for file_name in commit.stats.files.keys():
            if args.pattern in file_name:
                found = True
                files_change_count[str(file_name)] = files_change_count.get(str(file_name), 0) + 1
                change_dict = who_changed.get(str(file_name), {})
                change_dict[str(commit.author.email).lower()] = change_dict.get(str(commit.author.email).lower(), 0) + 1
                who_changed[str(file_name)] = change_dict

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
    csv_writer.writerow(['author', 'commit count'])  # csv headers
    rows = []

    by_committer = {}
    for commit in commits_sorted:
        by_committer[str(commit.author)] = by_committer.get(str(commit.author), 0) + 1

    for author in sorted(by_committer.keys()):
        rows.append([author, by_committer[author]])

    csv_writer.writerows(rows)
    csv_file.close()
    print(f'Wrote author counts to: {args.authors_output}')

    # file change counts

    rows = []
    csv_file = open(args.files_output, mode='w')
    csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(['file', 'change count'])
    for file_name in sorted(files_change_count.keys()):
        rows.append([file_name, files_change_count[file_name]])
    csv_writer.writerows(rows)
    csv_file.close()
    print(f'Wrote file counts to: {args.files_output}')

    # write graph
    G = nx.Graph()

    # add nodes for all files
    for file_name, _ in who_changed.items():
        G.add_node(file_name)
    G.add_nodes_from(teams.teams.keys())

    # sum up team changes
    team_changed = {}

    for file_name, change_dict in who_changed.items():
        counts_by_team = {}
        for who, count in change_dict.items():
            dev_tuple = teams.find_developer_by_email(who)
            if dev_tuple:
                counts_by_team[dev_tuple[1]] = counts_by_team.get(dev_tuple[1], 0) + count
        team_changed[file_name] = counts_by_team

    for file_name, team_change_dict in team_changed.items():
        for team_name, change_count in team_change_dict.items():
            G.add_edge(team_name, file_name, label=change_count)

    #pos = nx.nx_pydot.graphviz_layout(G)
    pos = nx.drawing.circular_layout(G)
    nx.draw_networkx(G, pos)
    labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=labels)
    nx.drawing.nx_pydot.write_dot(G, 'test.dot')
    print('Done')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Change watcher')
    parser.add_argument('path_to_repo', type=str, help='Path to git repository')
    parser.add_argument('pattern', type=str, help='String to match')
    parser.add_argument('url_prefix', type=str,
                        help='What to append a SHA to build a link to the commit on github (with slash)')
    parser.add_argument('commits_output', type=str, help='CSV file to write to commit data to')
    parser.add_argument('authors_output', type=str, help='CSV file to write author info to')
    parser.add_argument('files_output', type=str, help='CSV file to file change info to')
    parser.add_argument('team_csv', type=str, help='CSV file to read team data and email aliases from')
    args = parser.parse_args()
    main(args)
