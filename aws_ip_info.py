#!/usr/bin/env python3

import ipaddress
import json
import sys

import click
import requests

_AWS_IP_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
_KEY_MAP = {
    ipaddress.IPv4Network: {
        'list': 'prefixes',
        'net': 'ip_prefix'
    },
    ipaddress.IPv6Network: {
        'list': 'ipv6_prefixes',
        'net': 'ipv6_prefix'
    }
}

@click.command('aws-ip-info')
@click.argument('ip-address')
def main(ip_address: str) -> None:
    """
    Prints the information about the IP block that the given IP is a part of.
    """

    try:
        network = ipaddress.ip_network(ip_address, strict=False)
    except ValueError:
        click.echo(f"{ip_address!r} is not a valid IP address", err=True)
        return

    try:
        ip_data = requests.get(_AWS_IP_URL).json()
    except IOError:
        click.echo("Unable to fetch/parse the IP data from AWS.", err=True)
        return

    try:
        prefix_list = ip_data[_KEY_MAP[type(network)]['list']]
    except KeyError:
        click.echo(f"{ip_address!r} is not a supported address type.", err=True)
        return
    
    matches = []
    with click.progressbar(prefix_list) as prefix_bar:
        for prefix in prefix_bar:
            prefix_net = ipaddress.ip_network(prefix[_KEY_MAP[type(network)]['net']])
            if network.subnet_of(prefix_net):
                matches.append(prefix)

    if not matches:
        click.echo(f"{ip_address} is not an AWS IP address.", err=True)
        return

    click.echo(json.dumps(matches, indent=4))


if __name__ == '__main__':
    main()