#!/usr/bin/env python3

"""
Assists in automating the deletion of log streams from a CloudWatch Logs log group.
Prints the log streams from a given log group in batches of a given size. At the
end, confirmation is request before performing the deletion.
"""

from datetime import datetime
from typing import Any, Dict

import click
import tabulate

from aws_scripts.options import profile_option
from aws_scripts.session import create_session


@click.command("clean-streams")
@profile_option
@click.option("--prefix", required=False, help="Log group name")
@click.option(
    "--page-size",
    "-s",
    required=True,
    type=click.INT,
    default=50,
    help="The number of streams to prompt for at a time",
)
def main(profile: str, prefix: str, page_size: int) -> None:
    """
    Automate the deletion of log groups.

    A prefix can be given to assist in the deletion of a subset of all log groups.
    """

    session = create_session(profile_name=profile)
    client = session.client("logs")

    to_delete = []
    paginator = client.get_paginator("describe_log_groups")
    paginator_args: Dict[str, Any] = {"PaginationConfig": {"PageSize": page_size}}
    if prefix:
        paginator_args["logGroupNamePrefix"] = prefix
    for page in paginator.paginate(**paginator_args):
        groups = page["logGroups"]
        table = []
        for idx, group in enumerate(groups):
            group_name = group["logGroupName"]
            try:
                last_event = datetime.fromtimestamp(group["creationTime"] / 1000.0)
            except KeyError as e:
                if e.args[0] == "creationTime":
                    last_event = ""
                else:
                    raise
            table.append([idx, group_name, last_event])
        click.clear()
        print(
            tabulate.tabulate(table, headers=["Index", "Group Name", "Creation Time"])
        )
        delete = click.confirm("Delete all of the above")
        if delete:
            to_delete += [line[1] for line in table]
        else:
            continue

    click.clear()
    if not to_delete:
        return
    click.echo("The following are to be deleted.")
    for group in to_delete:
        click.echo(f"  {group}")
    delete = click.confirm(f"Delete all {len(to_delete)} of the above groups")
    if delete:
        with click.progressbar(to_delete, item_show_func=lambda x: x) as groups:
            for group in groups:
                client.delete_log_group(logGroupName=group)


if __name__ == "__main__":
    main()
