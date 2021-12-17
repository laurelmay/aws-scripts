import click

profile_option = click.option(
    "--profile",
    "-p",
    required=True,
    envvar="AWS_PROFILE",
    default="default",
    help="AWS CLI/SDK profile name",
)
