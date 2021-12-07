#!/usr/bin/env python3

"""
Assists in automating the deletion of log streams from a CloudWatch Logs log group.
Prints the log streams from a given log group in batches of a given size. At the
end, confirmation is request before performing the deletion.
"""

from datetime import datetime

import boto3
import click
import tabulate


@click.command('clean-streams')
@click.option(
    '--profile',
    '-p',
    required=True,
    default='default',
    help='Profile name',
)
@click.option(
    '--log-group',
    '-g',
    required=True,
    help="Log group name"
)
@click.option(
    '--page-size',
    '-s',
    type=click.INT,
    default=50,
    help="The number of streams to prompt for at a time",
)
def main(profile: str, log_group: str, page_size: str) -> None:
    """
    Delete log streams in a particular log group.

    Ordered by last event time, all streams in a group will be listed in batches
    of the given page size. This allows for approving or denying the deletion of
    each batch, rather than having to accept all streams in bulk.
    """

    session = boto3.Session(profile_name=profile)
    client = session.client('logs')

    to_delete = []
    paginator = client.get_paginator('describe_log_streams')
    for page in paginator.paginate(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=False,
            PaginationConfig={
                'PageSize': page_size
            }
    ):
        streams = page['logStreams']
        table = []
        for idx, stream in enumerate(streams):
            stream_name = stream['logStreamName']
            try:
                last_event = datetime.fromtimestamp(stream['lastEventTimestamp']/1000.0)
            except KeyError as e:
                if e.args[0] == 'lastEventTimestamp':
                    last_event = ''
                else:
                    raise
            table.append([idx, stream_name, last_event])
        click.clear()
        print(tabulate.tabulate(table, headers=["Index", "Stream Name", "Last Event Timestamp"]))
        delete = click.confirm("Delete all of the above")
        if delete:
            to_delete += [line[1] for line in table]
        else:
            continue

    click.clear()
    if not to_delete:
        return
    delete = click.confirm(f"Delete all {len(to_delete)} of the selected streams")
    if delete:
        with click.progressbar(to_delete, item_show_func=lambda x: x) as streams:
            for stream in streams:
                client.delete_log_stream(logGroupName=log_group, logStreamName=stream)


if __name__ == '__main__':
    main()
