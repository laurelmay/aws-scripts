import json
from typing import  TextIO

import boto3
import click


@click.command("dynamodb-item-import")
@click.option(
    "--item-file",
    "-i",
    type=click.File(encoding="utf-8"),
    help="File containing the items to import in JSON format",
)
@click.option(
    "--table-name", "-t", type=click.STRING, help="The name of the DynamoDB table"
)
def main(item_file: TextIO, table_name: str) -> None:
    client = boto3.client("dynamodb")
    items = json.load(item_file)
    for item in items:
        client.put_item(TableName=table_name, Item=item)


if __name__ == "__main__":
    pass
