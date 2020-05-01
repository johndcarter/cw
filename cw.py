import argparse
import json

from developer_registry import DeveloperRegistry
from git import Repo
from jira import JIRA, JIRAError
from os import path
import networkx as nx


def main(args):
    print(f'Repo: {args.path_to_repo}')
    print(f'Matching changes to: {args.pattern}')

    with open('private.json', 'r') as credentials:
        creds = json.load(credentials)

    jira = JIRA({"server": creds['jira_server']}, basic_auth=(creds['jira_user'], creds['jira_apikey']))

    repo = Repo(args.path_to_repo)
    developer_registry = DeveloperRegistry()
    print(f'Loading team data from: {args.team_csv}')
    developer_registry.load_from_csv(args.team_csv)
    for k, v in developer_registry.teams.items():
        print(f'\t{k} : {len(v)} members')
    print(f'Loaded {len(developer_registry.teams)} teams')

    commits_sorted = sorted(repo.iter_commits(rev='develop', since=args.since), key=(lambda c: c.committed_datetime))

    files_with_commits = {}
    change_count_for_file_by_author = {}
    change_count_for_file_by_team = {}
    commits_matched_by_team = {}
    current = 1

    # 'indexing' happens here
    for commit in commits_sorted:
        print(f'Processing {current} of {len(commits_sorted)}')

        matched_commit_team = None

        for file_name in commit.stats.files.keys():

            if args.pattern in file_name:
                author_temp = str(commit.author.email.lower())

                if file_name not in files_with_commits:
                    files_with_commits[file_name] = []

                files_with_commits[file_name].append(commit)

                # get the dictionary of changes for the file, or init a new one
                temp_dict = change_count_for_file_by_author.get(str(file_name), {})

                # for the author of the commit, add or increment the change count in the temporary
                temp_dict[author_temp] = temp_dict.get(author_temp, 0) + 1

                # store the update
                change_count_for_file_by_author[str(file_name)] = temp_dict

                dev_tuple = developer_registry.find_developer_by_email(author_temp)

                # we found the team for that developer
                if dev_tuple:
                    matched_commit_team = dev_tuple[1]

                    # get the dictionary of changes for that file, or init a new one
                    temp_team_dict = change_count_for_file_by_team.get(file_name, {})

                    # increment it
                    temp_team_dict[dev_tuple[1]] = temp_team_dict.get(dev_tuple[1], 0) + 1

                    # store the update
                    change_count_for_file_by_team[file_name] = temp_team_dict

        if matched_commit_team:
            temp_list = commits_matched_by_team.get(matched_commit_team, [])
            temp_list.append(commit)
            commits_matched_by_team[matched_commit_team] = temp_list

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

        write_all_changes_for_team(team, hot_list[team], len(commits_sorted),
                                   len(commits_matched_by_team.get(team, [])),
                                   args.output)

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

        dot_output_file = None
        if not args.output:
            dot_output_file = f'{team}.dot'
        else:
            dot_output_file = path.join(args.output, f'{team}.dot')

        nx.drawing.nx_pydot.write_dot(G, dot_output_file)

    print('Done')
    files_jira_types = correlate_commits_with_jira(files_with_commits, jira)
    print('Done correlation')

    hot_files = list(map((lambda t: (t[0], len(t[1]))), files_with_commits.items()))
    hot_files.sort(key=(lambda t: t[1]), reverse=True)
    hot_files = hot_files[0:25]

    text_file = open('top25_activity_2020.txt', 'w')
    for file_name, commit_count in hot_files:
        text_file.write(f'\nFile: {file_name} has {commit_count} commits.')

        for ticket_type, ticket_list in files_jira_types[file_name].items():

            if ticket_type == 'count':
                continue;

            text_file.write(f'\n\tTicket Type: {ticket_type}')
            text_file.write(f'\n\t\tTickets: ')

            for ticket_number in ticket_list:
                text_file.write(f'\n\t\t\t{creds["browse_url_prefix"] + ticket_number} ')

    text_file.close()

    print(hot_files)


def correlate_commits_with_jira(files_with_commits: dict, jira) -> dict:
    files_with_commits_detailed = {}
    file_count = 0

    for file_name, commit_list in files_with_commits.items():
        print(f'Correlating file {file_count} of {len(files_with_commits)}')

        if file_name not in files_with_commits_detailed:
            files_with_commits_detailed[file_name] = {'count': 0}

        commit_count = 0

        for commit in commit_list:

            print(f'\tQuerying: {commit_count} of {len(commit_list)}')

            ticket_number = get_jira_ticket_number_from_summary(commit.summary)
            files_with_commits_detailed[file_name]['count'] += 1

            if ticket_number:
                issue = None
                try:  # this is a ham-handed way to handle any malformed ticket #s
                    issue = jira.issue(ticket_number)
                except JIRAError as e:
                    print(f'Failed on find issue for: {ticket_number}')
                    continue

                ticket_type = issue.fields.issuetype.name

                if ticket_type not in files_with_commits_detailed[file_name]:
                    files_with_commits_detailed[file_name][ticket_type] = []

                files_with_commits_detailed[file_name][ticket_type].append(ticket_number)

            commit_count += 1

        file_count += 1

    return files_with_commits_detailed


def get_jira_ticket_number_from_summary(summary: str) -> str:
    splits = summary.split(sep=' ')
    # skip merge commits, and roughly enforce 'XX-NNNN' as the first part of summaries
    if splits[0] == 'Merge' or '-' not in splits[0]:
        return None
    return splits[0]


def write_all_changes_for_team(team: str, hot_list: list, commit_count: int, commits_matched: int,
                               outfile_name: str = None) -> None:
    output_file = None
    if not outfile_name:
        output_file = f'commits_by_file_for_{team}.txt'
    else:
        output_file = path.join(args.output, f'commits_by_file_for_{team}.txt')

    text_file = open(output_file, 'w')
    text_file.write(
        f'{team} team made {len(hot_list)} changes (over {commits_matched} commits) in {commit_count} commits scanned.')

    for t in hot_list:
        text_file.write(f'\n{t[0]}, {t[1]} changes.')

    text_file.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Change watcher')
    parser.add_argument('path_to_repo', type=str, help='Path to git repository')
    parser.add_argument('pattern', type=str, help='String to match')
    parser.add_argument('since', type=str, help='Examine commits since this date, format: YYYY-MM-DD')
    parser.add_argument('team_csv', type=str, help='CSV file to read team data and email aliases from')
    parser.add_argument('--output', type=str, help='Directory to write output to')
    args = parser.parse_args()
    main(args)
