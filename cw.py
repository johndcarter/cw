import argparse
import json

from developer_registry import DeveloperRegistry
from execute_and_capture import *
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

        current += 1

    print(f'Queried Range: {commits_sorted[0].committed_datetime} <-> {commits_sorted[-1].committed_datetime}')

    # reports
    # what are the most changed files by each team?
    hot_list = generate_hotlists_for_teams(change_count_for_file_by_team, developer_registry)

    # write out hot list for each team
    for team in hot_list.keys():
        write_all_changes_for_team(team, hot_list[team], path.join(args.output, f'commits_by_file_for_{team}.txt'))

    # build and write graph of team interactions
    for team in hot_list.keys():
        nx.drawing.nx_pydot.write_dot(build_graph(team, hot_list[team]), path.join(args.output, f'{team}.dot'))

    print('Done')
    write_jira_activity(correlate_commits_with_jira(files_with_commits, jira), files_with_commits,
                        creds["browse_url_prefix"], path.join(args.output, 'top25_jira_activity.txt'))
    print('Done correlation')

    write_files_with_most_commits(creds, files_with_commits, path.join(args.output, 'top25_modifications.txt'))

    # write change counts by author:
    with open(path.join(args.output, 'who.txt'), 'w') as text_file:
        text_file.write('Changes to public header files:')
        for author, count in sorted(
                get_change_counts_by_author(change_count_for_file_by_author, developer_registry).items(),
                key=(lambda t: t[1]), reverse=True):
            text_file.write(f'\n{author} -> {count} changes')


def write_files_with_most_commits(creds, files_with_commits, output_filename):
    with open(output_filename, 'w') as text_file:
        # this turns the map into a list of tuples filename -> [commit shas], sorted by the number of commits, top 25
        for file_name, commit_list in sorted(files_with_commits.items(), key=(lambda t: len(t[1])), reverse=True)[0:25]:
            text_file.write(f'\nFile: {file_name} had {len(commit_list)} commits:')
            for commit in commit_list:
                # omit merge commits:
                if commit.summary.startswith('Merge'):
                    continue;
                text_file.write(f'\n\t{commit.summary}')
                text_file.write(f'\n\t{creds["browse_url_prefix"] + commit.hexsha}:')
                inserts, deletes = get_insert_deletes_from_git_sha(args.path_to_repo, commit.hexsha)[file_name]
                text_file.write(f'\n\t\tInsertions: {inserts} Deletions: {deletes}')


def get_change_counts_by_author(change_count_for_file_by_author, developer_registry):
    author_with_total_counts = {}
    for _, dict_of_author_counts in change_count_for_file_by_author.items():
        for author, commit_count in dict_of_author_counts.items():
            found_tuple = developer_registry.find_developer_by_email(author)
            if found_tuple:
                developer_id, _ = found_tuple
                if developer_id.name not in author_with_total_counts:
                    author_with_total_counts[developer_id.name] = commit_count
                else:
                    author_with_total_counts[developer_id.name] += commit_count
    return author_with_total_counts


def build_graph(team_name, hot_list_for_team) -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(team_name)

    # add edges with labels
    for file_name, count in hot_list_for_team:
        graph.add_node(file_name)
        graph.add_edge(team_name, file_name, label=count)

    return graph


def generate_hotlists_for_teams(change_count_for_file_by_team, developer_registry) -> dict:
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

    return hot_list


def write_jira_activity(files_jira_types, files_with_commits, jira_issue_url_prefix, output_filename):
    hot_files = list(map((lambda t: (t[0], len(t[1]))), files_with_commits.items()))
    hot_files.sort(key=(lambda t: t[1]), reverse=True)
    hot_files = hot_files[0:25]
    text_file = open(output_filename, 'w')
    for file_name, commit_count in hot_files:
        text_file.write(f'\nFile: {file_name} has {commit_count} commits.')

        for ticket_type, ticket_list in files_jira_types[file_name].items():
            if ticket_type == 'count':
                continue;

            text_file.write(f'\n\tTicket Type: {ticket_type}')
            text_file.write(f'\n\t\tTickets: ')

            for ticket_number in ticket_list:
                text_file.write(f'\n\t\t\t{jira_issue_url_prefix + ticket_number} ')
    text_file.close()


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


def write_all_changes_for_team(team: str, hot_list: list, outfile_name: str = None) -> None:
    with open(outfile_name, 'w') as text_file:
        text_file.write(f'{team} team changed {len(hot_list)} files: ')

        for t in hot_list:
            text_file.write(f'\n{t[0]}, {t[1]} changes.')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Change watcher')
    parser.add_argument('path_to_repo', type=str, help='Path to git repository')
    parser.add_argument('pattern', type=str, help='String to match')
    parser.add_argument('since', type=str, help='Examine commits since this date, format: YYYY-MM-DD')
    parser.add_argument('team_csv', type=str, help='CSV file to read team data and email aliases from')
    parser.add_argument('--output', type=str, help='Directory to write output to')
    args = parser.parse_args()
    main(args)
