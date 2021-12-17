#!/usr/bin/env python3

import json
from typing import Dict, List

import boto3
import click
from botocore.exceptions import ClientError
from mypy_boto3_cloudformation.client import CloudFormationClient
from mypy_boto3_cloudformation.paginator import (
    ListExportsPaginator,
    ListImportsPaginator,
)

from aws_scripts.options import profile_option
from aws_scripts.session import create_session


def get_stack_name(arn: str) -> str:
    segments = arn.split(":")
    stack_id = segments[-1]
    _, name, uuid = stack_id.split("/")
    return name


def get_stack_export_names(cfn: CloudFormationClient, stack: str) -> List[str]:
    export_paginator: ListExportsPaginator = cfn.get_paginator("list_exports")
    exports = []
    for page in export_paginator.paginate():
        exports.extend(page.get("Exports", []))
    return [
        export["Name"]
        for export in exports
        if get_stack_name(export["ExportingStackId"]) == stack
    ]


def get_stacks_using_export(cfn: CloudFormationClient, export: str) -> List[str]:
    import_paginator: ListImportsPaginator = cfn.get_paginator("list_imports")
    importers = []
    try:
        for page in import_paginator.paginate(ExportName=export):
            importers.extend(page.get("Imports", []))
    except ClientError as e:
        if "is not imported by any" not in str(e):
            raise
    return importers


def map_users_to_exports(map: Dict[str, List[str]]) -> Dict[str, List[str]]:
    output_map = {}
    for export, stacks in map.items():
        for stack in stacks:
            output_map.setdefault(stack, [])
            output_map[stack].append(export)
    return output_map


@click.command("cfn-stack-consumers")
@profile_option
@click.option("--stack-name", "-n", help="The stack to check usage of", required=True)
def main(profile: str, stack_name: str) -> None:
    """
    Lists stacks that use the exports of a given stack.
    """

    session = create_session(profile_name=profile)
    cfn = session.client("cloudformation")

    export_map = {
        export: get_stacks_using_export(cfn, export)
        for export in get_stack_export_names(cfn, stack_name)
    }

    print(json.dumps(map_users_to_exports(export_map), indent=4))


if __name__ == "__main__":
    main()
