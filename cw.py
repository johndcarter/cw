import argparse

from developer_registry import DeveloperRegistry
from git import Repo
import networkx as nx


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
    change_count_for_file_by_team = {}
    current = 1

    # 'indexing' happens here
    for commit in commits_sorted:
        print(f'Processing {current} of {len(commits_sorted)}')
        for file_name in commit.stats.files.keys():

            if args.pattern in file_name:
                author_temp = str(commit.author.email.lower())

                # get the dictionary of changes for the file, or init a new one
                temp_dict = change_count_for_file_by_author.get(str(file_name), {})

                # for the author of the commit, add or increment the change count in the temporary
                temp_dict[author_temp] = temp_dict.get(author_temp, 0) + 1

                # store the update
                change_count_for_file_by_author[str(file_name)] = temp_dict

                dev_tuple = developer_registry.find_developer_by_email(author_temp)

                # we found the team for that developer
                if dev_tuple:
                    # get the dictionary of changes for that file, or init a new one
                    temp_team_dict = change_count_for_file_by_team.get(file_name, {})

                    # increment it
                    temp_team_dict[dev_tuple[1]] = temp_team_dict.get(dev_tuple[1], 0) + 1

                    # store the update
                    change_count_for_file_by_team[file_name] = temp_team_dict

        current = current + 1

    print(f'Queried Range: {commits_sorted[0].committed_datetime} <-> {commits_sorted[-1].committed_datetime}')

    # reports
    # what are the most changed files by each team?
    hot_list = {}

    for team in developer_registry.teams.keys():
        # uses a map to build a list of tuples: (filename, change_count), then sorts that by change count
        hot_list[team] = sorted(list(map(lambda i: (i[0], i[1].get(team, 0)), change_count_for_file_by_team.items())),
                                key=lambda e: e[1], reverse=True)
        # drop any files that weren't changed by that team
        hot_list[team] = list(filter(lambda i: i[1] > 0, hot_list[team]))
        # limit graph to 25 or less files
        if len(hot_list[team]) > 25:
            hot_list[team] = hot_list[team][0:25]

    # write graph
    for team in developer_registry.teams.keys():
        G = nx.Graph()

        # add nodes for team
        G.add_node(team)

        # add edges with labels
        for file_name, count in hot_list[team]:
            G.add_node(file_name)
            G.add_edge(team, file_name, label=count)

        nx.drawing.nx_pydot.write_dot(G, f'{team}.dot')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Change watcher')
    parser.add_argument('path_to_repo', type=str, help='Path to git repository')
    parser.add_argument('pattern', type=str, help='String to match')
    parser.add_argument('since', type=str, help='Examine commits since this date, format: YYYY-MM-DD')
    parser.add_argument('team_csv', type=str, help='CSV file to read team data and email aliases from')
    args = parser.parse_args()
    main(args)
