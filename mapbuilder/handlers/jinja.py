from pathlib import Path
from typing import List

import numpy
from jinja2 import Environment, FileSystemLoader
import shapely, shapely.ops
from shapely import Geometry, Polygon

from mapbuilder.data.aixm2 import AIXMFeature


class JinjaHandler:
    def handle(self, item: Path, data) -> str:
        file_loader = FileSystemLoader(item.parent)
        jinja_env = Environment(loader=file_loader)
        jinja_env.globals.update(
            data=data,
            combine=combine,
            geoms=geoms,
        )
        jinja_env.filters.update(
            geoms=geoms,
            simplify=simplify,
            to_line=to_line,
            to_coordline=to_coordline,
            to_poly=to_poly,
            join_segments=join_segments,
            filter_smaller_than=filter_smaller_than,
            envelope=envelope,
            to_text=to_text,
            to_text_buffer=to_text_buffer,
            to_symbol=to_symbol,
        )

        return jinja_env.get_template(item.name).render()


def geoms(features: List[AIXMFeature] | AIXMFeature) -> List[Geometry]:
    """Extracts the geometries from the given (list of) feature(s)"""
    if isinstance(features, list):
        result = [geometry for instance in features for geometry in instance.geometries]
    else:
        result = features.geometries

    return result


def combine(geometries: list[Geometry]) -> Geometry:
    combined = shapely.ops.unary_union([Polygon(geo) for geo in geometries])
    #combined = shapely.ops.unary_union(geometries)
    #   return combined.exterior
    return shapely.buffer(combined, 0.00000000000001)


def to_text_buffer(geometry, label: str, color: str, adapt_to_length=True):
    if isinstance(geometry, list):
        point = geometry[0]
    else:
        point = geometry

    if point is None:
        return ""

    lines = []
    distance = 0.00008
    labeltext, _, _ = label.partition("#")
    if adapt_to_length:
        distance += 0.00001 * len(labeltext)
    buffer = shapely.buffer(point, distance).envelope.boundary

    _render_polygon(lines, [buffer], color)

    return "\n".join(lines)


def to_text(geometry, label: str):
    if isinstance(geometry, list):
        point = geometry[0]
    else:
        point = geometry

    if point is None:
        return ""

    labeltext, _, _ = label.partition("#")
    return f"TEXT:{coord2es(point.coords[0])}:{labeltext}"


def to_symbol(geometry, symbol):
    if isinstance(geometry, list):
        point = geometry[0]
    else:
        point = geometry

    if point is None:
        return ""

    return f"SYMBOL:{symbol}:{coord2es(point.coords[0])}"


def _get_geoms(thing):
    """Extracts the geometries from either an AIXMFeature or geometry object"""
    if isinstance(thing, list):
        if len(thing) == 0:
            return []

        if isinstance(thing[0], AIXMFeature):
            return [geometry for instance in thing for geometry in instance.geometries]
        else:
            return thing
    elif isinstance(thing, AIXMFeature):
        return thing.geometries
    elif isinstance(thing, shapely.MultiLineString):
        return thing.geoms
    elif isinstance(thing, shapely.LineString):
        return [thing]
    elif isinstance(thing, shapely.LinearRing):
        return [thing]
    elif isinstance(thing, shapely.Polygon):
        return [thing.exterior]
    elif isinstance(thing, shapely.geometry.base.GeometrySequence):
        return thing
    elif isinstance(thing, numpy.ndarray):
        return thing
    else:
        return []


def to_line(geometries, designator: str):
    lines = [f"// {designator}"] if designator else []

    _render_linestring(lines, _get_geoms(geometries))

    return "\n".join(lines)


def to_coordline(geometries, designator: str):
    lines = [f"// {designator}"] if designator else []

    _render_coords(lines, _get_geoms(geometries))

    lines.append("COORDLINE")
    lines.append("")
    return "\n".join(lines)


def filter_smaller_than(geometries, threshold):
    geo = _get_geoms(geometries)
    if isinstance(geo, list):
        return list(filter(lambda geometry: geometry.envelope.area >= threshold, geo))


def envelope(geometries):
    return shapely.envelope(geometries)


def to_poly(geometries, designator: str, color: str, coordpoly=False):
    lines = [f"// {designator}"] if designator else []

    _render_polygon(lines, _get_geoms(geometries), color)

    if coordpoly:
        lines.append(f"COORDPOLY:{coordpoly}")
        lines.append("")

    return "\n".join(lines)


def _render_polygon(lines, polygons, color):
    for polygon in polygons:
        lines.append(f"COLOR:{color}")

        for point in polygon.coords:
            lines.append(f"COORD:{coord2es((point[0], point[1]))}")


def _render_coords(lines, linestring):
    for geometry in linestring:
        for point in geometry.coords:
            lines.append(f"COORD:{point[0]}:{point[1]}")

        lines.append("")


def _render_linestring(lines, linestring):
    for geometry in linestring:
        count = len(geometry.coords)

        for idx, point in enumerate(geometry.coords):
            if idx == count - 1:
                break

            lines.append(
                f"LINE:{coord2es((point[0], point[1]))}:{coord2es((geometry.coords[idx + 1][0], geometry.coords[idx + 1][1]))}"
            )
        lines.append("")


def simplify(geometries, tolerance):
    geo = _get_geoms(geometries)
    if isinstance(geo, list):
        return list(map(lambda geometry: shapely.simplify(geometry, tolerance), geo))
    else:
        return shapely.simplify(geo, tolerance)


def join_segments(lines):
    return shapely.ops.linemerge(_get_geoms(lines))


def coord2es(coord):
    return f"{coord[0]}:{coord[1]}"
