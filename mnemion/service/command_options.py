"""Load a command's setup only when argparse enters that command."""

import argparse


def _configure(parser, command):
    # Keep explicit imports so frozen native engines retain every supported
    # command, without making API/worker startup import desktop and recovery UI.
    if command == "journal":
        from ..journal.cli import arguments
    elif command == "recovery-kit":
        from .recovery_kit import arguments
    elif command == "local":
        from ..local_workspace import arguments
    elif command == "telemetry":
        from ..product_telemetry.cli import arguments
    elif command == "desktop-control":
        from ..desktop_operator import arguments
    elif command == "desktop-source":
        from ..desktop_sources import arguments
    elif command == "connect":
        from ..connectors.runner_options import arguments
    elif command == "desktop-agent":
        from ..desktop_agents import arguments
    elif command == "desktop-host":
        from ..host_control.desktop import arguments
    elif command == "agent-package":
        from ..agent_packages import arguments
    elif command == "supervise":
        from .supervision import arguments
    elif command == "updates":
        from .service_updates import arguments
    elif command == "host-control":
        from ..host_control.cli import arguments
    elif command == "host":
        from .host_cli import arguments
    else:
        raise ValueError("Unknown service command options")
    arguments(parser)


class CommandParser(argparse.ArgumentParser):
    def __init__(self, *args, options_command=None, **kwargs):
        self._options_command = options_command
        super().__init__(*args, **kwargs)

    def _load_options(self):
        command = self._options_command
        if command is not None:
            self._options_command = None
            _configure(self, command)

    def parse_known_args(self, args=None, namespace=None):
        self._load_options()
        return super().parse_known_args(args, namespace)

    def format_help(self):
        self._load_options()
        return super().format_help()
