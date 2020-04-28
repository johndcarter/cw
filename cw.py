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
    developer_registry = DeveloperRegistry()
    print(f'Loading team data from: {args.team_csv}')
    developer_registry.load_from_csv(args.team_csv)
    for k, v in developer_registry.teams.items():
        print(f'\t{k} : {len(v)} members')
    print(f'Loaded {len(developer_registry.teams)} teams')

    commits_sorted = sorted(repo.iter_commits(rev='develop', since=args.since), key=(lambda c: c.committed_datetime))

    change_count_for_file_by_author = {}
    current = 1

    # 'indexing' happens here
    for commit in commits_sorted:
        print(f'Processing {current} of {len(commits_sorted)}')
        for file_name in commit.stats.files.keys():
            if args.pattern in file_name:
                # get the dictionary of changes for the file, or init a new one
                temp_dict = change_count_for_file_by_author.get(str(file_name), {})

                # for the author of the commit, add or increment the change count in the temporary
                temp_dict[str(commit.author.email).lower()] = temp_dict.get(str(commit.author.email).lower(), 0) + 1

                # store the update
                change_count_for_file_by_author[str(file_name)] = temp_dict

        current = current + 1

    # sum up team changes
    change_count_for_file_by_team = {}

    for file_name, author_changes in change_count_for_file_by_author.items():
        counts_by_team = {}
        for who, count in author_changes.items():
            dev_tuple = developer_registry.find_developer_by_email(who)

            # if we found the author, add one to their change count for that team
            if dev_tuple:
                counts_by_team[dev_tuple[1]] = counts_by_team.get(dev_tuple[1], 0) + count
        change_count_for_file_by_team[file_name] = counts_by_team

    print(f'Queried Range: {commits_sorted[0].committed_datetime} <-> {commits_sorted[-1].committed_datetime}')

    # reports
    # what are the most changed files by each team?

    changes_by_team = {}
    # for team in developer_registry.teams.keys():
    #     ch
    #     for file_name, change_count_by_team in change_count_for_file_by_team[team].items():



    # write graph
    G = nx.Graph()

    # add nodes for all files
    for file_name, _ in change_count_for_file_by_author.items():
        G.add_node(file_name)
    G.add_nodes_from(developer_registry.teams.keys())

    for file_name, team_change_dict in change_count_for_file_by_team.items():
        for team_name, change_count in team_change_dict.items():
            G.add_edge(team_name, file_name, label=change_count)

    # pos = nx.nx_pydot.graphviz_layout(G)
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
    parser.add_argument('since', type=str, help='Examine commits since this date, format: YYYY-MM-DD')
    parser.add_argument('team_csv', type=str, help='CSV file to read team data and email aliases from')
    args = parser.parse_args()
    main(args)
