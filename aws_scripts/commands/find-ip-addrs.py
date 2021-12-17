#!/usr/bin/env python3

"""
Find available IP addresses in an AWS Subnet
"""

import ipaddress

import click

from aws_scripts.options import profile_option
from aws_scripts.session import create_session


@click.command("subnet-ips")
@click.option(
    "--subnet-id",
    "-s",
    required=False,
    help="The ID of the desired subnet (may not be specified with --subnet-name)",
    metavar="ID",
)
@click.option(
    "--subnet-name",
    "-n",
    required=False,
    help="The Name tag of the subnet (may not be specified with --subnet-id)",
    metavar="NAME TAG",
)
@profile_option
@click.pass_context
def main(ctx: click.Context, subnet_id: str, subnet_name: str, profile: str) -> None:
    """
    Lists availble IP addresses in all subnets (or optionally just one subnet) in an account.
    """

    if subnet_id and subnet_name:
        click.echo(
            "Only one of --subnet-id and --subnet-name may be specified", err=True
        )
        click.echo(ctx.get_help(), color=ctx.color)
        return

    session = create_session(profile_name=profile)
    ec2 = session.resource("ec2")
    if subnet_id:
        subnets = [ec2.Subnet(subnet_id)]
    elif subnet_name:
        subnets = ec2.subnets.filter(
            Filters=[{"Name": "tag:Name", "Values": [subnet_name]}]
        )
    else:
        subnets = ec2.subnets.all()

    for subnet in subnets:
        # AWS reserves the network address, three more addresses, and the broadcast address.
        # Documented at:
        #  https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Subnets.html#VPC_Sizing
        # Python's ipaddress.IPNetwork does not support slicing, so it needs to be converted to
        # a list
        available_ips = {
            str(ip) for ip in list(ipaddress.IPv4Network(subnet.cidr_block))[4:-1]
        }

        name_tags = [tag for tag in subnet.tags if tag["Key"] == "Name"]
        if name_tags:
            name = name_tags[0]["Value"]
        else:
            name = None

        for interface in subnet.network_interfaces.all():
            int_ips = {
                addr["PrivateIpAddress"] for addr in interface.private_ip_addresses
            }
            available_ips -= int_ips

        identifier = f"{name} ({subnet.id})" if name else subnet.id

        click.echo(f"{len(available_ips)} available IP Addresses in {identifier}:")
        for ip in sorted(available_ips, key=ipaddress.IPv4Address):
            click.echo(f"  {ip}")


if __name__ == "__main__":
    main()
