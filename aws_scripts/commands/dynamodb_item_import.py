import json
from typing import TextIO

import boto3
import click

from aws_scripts.options import profile_option
from aws_scripts.session import create_session


@click.command("dynamodb-item-import")
@profile_option
@click.option(
    "--item-file",
    "-i",
    type=click.File(encoding="utf-8"),
    help="File containing the items to import in JSON format",
)
@click.option(
    "--table-name", "-t", type=click.STRING, help="The name of the DynamoDB table"
)
def main(profile: str, item_file: TextIO, table_name: str) -> None:
    """
    Import data into a given DynamoDB table
    """

    client = create_session(profile_name=profile).client("dynamodb")
    items = json.load(item_file)
    for item in items:
        client.put_item(TableName=table_name, Item=item)


if __name__ == "__main__":
    pass
