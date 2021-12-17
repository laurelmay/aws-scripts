import importlib

from pathlib import Path

import click

_ALL_COMMANDS: list[click.Command] = []


def _load_commands() -> list[click.Command]:
    directory = Path(__file__).resolve().parent
    commands = []
    for file_path in directory.iterdir():
        if file_path.stem == "__init__" or file_path.suffix != ".py":
            continue

        module_name = file_path.stem
        try:
            spec = importlib.util.spec_from_loader(module_name, None)
            if not spec:
                continue
            command_module = importlib.util.module_from_spec(spec)
            exec(file_path.open().read(), command_module.__dict__)
        except (ImportError, SyntaxError) as import_error:
            print(import_error)
        else:
            module_contents = [
                getattr(command_module, item_name) for item_name in dir(command_module)
            ]
            for content in module_contents:
                if isinstance(content, click.Command):
                    commands.append(content)
    return commands


def all_commands() -> list[click.Command]:
    global _ALL_COMMANDS
    if not _ALL_COMMANDS:
        _ALL_COMMANDS = _load_commands()
    return list(_ALL_COMMANDS)


if not _ALL_COMMANDS:
    _ALL_COMMANDS = _load_commands()
