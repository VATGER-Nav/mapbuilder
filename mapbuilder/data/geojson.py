"""GeoJSON support (RFC 7946)."""

import json
import logging
from pathlib import Path
from typing import Any

from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from mapbuilder import MapbuilderException
from mapbuilder.data.feature import Feature

GEOMETRY_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon",
                  "GeometryCollection"}
# Coordinate systems with WGS 84 lon/lat coordinates, as named by the (obsolete) "crs" member
WGS84_CRS = {"urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:OGC::CRS84", "urn:ogc:def:crs:EPSG::4326",
             "EPSG:4326"}


def parse_geojson(filename: Path, id_property: str | None = None) -> dict[Any, Feature]:
    """Parses a GeoJSON file.

    Args:
        filename: Path to the GeoJSON file.
        id_property: Property used as feature ID; defaults to the ``id`` of each feature, or its
            position in the file (starting at 1) if it has none.

    Returns:
        Dictionary mapping feature IDs to features. Coordinates are stored as (lat, lon).
    """
    try:
        with filename.open("rb") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise MapbuilderException(f"Cannot read GeoJSON: {e}", file=filename) from e

    if not isinstance(data, dict):
        msg = "GeoJSON must contain an object"
        raise MapbuilderException(msg, file=filename)

    _check_crs(data, filename)
    collection_name = data.get("name")

    if data.get("type") == "FeatureCollection":
        raw_features = data.get("features") or []
    elif data.get("type") == "Feature":
        raw_features = [data]
    elif data.get("type") in GEOMETRY_TYPES:
        raw_features = [{"type": "Feature", "geometry": data, "properties": {}}]
    else:
        raise MapbuilderException(f"Unsupported GeoJSON type {data.get('type')!r}", file=filename)

    features: dict[Any, Feature] = {}
    for position, raw in enumerate(raw_features, start=1):
        properties = raw.get("properties") or {}

        if id_property is None:
            # Feature IDs are strings, like in other GIS tools
            feature_id = str(raw["id"]) if raw.get("id") is not None else str(position)
        else:
            feature_id = properties.get(id_property)
            if feature_id is None or feature_id == "":
                msg = f"Feature {position} has no {id_property}"
                raise MapbuilderException(msg, file=filename)

        if feature_id in features:
            logging.warning(f"{filename.name}: duplicate ID {feature_id}, keeping the last feature")

        try:
            geometry = _geometry(raw.get("geometry"))
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, GEOSException) as e:
            logging.warning(f"{filename.name}: skipping invalid geometry of feature {feature_id}: {e}")
            geometry = None

        features[feature_id] = Feature(str(feature_id), collection_name, properties, geometry)

    return features


def _check_crs(data: dict, filename: Path) -> None:
    """Rejects files declaring a coordinate system other than WGS 84 (RFC 7946 files never declare one)."""
    crs = data.get("crs")
    if crs is None:
        return

    name = (crs.get("properties") or {}).get("name") if isinstance(crs, dict) else None
    if name not in WGS84_CRS:
        msg = f"GeoJSON uses coordinate system {name or crs!r}, only WGS 84 (EPSG:4326) is supported"
        raise MapbuilderException(msg, file=filename)


def _geometry(raw: dict | None) -> BaseGeometry | None:
    """Converts a GeoJSON geometry, swapping lon/lat to (lat, lon)."""
    if raw is None:
        return None

    geometry = shape(raw)
    if geometry.is_empty:
        return None

    return transform(lambda x, y, z=None: (y, x) if z is None else (y, x, z), geometry)
