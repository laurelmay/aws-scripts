#!/usr/bin/env python3

"""
Rotate access keys.
"""

import configparser
import os
from typing import List, Optional

import boto3
import click
from mypy_boto3_iam.client import IAMClient
from mypy_boto3_iam.type_defs import UserTypeDef, AccessKeyTypeDef

def user_access_keys(iam: IAMClient, user: str) -> list[AccessKeyTypeDef]:
    """
    List all IAM access keys for the given user.
    """
    keys = []
    paginator = iam.get_paginator('list_access_keys')
    for page in paginator.paginate(UserName=user):
        keys.extend(page["AccessKeyMetadata"])
    return keys


def delete_key(iam: IAMClient, access_key_id: str) -> str:
    """
    Delete the given IAM Access Key.
    """
    iam.delete_access_key(AccessKeyId=access_key_id)
    return access_key_id


def delete_keys(iam: IAMClient, message: str, existing_keys: List[AccessKeyTypeDef]) -> bool:
    click.echo(message)
    for key in existing_keys:
        click.echo(f"  {key['AccessKeyId']} (Created: {key.get('CreateDate', 'Unknown')})")

    delete_old_keys = click.confirm(
        "Do you want to delete the above access key pairs", prompt_suffix="? "
    )

    if delete_old_keys:
        for key in existing_keys:
            click.echo(f"Deleting: {key['AccessKeyId']}")
            delete_key(iam, key["AccessKeyId"])

    return delete_old_keys


def write_config(profile: str, key_pair: AccessKeyTypeDef) -> None:
    config_path = os.path.expanduser("~/.aws/credentials")
    config = configparser.ConfigParser()
    config.read(config_path)

    config[profile]["aws_access_key_id"] = key_pair["AccessKeyId"]
    config[profile]["aws_secret_access_key"] = key_pair["SecretAccessKey"]

    with open(config_path, "w") as config_file:
        config.write(config_file)


def create_pair(
    iam: IAMClient,
    user: UserTypeDef,
    existing_keys: Optional[List[AccessKeyTypeDef]] = None,
) -> Optional[AccessKeyTypeDef]:
    if existing_keys is None:
        existing_keys = user_access_keys(iam, user["UserName"])

    try:
        return iam.create_access_key(UserName=user["UserName"])["AccessKey"]
    except iam.exceptions.LimitExceededException:
        msg = "You already have two IAM access keys, the max allowed by AWS:"
        if delete_keys(iam, msg, existing_keys):
            return create_pair(iam, user, existing_keys)

    return None


def get_iam_resource(profile: str) -> IAMClient:
    session = boto3.Session(profile_name=profile)
    return session.client("iam")


@click.command("rotate-keys")
@click.option(
    "--profile",
    "-p",
    required=True,
    envvar="AWS_PROFILE",
    default="default",
    help="Profile name",
)
def main(profile: str) -> None:
    """
    Rotate access keys for an AWS IAM user. A new access key will be created,
    optionally saved to the ~/.aws/credentials file, and then old access keys
    will be optionally deleted.
    """

    iam = get_iam_resource(profile)

    user = iam.get_user()["User"]

    if not user:
        print("Unable to get user.")
        return

    key_pair = create_pair(iam, user)
    if not key_pair:
        return

    click.echo("The following will be written:")
    click.echo(f"[{profile}]")
    click.echo(f"aws_secret_key_id = {key_pair['AccessKeyId']}")
    click.echo(f"aws_secret_access_key = {key_pair['SecretAccessKey']}")
    click.echo()

    write = click.confirm(
        f"Are you sure you want to overwrite your {profile} profile",
        prompt_suffix="? ",
    )
    if write:
        write_config(profile, key_pair)
    else:
        delete_keys(iam, 'The config was not updated. You may want to delete the newly create key', [key_pair])

    iam = get_iam_resource(profile)

    existing_keys = [
        key
        for key in user_access_keys(iam, user["UserName"])
        if key["AccessKeyId"] != key_pair["AccessKeyId"]
    ]
    if existing_keys:
        delete_keys(iam, "Old access key pairs:", existing_keys)


if __name__ == "__main__":
    main()
