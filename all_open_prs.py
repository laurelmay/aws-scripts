#!/usr/bin/env python3

"""
Displays all of the open PRs against all CodeCommit repositories in an account
"""

import sys
from typing import Any, Dict, Tuple

import boto3
import click
import tabulate
from botocore.exceptions import ClientError
from mypy_boto3_codecommit.client import CodeCommitClient


def get_account_alias(session: boto3.Session) -> str:
    """
    Returns the account alias if one is available, otherwise the ID.
    """

    iam = session.client('iam')
    sts = session.client('sts')
    try:
        return iam.list_account_aliases()['AccountAliases'][0]
    except (ClientError, IndexError):
        return sts.get_caller_identity()['Account']


def get_console_domain(region: str) -> str:
    """
    Get the domain for the AWS management console based on the region
    """

    if region.startswith('us-gov'):
        return "console.amazonaws-us-gov.com"
    if region.startswith('cn'):
        return "console.amazonaws.cn"
    if region.startswith('us-iso'):
        raise ValueError("AWS ISO regions are not supported")
    return "console.aws.amazon.com"


def build_pr_url(region: str, repo: str, pr_id: str) -> str:
    """
    Builds a CodeCommit PR URL
    """

    domain = get_console_domain(region)
    return f"https://{domain}/codesuite/codecommit/repositories/{repo}/pull-requests/{pr_id}/"


def validate_approvals(cc: CodeCommitClient, pr: Dict[str, Any]) -> Tuple[bool, str]:
    revision = pr['revisionId']
    pr_id = pr['pullRequestId']
    evaluation = cc.evaluate_pull_request_approval_rules(
        pullRequestId=pr_id, revisionId=revision
    )['evaluation']
    if evaluation['approved']:
        return True, click.style("Approved", fg="green")
    if evaluation['overridden']:
        return True, click.style("Overriden", fg="yellow")
    return True, click.style("Not approved", fg="red")


@click.command('all-open-prs')
@click.option(
    '--profile',
    '-p',
    required=True,
    default='default',
    help='Profile name',
)
@click.option(
    '--repo',
    '-r',
    required=False,
    default=None,
    help='The repo to list PRs for (lists all PRs if not given)',
)
@click.option(
    '--sort-by',
    '-s',
    type=click.Choice(['repo', 'id', 'author', 'title', 'approval']),
    multiple=True,
    default=['id'],
    help=""
)
def main(profile: str, repo: str, sort_by: str):
    """
    List all open PRs in an AWS account.
    """

    session = boto3.Session(profile_name=profile)
    cc = session.client('codecommit')
    repos = []
    if repo:
        repos.append(repo)
    else:
        repo_paginator = cc.get_paginator('list_repositories')
        for page in repo_paginator.paginate():
            repos.extend(repo['repositoryName'] for repo in page['repositories'])

    prs = []
    approved_prs = []
    def repo_name(repo):
        if not repo:
            return repo
        return repo

    with click.progressbar(repos, label="Checking repos...", item_show_func=repo_name) as repo_bar:
        for repo in repo_bar:
            pr_paginator = cc.get_paginator('list_pull_requests')
            for page in pr_paginator.paginate(repositoryName=repo, pullRequestStatus='OPEN'):
                prs.extend(page['pullRequestIds'])

    table = []
    headers = ['Repository', 'PR #', 'Title', 'Author', 'URL', 'Approvals']
    with click.progressbar(prs, label="Loading PRs...   ") as bar:
        for pr in bar:
            data = cc.get_pull_request(pullRequestId=pr)['pullRequest']
            title = data['title']
            if len(data['title']) > 52:
                title = f"{title[:49]}..."
            try:
                author = data['authorArn'].split(':')[-1].split('/')[-1]
            # If the IAM user who authored the commit no longer exists, the
            # authorArn field may not exist or any number of issues may occur.
            except (KeyError, ValueError, IndexError):
                author = ""
            repo = data['pullRequestTargets'][0]['repositoryName']
            url = build_pr_url(session.region_name, repo, pr)
            approved, approval_text = validate_approvals(cc, data)
            if approved:
                approved_prs.append(pr)
            row = [repo, pr, title, author, url, approval_text]
            table.append(row)

    if not table:
        print(f"There are not any PRs open in {get_account_alias(session)}.")
        return

    def sort_keys(pr):
        keys = []
        for sort in sort_by:
            if sort == "id":
                keys.append(int(pr[1]))
            elif sort == 'repo':
                keys.append(pr[0])
            elif sort == 'title':
                keys.append(pr[2])
            elif sort == 'author':
                keys.append(pr[3])
            elif sort == 'approval':
                keys.append(pr[4])
        return keys or int(pr[1])
    table.sort(key=sort_keys)

    print(tabulate.tabulate(table, headers, tablefmt="psql"))



if __name__ == '__main__':
    main()
