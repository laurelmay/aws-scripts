#!/usr/bin/env python

"""
Handles the creation of a new AWS GovCloud account.
"""

import json
import sys
import time
from typing import List, Literal, Optional

import boto3
import botocore
import click
from botocore.exceptions import ClientError
from mypy_boto3_organizations.client import OrganizationsClient
from mypy_boto3_organizations.literals import (
    AccountStatusType,
    CreateAccountStateType,
    IAMUserAccessToBillingType,
)
from mypy_boto3_organizations.type_defs import (
    CreateGovCloudAccountResponseTypeDef,
    CreateAccountStatusTypeDef,
    TagTypeDef,
)


def create_account(
    client: OrganizationsClient,
    account_name: str,
    email: str,
    iam_user_access_to_billing: IAMUserAccessToBillingType = "ALLOW",
) -> CreateGovCloudAccountResponseTypeDef:
    """
    Initiate the creation of the AWS GovCloud account.

    :returns: The AWS Organizations CreateAccountRequest ID
    """
    return client.create_gov_cloud_account(
        Email=email,
        AccountName=account_name,
        IamUserAccessToBilling=iam_user_access_to_billing,
    )


def get_account_status(
    client: OrganizationsClient, create_account_request_id: str
) -> CreateAccountStatusTypeDef:
    return client.describe_create_account_status(
        CreateAccountRequestId=create_account_request_id
    )["CreateAccountStatus"]


def wait_for_creation(
    client: OrganizationsClient,
    create_account_request_id: str,
    wait: int = 10,
    times: int = 30,
) -> bool:
    def is_creation_complete() -> CreateAccountStateType | Literal["ERROR"]:
        try:
            status_info = get_account_status(client, create_account_request_id)
            return status_info["State"]
        except (ClientError, KeyError):
            return "ERROR"

    attempts = 0
    print("Waiting for account creation to complete...")
    while attempts < times and (state := is_creation_complete()) == "IN_PROGRESS":
        attempts += 1
        time.sleep(wait)
    status_map = {
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
        "IN_PROGRESS": "timed out",
    }
    print(f"Account completion {status_map.get(state, f'unknown ({state})')}...")

    return state == "SUCCEEDED"


def tag_commercial_account(client: OrganizationsClient, create_account_request_id: str) -> None:
    status_info = get_account_status(client, create_account_request_id)
    tag_data: List[TagTypeDef] = [{"Key": "GovCloudAccountId", "Value": status_info["GovCloudAccountId"]}]
    client.tag_resource(ResourceId=status_info["AccountId"], Tags=tag_data)


@click.command("create-govcloud-account")
@click.option(
    "--account-name", required=True, help="The friendly name of the new account"
)
@click.option(
    "--email",
    required=True,
    help="The email address of the owner to assign to the new member account.",
)
@click.option(
    "--iam-user-access-to-billing",
    required=True,
    type=click.Choice(("ALLOW", "DENY")),
    default="ALLOW",
    help="Allow IAM users in the linked commercial account to access billing.",
)
def main(account_name: str, email: str, iam_user_access_to_billing: IAMUserAccessToBillingType) -> None:
    client = boto3.client("organizations")
    car_response = create_account(
        client, account_name, email, iam_user_access_to_billing
    )
    car_id = car_response["CreateAccountStatus"]["Id"]
    success = wait_for_creation(client, car_id)
    if not success:
        print("Account creation did not complete successfully in time")
        print(f"Request id: {car_id}")
        print(json.dumps(get_account_status(client, car_id), indent=4))
    tag_commercial_account(client, car_id)
    print("Account creation completed successfully.")
    print(json.dumps(get_account_status(client, car_id), indent=4))


if __name__ == "__main__":
    main()
