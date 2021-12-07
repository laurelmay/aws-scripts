#!/usr/bin/env python3

"""
stack_destroy module provides functions to delete all CloudFormation
stacks in an account, reguardless of termination protection
"""

import datetime
import time
from typing import List, Optional

import boto3
import click
import tabulate
from botocore.exceptions import ClientError
from mypy_boto3_cloudformation.service_resource import Stack, CloudFormationServiceResource


def is_nested(stack: Stack) -> bool:
    return bool(stack.parent_id and (stack.parent_id != stack.stack_id))


def correct_state(stack: Stack, state: str) -> bool:
    return (not state) or stack.stack_status == state


def changed_time(stack: Stack) -> datetime.datetime:
    if stack.deletion_time:
        return stack.deletion_time
    if stack.last_updated_time:
        return stack.last_updated_time
    return stack.creation_time


def delete_sweep(cfn: CloudFormationServiceResource, stacks: List[Stack], role_arn: Optional[str] = None) -> List[Stack]:
    """
    Execute a delete on all stacks in the CREATE_COMPLETE status
    """

    for stack in stacks[:]:
        try:
            stack.reload()
        except ClientError as err:
            if f"{stack.name} does not exist" in str(err):
                stacks.remove(stack)
            else:
                raise

    stacks = [
        stack
        for stack in stacks
        if stack.stack_status not in ['DELETE_IN_PROGRESS', 'DELETE_COMPLETE']
    ]

    for stack in stacks:
        click.echo(f"Attempting deletion on {stack.name}")
        try:
            cfn.meta.client.update_termination_protection(
                EnableTerminationProtection=False,
                StackName=stack.stack_name
            )
        except ClientError:
            click.echo(
                f"Unable to update termination protection for {stack.stack_name}",
                err=True
            )
        delete_args = {}
        if role_arn:
            delete_args['RoleARN'] = role_arn
        stack.delete(**delete_args)

    return stacks


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
def main(profile: str, stack_state: str, max_sweeps: int, sweep_time: int, ignore: List[str], role_arn: str) -> None:
    """
    Assists in automating the deletion of all CloudFormation stacks in an account.
    This only initiates deletion for all stacks, it does not wait for them all to
    complete, so it is possible for stacks to remain in the account with deletion
    errors at the end of a successful execution of this script.
    """

    session = boto3.Session(profile_name=profile)
    cfn = session.resource('cloudformation')

    stacks = [
        stack for stack in cfn.stacks.all()
        if correct_state(stack, stack_state) and not is_nested(stack)
    ]
    stacks = [
        stack for stack in stacks
        if stack.name not in ignore
    ]
    stacks.sort(key=changed_time, reverse=True)
    headers = ['Stack Name', 'Last Changed Time', 'Stack Status']
    table = []
    for stack in stacks:
        last_changed = changed_time(stack).strftime("%Y-%m-%d %H:%M:%S")
        table.append([stack.name, last_changed, stack.stack_status])

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
