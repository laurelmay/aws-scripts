#!/usr/bin/env python3

import ipaddress
import socket
from typing import Any

import click
import requests
import tabulate

_AWS_IP_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"


def format_ip(input: str, resolved: list[str]):
    if [input] == resolved:
        return input
    return f"{input} ({','.join(resolved)})"


class IpLookup:
    address: str
    network: ipaddress.IPv4Network | ipaddress.IPv6Network
    _matching_prefixes: list[dict[str, Any]]

    def __init__(self, address: str):
        self.address = address
        self.network = ipaddress.ip_network(address, strict=False)
        self._matching_prefixes = []

    def _add_match(self, prefix: dict[str, Any]) -> None:
        self._matching_prefixes.append(prefix)

    def add_if_match(self, prefix: dict[str, Any]) -> None:
        # The address type (v4 or v6) does not match the given prefix
        if self.prefix_key not in prefix:
            return

        if self.network.subnet_of(ipaddress.ip_network(prefix[self.prefix_key])):
            self._add_match(prefix)

    @property
    def prefix_key(self) -> bool:
        if self.is_v6:
            return "ipv6_prefix"
        return "ip_prefix"

    @property
    def is_v4(self) -> bool:
        return type(self.network) == ipaddress.IPv4Network

    @property
    def is_v6(self) -> bool:
        return type(self.network) == ipaddress.IPv6Network

    def create_table_row(self) -> list[str]:
        if not self._matching_prefixes:
            return []
        return [
            self.address,
            ", ".join({prefix[self.prefix_key] for prefix in self._matching_prefixes}),
            ", ".join({prefix["region"] for prefix in self._matching_prefixes}),
            ", ".join({prefix["service"] for prefix in self._matching_prefixes}),
            ", ".join(
                {prefix["network_border_group"] for prefix in self._matching_prefixes}
            ),
        ]


@click.command("aws-ip-info")
@click.argument("hostname", metavar="IP-OR-HOSTNAME")
def main(hostname: str) -> None:
    """
    Prints the information about the AWS IP block that an IP address belongs to.

    If an IP address is provided it is looked up directly; if a name is provided,
    a DNS lookup will be performed and all the IPs that the name resolves to will
    be looked up and reported on.

    Example:
    
        aws-ip-info status.aws.amazon.com
    """

    try:
        ip_data = requests.get(_AWS_IP_URL).json()
    except IOError:
        click.echo("Unable to fetch/parse the IP data from AWS.", err=True)
        return

    try:
        resolved_sockets = socket.getaddrinfo(hostname, 443)
    except (ValueError, socket.gaierror):
        click.echo(f"{hostname!r} is not a valid hostname", err=True)
        return

    unique_ips = {socket_info[-1][0] for socket_info in resolved_sockets}
    resolved_ips = [IpLookup(addr) for addr in unique_ips]
    all_aws_prefixes = ip_data["prefixes"] + ip_data["ipv6_prefixes"]

    click.echo(f"Finding matches for {format_ip(hostname, unique_ips)}")
    with click.progressbar(all_aws_prefixes) as prefix_bar:
        for prefix in prefix_bar:
            for ip_lookup in resolved_ips:
                ip_lookup.add_if_match(prefix)

    headers = [
        "Address",
        "Prefix",
        "Region(s)",
        "Services(s)",
        "Network Border Group(s)",
    ]
    results = sorted(
        [row for match in resolved_ips if (row := match.create_table_row())],
        key=lambda row: row[0],
    )
    if not results:
        click.echo(f"{format_ip(hostname, unique_ips)} is not an AWS address", err=True)
        return

    click.echo(tabulate.tabulate(results, headers=headers, tablefmt="psql"))


if __name__ == "__main__":
    main()
