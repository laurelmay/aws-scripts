#!/usr/bin/env python3

"""
Automate the migration of a BitBucket project to a series of CodeCommit
repositories.
"""

import atexit
import datetime
import os.path
import sys
import tempfile
from typing import List, Dict, Optional, Type, TypedDict, Literal

import boto3
import click
from mypy_boto3_codecommit.client import CodeCommitClient
from mypy_boto3_codecommit.type_defs import RepositoryMetadataTypeDef
from mypy_boto3_iam.service_resource import User
import pygit2
import requests
import tabulate
from botocore.exceptions import ClientError


class BitBucketSelfLink(TypedDict):
    href: str


class BitBucketCloneLink(TypedDict):
    href: str
    name: str


class BitBucketProjectLinks(TypedDict):
    self: List[BitBucketSelfLink]


class BitBucketRepoLinks(TypedDict):
    self: List[BitBucketSelfLink]
    clone: List[BitBucketCloneLink]


class BitBucketApiRepoProject(TypedDict):
    key: str
    id: int
    name: str
    description: str
    public: bool
    links: BitBucketProjectLinks


class BitBucketApiRepoObject(TypedDict):
    slug: str
    id: int
    name: str
    description: str
    hierarchyId: str
    scmId: Literal["git"]
    state: str
    statusMessage: str
    forkable: bool
    public: bool
    project: BitBucketApiRepoProject
    links: BitBucketRepoLinks


class BitBucketApiReposResponse(TypedDict):
    size: int
    limit: int
    isLastPage: bool
    start: bool
    values: List[BitBucketApiRepoObject]


class RepositoryMigration:
    key: str
    name: str
    description: str
    clone_url: str
    local_path: Optional[str]
    _repo: Optional[pygit2.Repository]
    codecommit: Optional[RepositoryMetadataTypeDef]

    def __init__(self, key: str, name: str, description: str, clone_url: str) -> None:
        self.key = key
        self.name = name
        self.description = description
        self.clone_url = clone_url
        self.local_path = None
        self._repo = None
        self.codecommit = None

    def clone(
        self,
        parent_dir: Optional[str] = None,
        callbacks: Optional[pygit2.RemoteCallbacks] = None,
    ) -> pygit2.Repository:
        repo_path = os.path.join(parent_dir, f"{self.name}.git")
        repo = pygit2.init_repository(repo_path, bare=True)
        remote = repo.remotes.create("origin", self.clone_url, "+refs/*:refs/*")
        repo.config["remote.origin.mirror"] = True
        remote.fetch(callbacks=callbacks)
        self.local_path = repo_path
        self._repo = repo
        return repo

    def mirror_to(
        self, new_remote: str, callbacks: Optional[pygit2.RemoteCallbacks] = None
    ) -> None:
        if not self._repo:
            raise NotImplementedError("The repo must be cloned locally first")
        repo = self._repo
        remote = repo.remotes.create("codecommit", new_remote, "+refs/*:refs/*")
        repo.config["remote.codecommit.mirror"] = True
        repo.config["core.compression"] = 0
        refs = [f"refs/heads/{branch}" for branch in repo.branches]
        remote.push(refs, callbacks=callbacks)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} key={self.key!r} name={self.name!r} clone_url={self.clone_url!r}>"

    @classmethod
    def from_api(cls, api_response: BitBucketApiRepoObject) -> "RepositoryMigration":
        name = api_response["name"]
        key = api_response["slug"]
        description = (
            api_response["description"] if "description" in api_response else ""
        )

        links = api_response["links"]
        if "clone" not in links:
            raise ValueError(f"{key} has no valid clone URLs")

        clone_urls = links["clone"]
        http_urls = [url["href"] for url in clone_urls if url["name"] == "http"]

        if not http_urls:
            raise ValueError(f"{key} must be cloneable over HTTP(S).")

        return cls(key, name, description, http_urls[0])


class BitBucketApiConnection:

    api_version = "1.0"

    session: requests.Session
    host: str
    port: int

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 443,
        verify: str | bool = True,
    ) -> None:
        session = requests.Session()
        session.auth = (username, password)
        session.headers.update({"User-Agent": "BitBucket to CodeCommit Migration"})
        session.verify = verify
        self.session = session
        self.host = host
        self.port = port

    def build_url(self, resource: str) -> str:
        return f"https://{self.host}:{self.port}/rest/api/{self.api_version}/{resource}"

    def repos_for_project(self, project: str) -> List[BitBucketApiRepoObject]:
        resource = f"projects/{project}/repos"
        repos: List[BitBucketApiRepoObject] = []
        last_page = False
        next_start = 0
        while not last_page:
            api_response = self.session.get(
                self.build_url(resource), params={"start": next_start}
            )
            api_response.raise_for_status()
            api_result: BitBucketApiReposResponse = api_response.json()
            repos.extend(api_result["values"])
            last_page = api_result["isLastPage"]
            if not last_page:
                next_start = api_result["start"]
        return repos


def create_boto_session(name: str) -> boto3.Session:
    session_args = {}
    if name:
        session_args["profile_name"] = name
    return boto3.Session(**session_args)


def build_grc_url(profile: str, repo: str) -> str:
    if profile:
        return f"codecommit://{profile}@{repo}"
    return f"codecommit://{repo}"


def create_codecommit_repo(
    codecommit: CodeCommitClient, name: str, description: str, user: User
) -> RepositoryMetadataTypeDef:
    try:
        return codecommit.create_repository(
            repositoryName=name,
            repositoryDescription=description,
            tags={
                "MigratedFrom": "BitBucket",
                "MigrationDateTime": datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "MigratedBy": user.user_name,
            },
        )["repositoryMetadata"]
    except ClientError as err:
        if "RepositoryNameExistsException" in str(err):
            return codecommit.get_repository(repositoryName=name)["repositoryMetadata"]
        raise


@click.command("bitbucket-to-codecommit")
@click.option("-p", "--profile", help="The AWS CLI profile to use")
@click.option(
    "-d",
    "--bitbucket-domain",
    help="The domain name where BitBucket can be accessed",
    required=True,
)
@click.option(
    "-u",
    "--username",
    help="The BitBucket user name to use for API calls",
    required=True,
)
@click.password_option(
    confirmation_prompt=False,
    help="The password for the BitBucket user",
    required=True,
)
@click.option(
    "--project",
    help="The slug/key of the BitBucket project",
    required=True,
)
@click.option(
    "--prefix", help="The prefix to use on the new CodeCommit repositories", default=""
)
@click.option(
    "--cert",
    help="The path to a cert bundle to verify the host. Defaults to default trust store",
)
def main(
    profile: str,
    bitbucket_domain: str,
    username: str,
    password: str,
    project: str,
    prefix: str,
    cert: str | bool,
) -> None:
    """
    Automate the migration of a BitBucket project to AWS CodeCommit.

    All the repositories in a project are copied over at the same time. Only
    git repositories are supported.
    """

    if not cert:
        cert = True
    else:
        pygit2.settings.set_ssl_cert_locations(cert_file=cert, cert_dir=None)

    api_connection = BitBucketApiConnection(
        bitbucket_domain, username, password, verify=cert
    )
    repo_data = api_connection.repos_for_project(project)
    repos = [RepositoryMigration.from_api(repo) for repo in repo_data]
    repo_table = []
    for repo in repos:
        repo_table.append([repo.key, repo.name, repo.clone_url])
    click.echo(
        tabulate.tabulate(
            repo_table, tablefmt="psql", headers=("Key", "Name", "Clone URL")
        )
    )
    click.confirm("Copy these repos to CodeCommit", abort=True)

    session = create_boto_session(profile)
    codecommit = session.client("codecommit")

    iam = session.resource("iam")
    user = iam.CurrentUser().user

    clone_creds = pygit2.UserPass(username, password)
    clone_creds_callback = pygit2.RemoteCallbacks(credentials=clone_creds)
    codecommit_creds = iam.create_service_specific_credential(
        UserName=user.user_name, ServiceName="codecommit.amazonaws.com"
    )["ServiceSpecificCredential"]
    push_creds = pygit2.UserPass(
        codecommit_creds["ServiceUserName"], codecommit_creds["ServicePassword"]
    )
    push_creds_callback = pygit2.RemoteCallbacks(credentials=push_creds)

    atexit.register(
        iam.delete_service_specific_credential,
        UserName=user.user_name,
        ServiceSpecificCredentialId=codecommit_creds["ServiceSpecificCredentialId"],
    )

    failed = []
    with tempfile.TemporaryDirectory() as tempdir:
        click.echo("Cloning repos from BitBucket...")
        with click.progressbar(
            repos, item_show_func=lambda x: x if not x else x.key
        ) as repo_clone_bar:
            for repo in repo_clone_bar:
                local_clone = repo.clone(tempdir, callbacks=clone_creds_callback)
                repo.codecommit = create_codecommit_repo(
                    codecommit, f"{prefix}{repo.key}", repo.description, user
                )

        click.echo("Mirroring repos to CodeCommit...")
        with click.progressbar(
            repos, item_show_func=lambda x: x if not x else x.key
        ) as repo_clone_bar:
            for repo in repo_clone_bar:
                try:
                    if not repo.codecommit:
                        failed.append((repo, "CodeCommit data is missing"))
                        continue
                    repo.mirror_to(
                        repo.codecommit["cloneUrlHttp"], callbacks=push_creds_callback
                    )
                except pygit2.errors.GitError as err:
                    # Errors cannot be printed now as it will result in the progress bar breaking
                    # The failures are also not critical. Printing them later allows us to provide
                    # cleaner output and error messages
                    failed.append((repo, str(err)))

    if failed:
        click.clear()
        click.echo(
            "The following repos could not be mirrored and must be copied manually"
        )
        failed_table = [
            [repo.key, repo.name, repo.clone_url, repo.codecommit["cloneUrlHttp"], err]
            for (repo, err) in failed
        ]
        click.echo(
            tabulate.tabulate(
                failed_table,
                headers=("Key", "Name", "Source", "Destination", "Error Message"),
                tablefmt="psql",
            )
        )


if __name__ == "__main__":
    main()
