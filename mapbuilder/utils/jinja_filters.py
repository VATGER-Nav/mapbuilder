import logging
from collections.abc import Iterable

import fiona
import shapely
from fiona import Feature
from shapely import MultiLineString
from shapely.coords import CoordinateSequence
from shapely.geometry.base import BaseGeometry
from shapely.geometry.collection import GeometryCollection
from shapely.geometry.linestring import LineString
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import LinearRing, Polygon
from shapely.ops import linemerge

from mapbuilder import MapbuilderException


def render_area(features, area_def: str, designator: str | None = None):
    """
    (GRP) Render area coordinates with COORDTYPE/COORD.
    """
    lines = [f"// {designator}"] if designator else []

    for feature in _ensure_iterable(features):
        for sequence in _coords(feature):
            lines.append(f"COORDTYPE:{area_def}")
            lines.extend(sequence)

    return "\n".join(lines)


def render_line(features, designator: str | None = None):
    """
    (GRP/TS) Render lines with LINE statements.
    """
    lines = [f"// {designator}"] if designator else []

    for feature in _ensure_iterable(features):
        _lines(lines, feature)

    return "\n".join(lines)


def feat_exclude_property(features: list[Feature], prop: str, *values: str) -> list[Feature]:
    """
    Filter features by property value, excluding those with specified values.
    """
    if prop == "id":
        return [feature for feature in features if feature.id not in values]
    else:
        return [feature for feature in features if feature.properties.get(prop) not in values]


def geom_simplify(thing: Feature | BaseGeometry, tolerance):
    """
    (FEAT-TO-GEO) Simplify geometries in the given features using the specified tolerance.
    """
    return [shapely.simplify(_geometry(feature), tolerance)
           for feature in _ensure_iterable(thing)]


def geom_join(features):
    lines = [_geometry(geo) for geo in _ensure_iterable(features)]
    # noinspection PyTypeChecker
    return linemerge(lines)


def geom_filter_min_area(thing: Feature | BaseGeometry, min_area: float):
    """
    (FEAT-TO-GEO) Filter geometries in the given features by minimum area.
    """
    return [feature for feature in _ensure_iterable(thing)
            if _geometry(feature).area >= min_area]


def _coords(thing) -> list[list[str]]:
    """
    Render COORD lines for the given scalar feature.
    """
    geometry = _geometry(thing)
    sequences = _coordinates(geometry)

    return [[f"COORD:{_coord2es(c)}" for c in sequence] for sequence in sequences]


def _lines(lines: list, feature):
    geometries = _coordinates(feature)

    for geometry in geometries:
        count = len(geometry)

        for idx, point in enumerate(geometry):
            if idx == count - 1:
                break

            lines.append(
                f"LINE:{_coord2es((point[0], point[1]))}"
                f":{_coord2es((geometry[idx + 1][0], geometry[idx + 1][1]))}",
            )


def _geometry(feat_or_geom: Feature | BaseGeometry) -> BaseGeometry:
    """
    Extracts geometry from the given feature type.
    """

    if isinstance(feat_or_geom, fiona.Feature):
        return shapely.geometry.shape(feat_or_geom.geometry)
    elif isinstance(feat_or_geom, BaseGeometry):
        return feat_or_geom

    raise MapbuilderException(f"Unsupported geometry type: {type(feat_or_geom)}")


def _coordinates(thing: Feature | BaseGeometry) -> list[CoordinateSequence]:
    """
    Extracts coordinate sequences from the given geometry or feature.
    """
    if isinstance(thing, Feature):
        thing = _geometry(thing)

    if isinstance(thing, BaseGeometry) and thing.is_empty:
        logging.warning("Empty geometry encountered.")
        return []

    if isinstance(thing, Polygon):
        return [thing.exterior.coords]
    elif isinstance(thing, (LinearRing, LineString)):
        return [thing.coords]
    elif isinstance(thing, MultiLineString):
        return [line.coords for line in thing.geoms]
    elif isinstance(thing, MultiPolygon):
        return [poly.exterior.coords for poly in thing.geoms]
    elif isinstance(thing, GeometryCollection):
        return [coord for geom in thing.geoms for coord in _coordinates(geom)]

    raise MapbuilderException(f"Unsupported type to extract coordinates from: {type(thing)}")


def _ensure_iterable(x):
    if isinstance(x, Iterable) and not isinstance(x, (str, bytes, Feature)):
        return x
    return [x]


def _coord2es(coord):
    return f"{coord[0]}:{coord[1]}"
