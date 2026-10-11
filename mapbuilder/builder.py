import logging
import re
import time
from pathlib import Path

import mapbuilder.data.aixm

from .cache import Cache
from .data.aixm2 import parse_aixm
from .data.aixm51 import parse_aixm as parse_aixm51
from .data.gpkg import parse_gpkg
from .data.kml import KMLParser
from .data.kml2 import parse_kml
from .data.rwy import parse_runway
from .data.sectors import parse_sectors, sectors_to_lines
from .data.sidstar import parse_sidstar
from .dfs import datasets
from .handlers.jinja import JinjaHandler
from .handlers.plaintext import PlainTextHandler
from .utils.geojson import load_geojson

SUFFIXES = [".txt", ".jinja"]


class Builder:
    def __init__(self, source_dir, target_dir, cache_dir, config):
        self.build_version = int(time.time())
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.cache = Cache(cache_dir)
        self.config = config

        self.data = {}
        self.dfs_datasets = None
        for data_source in config["data"]:
            data_source_type = config["data"][data_source]["type"]
            if data_source_type == "aixm":
                logging.debug(f"Loading AIXM source {data_source}...")

                src = self.__load(data_source, config["data"][data_source]["source"])
                if src is not None:
                    self.data[data_source] = parse_aixm(src)
            elif data_source_type == "aixm2":
                logging.debug(f"Loading AIXM2 source {data_source}...")

                src = self.__load(data_source, config["data"][data_source]["source"])
                if src is not None:
                    self.data[data_source] = mapbuilder.data.aixm.parse_aixm(src)
            elif data_source_type == "aixm51":
                logging.debug(f"Loading AIXM 5.1 source {data_source}...")

                src = self.__load(data_source, config["data"][data_source]["source"])
                if src is not None:
                    self.data[data_source] = parse_aixm51(src)
            elif data_source_type == "kml":
                logging.debug(f"Loading KML source {data_source}...")
                data_root = None
                if "root" in config["data"][data_source]:
                    data_root = config["data"][data_source]["root"]
                parser = KMLParser(
                    source_dir / config["data"][data_source]["source"], data_root
                )
                self.data[data_source] = parser.parse()
            elif data_source_type == "kml2":
                logging.debug(f"Loading KML source {data_source} as features...")
                self.data[data_source] = parse_kml(
                    source_dir / config["data"][data_source]["source"],
                    config["data"][data_source].get("root"),
                )
            elif data_source_type == "raw":
                logging.debug(f"Loading raw source {data_source}...")
                with (source_dir / config["data"][data_source]["source"]).open(
                        encoding="iso-8859-1",
                ) as f:
                    self.data[data_source] = f.read()
            elif data_source_type == "ese":
                logging.debug(f"Loading ESE source {data_source}...")
                self.data[data_source] = {
                    "SIDSTAR": parse_sidstar(
                        source_dir / config["data"][data_source]["source"]
                    ),
                }
            elif data_source_type == "sct":
                logging.debug(f"Loading SCT source {data_source}...")
                self.data[data_source] = {
                    "RUNWAY": parse_runway(
                        source_dir / config["data"][data_source]["source"]
                    ),
                }
            elif data_source_type == "sectors":
                logging.debug(f"Loading sectors source {data_source}...")
                fixes = parse_sectors(source_dir / config["data"][data_source]["source"])
                self.data[data_source] = {
                    "fixes": fixes,
                    "lines": sectors_to_lines(fixes),
                }
            elif data_source_type == "gpkg":
                logging.debug(f"Loading GeoPackage source {data_source}...")
                self.data[data_source] = parse_gpkg(
                    source_dir / config["data"][data_source]["source"],
                    config["data"][data_source]["layers"],
                    config["data"][data_source].get("id_property", None),
                )
            elif data_source_type == "geojson":
                logging.debug(f"Loading GeoJSON source {data_source}...")

                src = self.__load(data_source, config["data"][data_source]["source"])
                if src is not None:
                    self.data[data_source] = load_geojson(src)
            else:
                logging.error(f"Unknown data source type for data source {data_source}")

        self.jinja_handler = JinjaHandler(self.data, self.config, cache_dir)

    def __load(self, name: str, src: str):
        if src.startswith("dfs:"):
            _, amdt, leaf, data_format = src.split(":")
            amdt_id = int(amdt)

            if self.dfs_datasets is None:
                self.dfs_datasets = datasets.get_dfs_datasets(self.cache)

            url = datasets.get_dfs_url(self.dfs_datasets[amdt_id], amdt_id, leaf, data_format)
            if url is None:
                logging.error(f"Cannot get source URL for DFS dataset {name}")
                return None
            return self.cache.get(f"dfs-{name}", url, 96)
        if src.startswith("http"):
            return self.cache.get(f"remote-{name}", src, 96)
        else:
            return self.source_dir / src

    def build(self):
        for profile in self.config["profiles"]:
            self.build_profile(profile)

    def __best_item(self, profile_id, item):
        """Looks for the best file for an item."""
        profile_candidates = [
            profile_id,
            *self.config["profiles"][profile_id]["aliases"],
        ]

        for candidate in profile_candidates:
            for suffix in SUFFIXES:
                candidate_file = item / f"{candidate}{suffix}"
                if candidate_file.is_file():
                    return candidate_file

        return None

    def __handle_item(self, item):
        if item.suffix == ".txt":
            return PlainTextHandler().handle(item)
        elif item.suffix == ".jinja":
            return self.jinja_handler.handle(item)
        else:
            logging.warning(f"No handler for file type {item.suffix} known. Skipping.")
            return None

    def build_profile(self, profile_id: str):
        logging.info(f"Building profile {profile_id}...")

        for map_data in self.config["profiles"][profile_id]["maps"]:
            self.build_profile_map(profile_id, map_data)

    def build_profile_map(self, profile_id: str, map_data: dict):
        start_ts = time.perf_counter()
        map_id = map_data["map"]
        target_file = map_data["target"]
        maps_root = self.source_dir / "maps" / map_id

        if not maps_root.is_dir():
            logging.error(f"Map `{map_id}' is not a directory. Skipping.")
            return

        header = f"// {map_id} {profile_id}\n// Auto-generated by mapbuilder. Do not edit manually."

        if map_data.get("add-version"):
            header = header + f"\n//VERSION:{self.build_version}"

        profile_contents = [header]

        self.build_visitor(profile_id, maps_root, profile_contents)

        profile_content = "\n\n".join(profile_contents)

        profile_content = re.sub(r"^[ \t]+", "", profile_content, flags=re.MULTILINE)
        profile_content = re.sub(r"\r?\n[ \t]*(?:\r?\n)+", r"\n\n", profile_content)

        with (self.target_dir / Path(target_file)).open(
                mode="w",
                encoding="iso-8859-1",
        ) as tgt_file:
            tgt_file.write(profile_content)

        end_ts = time.perf_counter()
        logging.info(f"Built {map_id} ({end_ts - start_ts:0.4f} sec).")

    def build_visitor(self, profile_id, rootdir, profile_contents):
        # Possibly inefficient, but we do not have a large number of files (hopefully)
        for item in sorted(rootdir.iterdir()):
            logging.debug(f"Processing item {item}")

            # if regular subdirectory
            if item.is_dir() and item.suffix != ".d":
                self.build_visitor(profile_id, item, profile_contents)
            else:
                # if per-profile content
                if item.is_dir() and item.suffix == ".d":
                    best_item = self.__best_item(profile_id, item)

                    if best_item:
                        item = best_item

                content = self.__handle_item(item)
                if content:
                    profile_contents.append(content)
