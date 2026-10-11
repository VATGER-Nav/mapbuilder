"""
Feature filters for Jinja templates.

Data flows through templates as features (geometry + properties) until it is rendered:

* ``feat_*`` filters take features and return a list of features. Bare geometries and fiona
  features are accepted and converted, so the result is always a list of :class:`Feature`.
* ``render_*`` filters end a pipeline and return GRP/TopSky statements.

A feature's geometry may be a multi-geometry; renderers emit one block per part.
"""

import logging
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from itertools import pairwise

import fiona
import shapely
from jinja2 import Undefined
from shapely.geometry.base import BaseGeometry
from shapely.geometry.collection import GeometryCollection
from shapely.geometry.linestring import LineString
from shapely.geometry.point import Point
from shapely.geometry.polygon import LinearRing, Polygon
from shapely.ops import linemerge

from mapbuilder import MapbuilderException
from mapbuilder.data.feature import Feature

# Selecting features


def feat_where(things, prop: str, *values) -> list[Feature]:
    """Keeps features whose property (or ``id``) has one of the given values."""
    return [feature for feature in _features(things) if _value(feature, prop) in values]


def feat_exclude(things, prop: str, *values) -> list[Feature]:
    """Drops features whose property (or ``id``) has one of the given values."""
    return [feature for feature in _features(things) if _value(feature, prop) not in values]


def feat_select_geometry(things, name: str) -> list[Feature]:
    """Uses the named geometric property (AIXM, e.g. ``extent``) as geometry; features without it are dropped."""
    result = []
    for feature in _features(things):
        geometry = feature.geometries.get(name)
        if geometry is None:
            hint = "" if feature.geometries else " (select geometries before transforming features)"
            logging.warning(f"{_describe(feature)} has no geometry '{name}'{hint}")
        else:
            result.append(feature.with_geometry(geometry))
    return result


def feat_min_area(things, area: float) -> list[Feature]:
    """Keeps features whose (total) area is at least ``area``. Use ``feat_explode`` first to filter per part."""
    return [feature for feature in _features(things)
            if feature.geometry is not None and feature.geometry.area >= area]


# Transforming features


def feat_simplify(things, tolerance: float) -> list[Feature]:
    """Simplifies each feature's geometry with the given tolerance."""
    return [_map_geometry(feature, lambda geometry: shapely.simplify(geometry, tolerance))
            for feature in _features(things)]


def feat_explode(things) -> list[Feature]:
    """Splits multi-part geometries into one feature per part, keeping properties."""
    return [feature.with_geometry(part)
            for feature in _features(things)
            for part in _parts(feature.geometry)]


def feat_join(things) -> list[Feature]:
    """Merges the lines of all features into one feature. Only properties shared by all features are kept."""
    features = _features(things)
    if not features:
        return []

    lines = []
    for feature in features:
        for part in _parts(feature.geometry):
            if isinstance(part, LineString | LinearRing):
                lines.append(part)
            else:
                logging.warning(f"Cannot join {part.geom_type} of {_describe(feature)}, skipping it")

    if not lines:
        return []

    # noinspection PyTypeChecker
    return [_merge(features, linemerge(lines))]


def feat_join_by(things, prop: str) -> list[Feature]:
    """Joins features per value of the given property (or ``id``), in order of first appearance."""
    groups: dict = defaultdict(list)
    for feature in _features(things):
        groups[_value(feature, prop)].append(feature)

    return [joined for group in groups.values() for joined in feat_join(group)]


def feat_union(things) -> list[Feature]:
    """Unites the geometries of all features into one feature. Only properties shared by all features are kept."""
    features = _features(things)
    geometries = [feature.geometry for feature in features if feature.geometry is not None]
    if not geometries:
        return []

    return [_merge(features, shapely.union_all(geometries))]


# Rendering

# Fill patterns of GRP COORDTYPE regions and TopSky COORDPOLY: percentages or GDI+ hatch styles
FILL_PATTERNS = {"0", "5", "10", "20", "25", "30", "40", "50", "60", "70", "75", "80", "90", "100"} | {
    f"E{i}" for i in range(53)
}
LINE_TYPES = Polygon | LineString | LinearRing


def render_grp(things, area: str = "OTHER:REGION", lines: str = "line", symbol: str | None = None,
               label: str | None = None) -> str:
    """
    (GRP) Render each part by its geometry type: polygons and rings as areas (COORDTYPE ``area``), lines as
    LINE statements (``lines="line"``) or COORDTYPE:OTHER:POLYLINE (``lines="polyline"``), points as ``symbol``.
    """
    if lines not in ("line", "polyline"):
        msg = f"render_grp: lines must be 'line' or 'polyline', not {lines!r}"
        raise MapbuilderException(msg)

    result = [f"// {label}"] if label else []
    for feature, part in _rendered_parts(things, LINE_TYPES | Point, "GRP item"):
        if isinstance(part, Polygon | LinearRing):
            result.extend(_area_block(feature, part, area))
        elif isinstance(part, LineString):
            result.extend(_line_statements(part) if lines == "line" else _polyline_block(part, "OTHER:POLYLINE"))
        else:
            result.extend(_symbol_statements(feature, part, symbol))

    return "\n".join(result)


def render_ts(things, fill: int | str = 100, symbol: str | None = None, label: str | None = None) -> str:
    """
    (TS) Render each part by its geometry type: polygons and rings as COORDPOLY with ``fill``, lines as
    COORDLINE, points as ``symbol``.
    """
    fill = _fill(fill)

    result = [f"// {label}"] if label else []
    for feature, part in _rendered_parts(things, LINE_TYPES | Point, "TopSky item"):
        if isinstance(part, Polygon | LinearRing):
            result.extend(_coordpoly_block(feature, part, fill))
        elif isinstance(part, LineString):
            result.extend(_coordline_block(part))
        else:
            result.extend(_symbol_statements(feature, part, symbol))

    return "\n".join(result)


def render_area(things, area_def: str, label: str | None = None) -> str:
    """
    (GRP) Render areas with COORDTYPE/COORD, one block per polygon. Holes are not supported.
    """
    lines = [f"// {label}"] if label else []

    for feature, part in _rendered_parts(things, LINE_TYPES, "area"):
        lines.extend(_area_block(feature, part, area_def))

    return "\n".join(lines)


def render_line(things, label: str | None = None) -> str:
    """
    (GRP/TS) Render lines and polygon outlines (including holes) with LINE statements.
    """
    lines = [f"// {label}"] if label else []

    for _, part in _rendered_parts(things, LINE_TYPES, "line"):
        lines.extend(_line_statements(part))

    return "\n".join(lines)


def render_polyline(things, line_def: str = "OTHER:POLYLINE", label: str | None = None) -> str:
    """
    (GRP) Render lines and polygon outlines (including holes) as COORDTYPE ``line_def`` blocks, one per line.
    """
    lines = [f"// {label}"] if label else []

    for _, part in _rendered_parts(things, LINE_TYPES, "line"):
        lines.extend(_polyline_block(part, line_def))

    return "\n".join(lines)


def render_coordline(things, label: str | None = None) -> str:
    """
    (TS) Render lines and polygon outlines (including holes) as COORD lines, each ended by COORDLINE.
    """
    lines = [f"// {label}"] if label else []

    for _, part in _rendered_parts(things, LINE_TYPES, "line"):
        lines.extend(_coordline_block(part))

    return "\n".join(lines)


def render_coordpoly(things, fill: int | str, label: str | None = None, color: str | None = None) -> str:
    """
    (TS) Render filled polygons as COORD lines, each ended by COORDPOLY with the given fill. Holes are not supported.
    """
    fill = _fill(fill)

    lines = [f"// {label}"] if label else []
    if color is not None:
        lines.append(f"COLOR:{color}")

    for feature, part in _rendered_parts(things, LINE_TYPES, "polygon"):
        lines.extend(_coordpoly_block(feature, part, fill))

    return "\n".join(lines)


def render_coords(things) -> str:
    """
    (GRP) Render the COORD lines of a single line or polygon, e.g. for stand definitions.
    """
    parts = list(_rendered_parts(things, LINE_TYPES, "coordinate"))
    if len(parts) > 1:
        logging.warning(f"render_coords got {len(parts)} parts, rendering only those of the first")

    return "\n".join(_coord_lines(_exterior(parts[0][1]))) if parts else ""


def render_symbol(things, symbol: str, text: str | None = None, prop: str | None = None,
                  offset: tuple[int, int] = (0, 0)) -> str:
    """
    (GRP/TS) Render SYMBOL statements at each point, optionally labelled with a fixed ``text`` or the value of
    property ``prop``, displaced by ``offset`` pixels (x right, y down). Non-point geometries use a point inside them.
    """
    if text is not None and prop is not None:
        msg = "render_symbol takes either text or prop"
        raise MapbuilderException(msg)

    lines = []
    for feature, point in _anchor_points(things):
        line = f"SYMBOL:{symbol}:{_coord2es(point.coords[0])}"
        label = _label(feature, text, prop) if text is not None or prop is not None else None
        if label is not None:
            line += f":{label}:{offset[0]}:{offset[1]}"
        lines.append(line)

    return "\n".join(lines)


def render_text(things, text: str | None = None, prop: str | None = None, offset: tuple[int, int] | None = None,
                align: str | None = None) -> str:
    """
    (GRP/TS) Render TEXT statements at each point, with a fixed ``text`` or the value of property ``prop``.
    ``offset`` displaces the text by pixels (x right, y down), ``align`` sets alignment flags such as ``LT``
    (L/C/R, T/C/B). Non-point geometries use a point inside them.
    """
    if (text is None) == (prop is None):
        msg = "render_text needs either text or prop"
        raise MapbuilderException(msg)
    if align is not None and not re.fullmatch(r"[LCR]?[TCB]?", align or "-"):
        msg = f"render_text: invalid alignment {align!r}, expected L/C/R and/or T/C/B"
        raise MapbuilderException(msg)

    keyword = f"TEXT/{align}" if align else "TEXT"
    suffix = f":{offset[0]}:{offset[1]}" if offset is not None else ""

    lines = []
    for feature, point in _anchor_points(things):
        label = _label(feature, text, prop)
        if label is not None:
            lines.append(f"{keyword}:{_coord2es(point.coords[0])}:{label}{suffix}")

    return "\n".join(lines)


# Deprecated


def raw_coords(things) -> list[list[str]]:
    """
    Deprecated: COORD lines per line/polygon part. Use ``render_coords`` or ``render_area``.
    """
    return [_coord_lines(_exterior(part))
            for _, part in _rendered_parts(things, Polygon | LineString | LinearRing, "coordinate")]


# Helpers


def _features(things) -> list[Feature]:
    """Normalizes a feature, geometry or (nested) collection thereof to a flat list of features."""
    return list(_iter_features(things))


def _iter_features(things) -> Iterator[Feature]:
    if things is None:
        return
    if isinstance(things, Undefined):
        # e.g. a missing key in a template; renders nothing, but should not go unnoticed
        logging.warning(f"Feature filter got an undefined value: {things._undefined_message}")
    elif isinstance(things, Feature):
        yield things
    elif isinstance(things, fiona.Feature):
        geometry = shapely.geometry.shape(things.geometry) if things.geometry is not None else None
        yield Feature(things.id, None, dict(things.properties or {}), geometry)
    elif isinstance(things, BaseGeometry):
        yield Feature(None, None, {}, things)
    elif isinstance(things, Mapping):
        for value in things.values():
            yield from _iter_features(value)
    elif isinstance(things, Iterable) and not isinstance(things, str | bytes):
        for thing in things:
            yield from _iter_features(thing)
    else:
        raise MapbuilderException(f"Expected features or geometries, got {type(things).__name__}: {things!r}")


def _value(feature: Feature, prop: str):
    return feature.id if prop == "id" else feature.properties.get(prop)


def _map_geometry(feature: Feature, fn) -> Feature:
    return feature if feature.geometry is None else feature.with_geometry(fn(feature.geometry))


def _merge(features: list[Feature], geometry: BaseGeometry) -> Feature:
    """Creates a feature from several, keeping what they have in common."""
    first, rest = features[0], features[1:]
    properties = {key: value for key, value in first.properties.items()
                  if all(key in other.properties and other.properties[key] == value for other in rest)}
    ids = tuple(dict.fromkeys(feature.id for feature in features if feature.id is not None))

    return Feature(
        id=ids[0] if len(ids) == 1 else None,
        type=first.type if all(feature.type == first.type for feature in rest) else None,
        properties=properties,
        geometry=geometry,
        merged_from=ids,
    )


def _parts(geometry: BaseGeometry | None) -> list[BaseGeometry]:
    """Splits a (multi-)geometry or collection into its non-empty single parts."""
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, GeometryCollection) or geometry.geom_type.startswith("Multi"):
        return [part for sub in geometry.geoms for part in _parts(sub)]
    return [geometry]


def _rendered_parts(things, types, kind: str) -> Iterator[tuple[Feature, BaseGeometry]]:
    """Yields the single parts of the given types, warning about features or parts that cannot be rendered."""
    for feature in _features(things):
        parts = _parts(feature.geometry)
        if not parts:
            logging.warning(f"{_describe(feature)} has no geometry to render")

        for part in parts:
            if isinstance(part, types):
                yield feature, part
            else:
                logging.warning(f"Cannot render {part.geom_type} of {_describe(feature)} as {kind}, skipping it")


def _anchor_points(things) -> Iterator[tuple[Feature, Point]]:
    """Yields each point of point features, or one point inside other features' geometries."""
    for feature in _features(things):
        parts = _parts(feature.geometry)
        if not parts:
            logging.warning(f"{_describe(feature)} has no geometry to render")
        elif all(isinstance(part, Point) for part in parts):
            yield from ((feature, part) for part in parts)
        else:
            yield feature, feature.geometry.representative_point()


def _area_block(feature: Feature, part: BaseGeometry, area_def: str) -> list[str]:
    if isinstance(part, Polygon) and part.interiors:
        logging.warning(f"{_describe(feature)} has holes, which are not rendered")
    return [f"COORDTYPE:{area_def}", *_coord_lines(_exterior(part))]


def _line_statements(part: BaseGeometry) -> list[str]:
    return [f"LINE:{_coord2es(a)}:{_coord2es(b)}" for ring in _rings(part) for a, b in pairwise(ring.coords)]


def _polyline_block(part: BaseGeometry, line_def: str) -> list[str]:
    return [line for ring in _rings(part) for line in (f"COORDTYPE:{line_def}", *_coord_lines(ring))]


def _coordline_block(part: BaseGeometry) -> list[str]:
    return [line for ring in _rings(part) for line in (*_coord_lines(ring), "COORDLINE")]


def _coordpoly_block(feature: Feature, part: BaseGeometry, fill: str) -> list[str]:
    if isinstance(part, Polygon) and part.interiors:
        logging.warning(f"{_describe(feature)} has holes, which are not rendered")
    return [*_coord_lines(_exterior(part)), f"COORDPOLY:{fill}"]


def _symbol_statements(feature: Feature, point: Point, symbol: str | None) -> list[str]:
    if symbol is None:
        logging.warning(f"Point of {_describe(feature)} not rendered, no symbol given")
        return []
    return [f"SYMBOL:{symbol}:{_coord2es(point.coords[0])}"]


def _fill(fill: int | str) -> str:
    if str(fill) not in FILL_PATTERNS:
        msg = f"Invalid fill pattern {fill!r}, expected one of 0, 5, 10, 20, 25, ..., 90, 100 or E0-E52"
        raise MapbuilderException(msg)
    return str(fill)


def _label(feature: Feature, text: str | None, prop: str | None) -> str | None:
    """Label text for TEXT/SYMBOL: cut at '#' (unique name suffixes), without colons (field separator)."""
    value = text if prop is None else _value(feature, prop)
    if value is None:
        logging.warning(f"{_describe(feature)} has no property '{prop}' to label it with")
        return None

    label = str(value).partition("#")[0]
    if ":" in label:
        logging.warning(f"Label {label!r} of {_describe(feature)} contains colons, replacing them with spaces")
        label = label.replace(":", " ")
    return label


def _rings(part: BaseGeometry) -> list:
    return [part.exterior, *part.interiors] if isinstance(part, Polygon) else [part]


def _exterior(part: BaseGeometry):
    return part.exterior if isinstance(part, Polygon) else part


def _coord_lines(geometry) -> list[str]:
    return [f"COORD:{_coord2es(coord)}" for coord in geometry.coords]


def _describe(feature: Feature) -> str:
    if feature.id is None and feature.merged_from:
        return f"{feature.type or 'Feature'} merged from {', '.join(feature.merged_from)}"
    return f"{feature.type or 'Feature'} {feature.id or '(anonymous)'}"


def _coord2es(coord):
    return f"{coord[0]}:{coord[1]}"
