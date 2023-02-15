#!/usr/bin/env python3

"""
Find available IP addresses in an AWS Subnet
"""

import ipaddress
from typing import Generator

import boto3
import click

from mypy_boto3_ec2 import EC2Client
from mypy_boto3_ec2.type_defs import NetworkInterfaceTypeDef


def get_network_interfaces(ec2: EC2Client, subnet_id: str) -> Generator[NetworkInterfaceTypeDef, None, None]:
    paginator = ec2.get_paginator('describe_network_interfaces')
    for page in paginator.paginate(Filters=[{'Name': 'subnet-id', 'Values': [subnet_id]}]):
        yield from page['NetworkInterfaces']


@click.command('find-ip-addrs')
@click.option(
    '--subnet-id',
    '-s',
    required=False,
    help="The ID of the desired subnet (may not be specified with --subnet-name)",
    metavar="ID",
)
@click.option(
    '--subnet-name',
    '-n',
    required=False,
    help="The Name tag of the subnet (may not be specified with --subnet-id)",
    metavar="NAME TAG"
)
@click.option(
    '--profile',
    '-p',
    envvar='AWS_PROFILE',
    required=True,
    default='default',
    help='Profile name',
)
@click.pass_context
def main(ctx: click.Context, subnet_id: str, subnet_name: str, profile: str) -> None:
    """
    Lists availble IP addresses in all subnets (or optionally just one subnet) in an account.
    """

    if subnet_id and subnet_name:
        click.echo("Only one of --subnet-id and --subnet-name may be specified", err=True)
        click.echo(ctx.get_help(), color=ctx.color)
        return

    session = boto3.Session(profile_name=profile)
    ec2 = session.client('ec2')
    query = {}
    if subnet_id:
        query["SubnetIds"] = [subnet_id]
    elif subnet_name:
        query["Filters"] = [{'Name': 'tag:Name', 'Values': [subnet_name]}]
    subnets = ec2.describe_subnets(**query)['Subnets']

    for subnet in subnets:
        # AWS reserves the network address, three more addresses, and the broadcast address.
        # Documented at:
        #  https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Subnets.html#VPC_Sizing
        # Python's ipaddress.IPNetwork does not support slicing, so it needs to be converted to
        # a list
        id = subnet.get('SubnetId')
        cidr = subnet.get('CidrBlock')
        if not id:
            raise Exception('Unexpectedly failed to retrieve subnet ID from EC2 API')
        if not cidr:
            raise Exception('Only IPv4 is currently supported')
        available_ips = {str(ip) for ip in list(ipaddress.IPv4Network(cidr))[4:-1]}

        name_tags = [tag for tag in subnet.get('Tags', []) if tag.get('Key') == 'Name']
        if name_tags:
            name = name_tags[0].get('Value')
        else:
            name = None

        interfaces = get_network_interfaces(ec2, id)
        for interface in interfaces:
            int_ips = {addr.get('PrivateIpAddress') for addr in interface.get('PrivateIpAddresses', [])}
            available_ips -= int_ips

        identifier = f"{name} ({id})" if name else id

        click.echo(f"{len(available_ips)} available IP Addresses in {identifier}:")
        for ip in sorted(available_ips, key=ipaddress.IPv4Address):
            click.echo(f"  {ip}")


if __name__ == '__main__':
    main()
