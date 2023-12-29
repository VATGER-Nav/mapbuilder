import argparse
import pprint

from rich.logging import RichHandler
import os.path
import sys
import logging
import tomllib
from pathlib import Path

from .builder import Builder


def main(prog_name: str, *argv: str) -> int:
    argp = argparse.ArgumentParser(
        prog=os.path.basename(prog_name), usage="%(prog)s [options] target_dir"
    )
    argp.add_argument("target_dir", type=Path, help="Target directory")
    argp.add_argument(
        "-s",
        "--source",
        type=Path,
        default=Path("."),
        help="Source directory (default: current directory)",
    )
    argp.add_argument("--debug", action="store_true", help="Enable debug output")

    args = argp.parse_args(argv)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    if not args.target_dir:
        argp.error("Target directory is required")

    config_file = (args.source / "mapbuilder.toml").resolve()
    logging.debug("Source directory: {}".format(config_file))
    if not config_file.is_file():
        argp.error("No mapbuilder.toml found in source directory.")

    with open(config_file, mode="rb") as cfh:
        config = tomllib.load(cfh)

    pprint.pprint(config)
    builder = Builder(args.source, args.target_dir, config)
    builder.build()
    return 0


def entry() -> None:
    logging.basicConfig(
        format="{message}",
        level=logging.INFO,
        style="{",
        handlers=[RichHandler(show_time=False, show_path=False)],
    )

    sys.exit(main(*sys.argv))


if __name__ == "__main__":
    entry()
