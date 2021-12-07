#!/usr/bin/env python3

"""
Assists in de-registering managed instances from SSM that have gone into
ConnectionLost ping status.
"""

from datetime import datetime

import boto3
import click
import tabulate

from mypy_boto3_ssm.type_defs import DescribeInstanceInformationResultTypeDef, InstanceInformationTypeDef

_CONNECTION_LOST_FILTERS = [
    {
        'key': 'PingStatus',
        'valueSet': ['ConnectionLost']
    },
    {
        'key': 'ResourceType',
        'valueSet': ['ManagedInstance']
    }
]


@click.command('deregister-lost-instances')
@click.option(
    '--profile',
    '-p',
    required=True,
    default='default',
    help='Profile name',
)
@click.option(
    '--page-size',
    '-s',
    required=True,
    type=click.INT,
    default=50,
    help="The number of instances to prompt for at a time",
)
def main(profile: str, page_size: int) -> None:
    """
    Deregister instances that have gone into ConnectionLost for their ping status
    from Systems Manager.
    """
    
    session = boto3.Session(profile_name=profile)
    ssm = session.client('ssm')

    lost_instances = []
    headers = ['Instance ID', 'Name', 'IP Address', 'Status', 'Last Ping']
    full_table = []

    paginator = ssm.get_paginator('describe_instance_information')
    for page in paginator.paginate(
        InstanceInformationFilterList=_CONNECTION_LOST_FILTERS,
        PaginationConfig={
            'PageSize': page_size
        }
    ):
        table = []
        page_instances= page.get('InstanceInformationList', [])

        for instance in page_instances:
            instance_id = instance['InstanceId']
            name = instance.get('Name', instance.get('ComputerName', 'Unknown'))
            ip_addr = instance.get('IPAddress', 'Unknown')
            ping_date = instance.get('LastPingDateTime', None)
            if ping_date:
                ping = datetime.strftime(instance['LastPingDateTime'], "%Y-%m-%d %H:%M:%S")
            else:
                ping = "Never"
            table.append([instance_id, name, ip_addr, 'Connection Lost', ping])

        if table:
            click.clear()
            click.echo(tabulate.tabulate(table, headers=headers, tablefmt="psql"))
            delete = click.confirm("Deregister all the above instances")
            if delete:
                lost_instances.extend(page_instances)
                full_table.extend(table)
        else:
            continue

    if not lost_instances:
        click.echo("There are not any instances to deregister.")
        return
    
    click.clear()
    click.echo(tabulate.tabulate(full_table, headers=headers, tablefmt="psql"))
    final_confirm = click.confirm("Are you sure you want to deregister all the above instances?")

    if not final_confirm:
        click.echo("Aborted.")
        return

    def get_instance_name(instance: InstanceInformationTypeDef) -> str:
        if not instance:
            return ""
        if 'Name' in instance:
            return instance['Name']
        return instance['InstanceId']

    with click.progressbar(lost_instances, item_show_func=get_instance_name) as instance_bar:
        for instance in instance_bar:
            ssm.deregister_managed_instance(InstanceId=instance['InstanceId'])

    


if __name__ == '__main__':
    main()