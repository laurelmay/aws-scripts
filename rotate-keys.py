#!/usr/bin/env python3

"""
Rotate access keys.
"""

import configparser
import os
from typing import Iterable, List, Optional

import boto3
import click

from mypy_boto3_sts.client import STSClient
from mypy_boto3_iam.service_resource import AccessKey, IAMServiceResource, User, AccessKeyPair


def get_user(users: Iterable[User], arn: str) -> Optional[User]:
    for user in users:
        if user.arn == arn:
            return user
    return None


def delete_keys(message: str, existing_keys: List[AccessKey]) -> bool:
    click.echo(message)
    for key in existing_keys:
        click.echo(f"  {key.access_key_id} (Created: {key.create_date})")

    delete_old_keys = click.confirm(
        "Do you want to delete the above access key pairs", prompt_suffix="? "
    )

    if delete_old_keys:
        for key in existing_keys:
            click.echo(f"Deleting: {key.access_key_id}")
            key.delete()

    return delete_old_keys


def write_config(profile: str, key_pair: AccessKeyPair) -> None:
    config_path = os.path.expanduser("~/.aws/credentials")
    config = configparser.ConfigParser()
    config.read(config_path)

    config[profile]["aws_access_key_id"] = key_pair.access_key_id
    config[profile]["aws_secret_access_key"] = key_pair.secret_access_key

    with open(config_path, "w") as config_file:
        config.write(config_file)


def create_pair(
    iam: IAMServiceResource,
    user: User,
    existing_keys: Optional[List[AccessKey]] = None,
) -> Optional[AccessKeyPair]:
    if existing_keys is None:
        existing_keys = list(user.access_keys.all())

    try:
        return user.create_access_key_pair()
    except iam.meta.client.exceptions.LimitExceededException:
        msg = "You already have two IAM access keys, the max allowed by AWS:"
        if delete_keys(msg, existing_keys):
            return create_pair(iam, user, existing_keys)

    return None


def get_iam_resource(profile: str) -> IAMServiceResource:
    session = boto3.Session(profile_name=profile)
    return session.resource("iam")


def get_sts_client(profile: str) -> STSClient:
    session = boto3.Session(profile_name=profile)
    return session.client("sts")


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
    sts = get_sts_client(profile)

    user_arn = sts.get_caller_identity()["Arn"]
    user = get_user(iam.users.all(), user_arn)

    if not user:
        print("Unable to get user.")
        return

    key_pair = create_pair(iam, user)
    if not key_pair:
        return

    click.echo("The following will be written:")
    click.echo(f"[{profile}]")
    click.echo(f"aws_secret_key_id = {key_pair.access_key_id}")
    click.echo(f"aws_secret_access_key = {key_pair.secret_access_key}")
    click.echo()

    write = click.confirm(
        f"Are you sure you want to overwrite your {profile} profile",
        prompt_suffix="? ",
    )
    if write:
        write_config(profile, key_pair)
    else:
        delete_new = click.confirm(
            f"Do you want to delete the newly created key",
            default=False,
            prompt_suffix="? ",
        )
        if delete_new:
            key_pair.delete()
        return

    iam = get_iam_resource(profile)

    existing_keys = [
        key
        for key in user.access_keys.all()
        if key.access_key_id != key_pair.access_key_id
    ]
    if existing_keys:
        delete_keys("Old access key pairs:", existing_keys)


if __name__ == "__main__":
    main()
