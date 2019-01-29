# -----------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# -----------------------------------------------------------------------------

import json
import os

from knack.util import CLIError

from azdev.utilities import find_file


SERVICE_COLOR = 'e99695'
CLI_COLOR = 'd4c5f9'


def _get_cli_repo():
    from github import Github

    gh_token = os.environ.get('GH_TOKEN')
    if not gh_token:
        raise CLIError('Could not find GH_TOKEN environment variable.')
    return Github(gh_token).get_repo('Azure/azure-cli')


def dump_labels():
    repo = _get_cli_repo()
    label_dict = {}
    for label in repo.get_labels():
        name = label.name
        label_dict[name] = {
            'count': 0,
            'color': label.color,
            'description': label.description,
            'category': 'OTHER',
            'owners': {}
        }
        if label.color == SERVICE_COLOR:
            label_dict[name]['category'] = 'SERVICE'
        elif label.color == CLI_COLOR:
            label_dict[name]['category'] = 'CLI'
    return label_dict


def dump_issues():
    repo = _get_cli_repo()
    issue_dict = {}
    for issue in repo.get_issues(state='open'):
        key = issue.number

        # PRs in Github are also issue. Skip these.
        if issue.pull_request:
            continue

        issue_dict[key] = {
            'user': issue.user.login,
            'url': issue.url,
            'updated_at': issue.updated_at,
            'title': issue.title,
            'state': issue.state,
            'milestone': issue.milestone.title if issue.milestone else None,
            'labels': [x.name for x in issue.labels],
            'created_at': issue.created_at,
            'comments': issue.comments,
            'closed_at': issue.closed_at,
            'closed_by': issue.closed_by.login if issue.closed_by else None,
            'assignees': [x.login for x in issue.assignees]
        }
    return issue_dict


def analyze_issues(issues_path=None, labels_path=None):
    issues = None
    labels = None
    if not issues_path:
        issues_path = os.path.join(find_file('issues.json'), 'issues.json')
    if not labels_path:
        labels_path = os.path.join(find_file('labels.json'), 'labels.json')

    if not issues_path:
        raise CLIError('Need issues.json')
    if not labels_path:
        raise CLIError('Need labels.json')

    with open(os.path.expanduser(issues_path), 'r') as issues_file:
        issues = json.loads(issues_file.read())
    with open(os.path.expanduser(labels_path), 'r') as labels_file:
        labels = json.loads(labels_file.read())

    for _, issue in issues.items():
        for label in issue['labels']:
            labels[label]['count'] = labels[label]['count'] + 1
            for assignee in issue['assignees']:
                if assignee not in labels[label]['owners']:
                    labels[label]['owners'][assignee] = 0
                labels[label]['owners'][assignee] = labels[label]['owners'][assignee] + 1

    return {k: v for k, v in labels.items() if labels[k]['count']}

def assign_issues(label, user, issues_path=None):
    issues = None

    if not issues_path:
        issues_path = os.path.join(find_file('issues.json'), 'issues.json')

    if not issues_path:
        raise CLIError('Need issues.json')

    with open(os.path.expanduser(issues_path), 'r') as issues_file:
        issues = json.loads(issues_file.read())

    for issue_id, issue in issues.items():
        if label in issue['labels'] and user not in issue['assignees']:
            # skip "help wanted" issues
            if 'help wanted' in issue['labels']:
                continue
            print('Assign issue {} to {} based on label {}'.format(issue_id, user, label))

