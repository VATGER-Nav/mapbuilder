"""GeoPackage support, reading the SQLite database directly (see https://www.geopackage.org/spec/)."""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import shapely
from shapely.errors import GEOSException
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from mapbuilder import MapbuilderException
from mapbuilder.data.feature import Feature

# Bytes of the envelope in a GeoPackage geometry header, by envelope contents indicator
ENVELOPE_SIZES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def parse_gpkg(filename: Path, layers: list[str] | None = None, id_property: str | None = None) -> dict:
    """Parses feature layers of a GeoPackage file.

    Args:
        filename: Path to the GeoPackage file.
        layers: Names of the layers to load; all feature layers if not given.
        id_property: Column used as feature ID; defaults to the feature ID (primary key) of each layer.

    Returns:
        Dictionary mapping layer names to their features by ID. Coordinates are stored as (lat, lon).
    """
    if not filename.is_file():
        raise MapbuilderException(f"GeoPackage {filename} not found", file=filename)

    with closing(sqlite3.connect(f"file:{filename}?mode=ro", uri=True)) as db:
        available = _feature_layers(db, filename)

        if layers is None:
            layers = list(available)
        for layer in layers:
            if layer not in available:
                msg = f"Layer {layer} not found, available layers: {', '.join(available) or 'none'}"
                raise MapbuilderException(msg, file=filename)

        return {layer: _parse_layer(db, filename, layer, available[layer], id_property) for layer in layers}


def _feature_layers(db: sqlite3.Connection, filename: Path) -> dict[str, tuple[str, str]]:
    """Returns the geometry column and coordinate system ("EPSG:4326") of each feature layer."""
    try:
        rows = db.execute(
            """SELECT c.table_name, g.column_name, s.organization, s.organization_coordsys_id
               FROM gpkg_contents c
               JOIN gpkg_geometry_columns g ON g.table_name = c.table_name
               LEFT JOIN gpkg_spatial_ref_sys s ON s.srs_id = g.srs_id
               WHERE c.data_type = 'features'
               ORDER BY c.table_name""",
        ).fetchall()
    except sqlite3.DatabaseError as e:
        raise MapbuilderException(f"Cannot read GeoPackage: {e}", file=filename) from e

    return {table: (column, f"{(org or '?').upper()}:{coordsys_id}") for table, column, org, coordsys_id in rows}


def _parse_layer(db: sqlite3.Connection, filename: Path, layer: str, layer_info: tuple[str, str],
                 id_property: str | None) -> dict[Any, Feature]:
    geometry_column, crs = layer_info
    if crs != "EPSG:4326":
        msg = f"Layer {layer} uses coordinate system {crs}, only EPSG:4326 (WGS 84) is supported"
        raise MapbuilderException(msg, file=filename)

    columns = db.execute(f'PRAGMA table_info("{layer}")').fetchall()  # (cid, name, type, notnull, default, pk)
    fid_column = next((name for _, name, _, _, _, pk in columns if pk), None)
    booleans = {name for _, name, column_type, *_ in columns if column_type.upper() == "BOOLEAN"}
    properties = [name for _, name, *_ in columns if name not in (fid_column, geometry_column)]

    if id_property is not None and id_property not in properties:
        msg = f"Layer {layer} has no column {id_property} to use as ID"
        raise MapbuilderException(msg, file=filename)

    selected = ", ".join(f'"{name}"' for name in (fid_column or "rowid", geometry_column, *properties))
    features: dict[Any, Feature] = {}

    for fid, blob, *values in db.execute(f'SELECT {selected} FROM "{layer}"'):
        props = {name: bool(value) if name in booleans and value is not None else value
                 for name, value in zip(properties, values, strict=True)}

        # Feature IDs are strings, like in other GIS tools
        feature_id = str(fid) if id_property is None else props[id_property]
        if feature_id is None or feature_id == "":
            msg = f"Feature {fid} in layer {layer} has no {id_property or 'feature ID'}"
            raise MapbuilderException(msg, file=filename)
        if feature_id in features:
            logging.warning(f"{filename.name}: duplicate ID {feature_id} in layer {layer}, keeping the last feature")

        try:
            geometry = _geometry(blob)
        except (ValueError, IndexError, GEOSException) as e:
            logging.warning(f"{filename.name}: skipping invalid geometry of feature {fid} in layer {layer}: {e}")
            geometry = None

        features[feature_id] = Feature(str(feature_id), layer, props, geometry)

    return features


def _geometry(blob: bytes | None) -> BaseGeometry | None:
    """Decodes a GeoPackage geometry blob, swapping lon/lat to (lat, lon)."""
    if blob is None:
        return None
    if blob[:2] != b"GP":
        msg = "not a GeoPackage geometry"
        raise ValueError(msg)

    flags = blob[3]
    if flags & 0b10000:  # empty geometry
        return None

    envelope = (flags >> 1) & 0b111
    if envelope not in ENVELOPE_SIZES:
        msg = f"invalid envelope indicator {envelope}"
        raise ValueError(msg)

    geometry = shapely.from_wkb(blob[8 + ENVELOPE_SIZES[envelope]:])
    return transform(lambda x, y, z=None: (y, x) if z is None else (y, x, z), geometry)
