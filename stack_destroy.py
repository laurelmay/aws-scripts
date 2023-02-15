#!/usr/bin/env python3

"""
stack_destroy module provides functions to delete all CloudFormation
stacks in an account, reguardless of termination protection
"""

import datetime
import time
from typing import Generator, Optional

import boto3
import click
import tabulate
from botocore.exceptions import ClientError
from mypy_boto3_cloudformation import CloudFormationClient
from mypy_boto3_cloudformation.type_defs import StackTypeDef 


def is_nested(stack: StackTypeDef) -> bool:
    return bool(stack.get('ParentId') and (stack.get('ParentId') != stack.get('StackId')))


def correct_state(stack: StackTypeDef, state: str) -> bool:
    return (not state) or stack['StackStatus'] == state


def changed_time(stack: StackTypeDef) -> datetime.datetime:
    if deletion_time := stack.get('DeletionTime'):
        return deletion_time
    if last_updated := stack.get('LastUpdatedTime'):
        return last_updated
    return stack.get('CreationTime')


def delete_sweep(cfn: CloudFormationClient, stacks: list[StackTypeDef], role_arn: Optional[str] = None) -> list[StackTypeDef]:
    """
    Execute a delete on all stacks in the CREATE_COMPLETE status
    """

    for stack in stacks[:]:
        try:
            stack = cfn.describe_stacks(StackName=stack['StackId'])['Stacks'][0]
        except ClientError as err:
            if f"{stack['StackName']} does not exist" in str(err):
                stacks.remove(stack)
            else:
                raise

    stacks = [
        stack
        for stack in stacks
        if stack['StackStatus'] not in ['DELETE_IN_PROGRESS', 'DELETE_COMPLETE']
    ]

    for stack in stacks:
        click.echo(f"Attempting deletion on {stack['StackName']}")
        try:
            cfn.update_termination_protection(
                EnableTerminationProtection=False,
                StackName=stack['StackId']
            )
        except ClientError:
            click.echo(
                f"Unable to update termination protection for {stack['StackName']}",
                err=True
            )
        delete_args = {"StackName": stack['StackName']}
        if role_arn:
            delete_args['RoleARN'] = role_arn
        cfn.delete_stack(**delete_args)

    return stacks


def get_all_stacks(cfn: CloudFormationClient) -> Generator[StackTypeDef, None, None]:
    paginator = cfn.get_paginator('describe_stacks')
    for page in paginator.paginate():
        yield from page['Stacks']


@click.command('stack-destroy')
@click.option(
    '--profile',
    '-p',
    required=True,
    default='default',
    help='The AWS CLI profile to use',
)
@click.option(
    '--stack-state',
    '-s',
    required=False,
    help="The stack state to filter on",
)
@click.option(
    '--max-sweeps',
    type=click.INT,
    required=False,
    help="The maximum number of delete sweeps to attempt",
)
@click.option(
    '--sweep-time',
    type=click.INT,
    default=30,
    help="The amount of time to wait between sweeps"
)
@click.option(
    '--ignore',
    '-i',
    multiple=True,
    help="Stacks to ignore"
)
@click.option(
    '--role-arn',
    '-r',
    default=None,
    help="The ARN of the role to use to delete the stacks"
)
def main(profile: str, stack_state: str, max_sweeps: int, sweep_time: int, ignore: list[str], role_arn: str) -> None:
    """
    Assists in automating the deletion of all CloudFormation stacks in an account.
    This only initiates deletion for all stacks, it does not wait for them all to
    complete, so it is possible for stacks to remain in the account with deletion
    errors at the end of a successful execution of this script.
    """

    session = boto3.Session(profile_name=profile)
    cfn = session.client('cloudformation')

    stacks = [
        stack for stack in get_all_stacks(cfn)
        if correct_state(stack, stack_state) and not is_nested(stack)
    ]
    stacks = [
        stack for stack in stacks
        if stack['StackName'] not in ignore
    ]
    stacks.sort(key=changed_time, reverse=True)
    headers = ['Stack Name', 'Last Changed Time', 'Stack Status']
    table = []
    for stack in stacks:
        last_changed = changed_time(stack).strftime("%Y-%m-%d %H:%M:%S")
        table.append([stack['StackName'], last_changed, stack['StackStatus']])

    if not stacks:
        click.echo("There are not any stacks to delete.")
        return

    click.clear()
    click.echo(tabulate.tabulate(table, headers=headers, tablefmt="psql"))
    if not click.confirm("Delete all above stacks"):
        click.echo("Aborted.")
        return

    sweep = 1
    while True:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"Starting sweep {sweep} at {current_time}")
        if not delete_sweep(cfn, stacks, role_arn):
            click.echo("All stacks have had deletion initiated.")
            break
        click.echo(f"Sleeping for {sweep_time} seconds")
        time.sleep(sweep_time)
        sweep += 1
        if max_sweeps and sweep > max_sweeps:
            click.echo("Max number of sweeps reached.")
            break


if __name__ == "__main__":
    main()
