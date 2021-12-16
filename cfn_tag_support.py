#!/usr/bin/env python3

from typing import Optional

import click
import requests


def specification_download_url(region: str) -> str:
    return f"https://s3.{region}.amazonaws.com/cfn-resource-specifications-{region}-prod/latest/CloudFormationResourceSpecification.json"


@click.command("cfn-tag-support")
@click.option(
    '--region',
    default="us-east-1",
    help="The AWS region to check support for",
)
@click.option(
    '--property-name',
    default='Tags',
    help="The name of the property to search for"
)
@click.option(
    '--resource-name-filter',
    required=False,
    help="The filter to apply to resource names, checks if the input is included in the resource name"
)
def main(region: str, property_name: str, resource_name_filter: Optional[str]) -> None:
    """
    Finds CloudFormation resources that have a given property (by default, 'Tags').

    Given a region (default: us-east-1) and property (default: 'Tags'), lists all the resources
    for which CloudFormation supports that property in that region. A filter can be applied to limit
    the resources that will be returned (a simple substring match is performed).
    """
    if not resource_name_filter:
        resource_name_filter = ""

    try:
        click.echo(f"Downloading CloudFormation spec for {region}")
        cfn_spec = requests.get(specification_download_url(region)).json()
    except IOError:
        click.echo(f"Unable to fetch/parse the CloudFormation spec for {region}", err=True)
        return

    resources = cfn_spec['ResourceTypes']
    support_tagging = []

    support_tagging = [name for name, data in resources.items() if property_name in data['Properties']]
    support_tagging = [resource for resource in support_tagging if resource_name_filter in resource]

    if len(support_tagging) > 15:
        echo = click.echo_via_pager
    else:
        echo = click.echo
    echo('\n'.join(sorted(support_tagging)))


if __name__ == "__main__":
    main()
