import click

from .commands import all_commands


@click.group("aws-utils")
def main():
    """
    A collection of scripts that are useful for interacting with AWS.
    """
    pass


for command in all_commands():
    main.add_command(command)

if __name__ == "__main__":
    main()
