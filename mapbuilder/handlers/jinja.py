from pathlib import Path

from jinja2 import Environment, FileSystemLoader
import shapely, shapely.ops
from pygeodesy import ellipsoidalVincenty as ev


class JinjaHandler:
    def handle(self, item: Path, data) -> str:
        file_loader = FileSystemLoader(item.parent)
        jinja_env = Environment(loader=file_loader)
        jinja_env.globals.update(data=data)
        jinja_env.filters.update(
            simplify=simplify,
            to_line=to_line,
            to_coordline=to_coordline,
            to_poly=to_poly,
            join_segments=join_segments,
            filter_smaller_than=filter_smaller_than,
            envelope=envelope,
            to_text=to_text,
        )

        return jinja_env.get_template(item.name).render()


def draw_ecl(threshold, length, bearing, fap, marker_style, markers):
    pass


def to_text(geometry, label: str):
    if isinstance(geometry, list):
        point = geometry[0]
    else:
        point = geometry

    if point is None:
        return ""

    labeltext, _, _ = label.partition("#")
    return f"TEXT:{coord2es(point.coords[0])}:{labeltext}"


def to_line(geometries, designator: str):
    lines = [f"// {designator}"] if designator else []

    if isinstance(geometries, list):
        _render_linestring(lines, geometries)
    elif isinstance(geometries, shapely.MultiLineString):
        _render_linestring(lines, geometries.geoms)
    elif isinstance(geometries, shapely.LineString):
        _render_linestring(lines, [geometries])

    return "\n".join(lines)


def to_coordline(geometries, designator: str):
    lines = [f"// {designator}"] if designator else []

    if isinstance(geometries, list):
        _render_coords(lines, geometries)
    elif isinstance(geometries, shapely.MultiLineString):
        _render_coords(lines, geometries.geoms)
    elif isinstance(geometries, shapely.LineString):
        _render_coords(lines, [geometries])

    lines.append("COORDLINE")
    lines.append("")
    return "\n".join(lines)


def filter_smaller_than(geometries, threshold):
    if isinstance(geometries, list):
        return list(filter(lambda geometry: geometry.envelope.area >= threshold, geometries))


def envelope(geometries):
    return shapely.envelope(geometries)


def to_poly(geometries, designator: str, color: str, coordpoly=False):
    lines = [f"// {designator}"] if designator else []

    if isinstance(geometries, list):
        _render_polygon(lines, geometries, color)
    elif isinstance(geometries, shapely.LinearRing):
        _render_polygon(lines, [geometries], color)

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
    if isinstance(geometries, list):
        return list(map(lambda geometry: shapely.simplify(geometry, tolerance), geometries))
    else:
        return shapely.simplify(geometries, tolerance)


def join_segments(lines):
    return shapely.ops.linemerge(lines)


def decimal_to_dms(decimal, direction):
    degrees = int(decimal)
    minutes = int((decimal - degrees) * 60)
    seconds = round(((decimal - degrees) * 60 - minutes) * 60, 2)
    return f"{direction}{degrees:03d}.{minutes:02d}.{seconds:06.3f}"


def coord2es_old(tuple):
    lat = decimal_to_dms(tuple[0], "N" if tuple[0] >= 0 else "S")
    lon = decimal_to_dms(tuple[1], "E" if tuple[1] >= 1 else "W")
    return f"{lat}:{lon}"


def coord2es(tuple):
    lat = tuple[0]
    lon = tuple[1]
    return f"{lat}:{lon}"
