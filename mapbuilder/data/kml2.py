import logging
from pathlib import Path
from typing import Any

from lxml import etree
from shapely import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from mapbuilder import MapbuilderException
from mapbuilder.data.feature import Feature

MULTI_TYPES = {Point: MultiPoint, LineString: MultiLineString, Polygon: MultiPolygon}


def parse_kml(file: Path, root: str | None = None) -> dict[str, Any]:
    """Parses a KML file into features for the Jinja feature API.

    The result mirrors the KML structure: folders become nested dicts, placemarks become lists of
    features under their name (names need not be unique). With ``root``, only the content of that
    top-level folder is returned.

    Coordinates are stored as (lat, lon), like all other data sources.
    """
    tree = etree.parse(file)
    result: dict[str, Any] = {}
    _parse_container(tree.getroot(), result, ())

    if root is not None:
        if root not in result:
            raise MapbuilderException(f"Root folder {root} not found", file=file)
        return result[root]

    return result


def _parse_container(el: etree._Element, result: dict[str, Any], path: tuple[str, ...]) -> None:
    for child in el:
        tag = _local(child)

        if tag == "Document":
            # Documents do not add a level, like in the legacy KML parser
            _parse_container(child, result, path)
        elif tag == "Folder":
            name = _text(child, "name") or ""
            if name in result:
                logging.warning(f"KML folder {'/'.join((*path, name))} clashes with another folder or placemark")
            folder = result[name] = {}
            _parse_container(child, folder, (*path, name))
        elif tag == "Placemark":
            feature = _placemark(child, path)
            if feature is not None:
                placemarks = result.setdefault(feature.properties["name"], [])
                if not isinstance(placemarks, list):
                    logging.warning(f"KML placemark {_describe(feature)} clashes with a folder, skipping it")
                else:
                    placemarks.append(feature)


def _placemark(el: etree._Element, path: tuple[str, ...]) -> Feature | None:
    name = _text(el, "name") or ""
    properties: dict[str, Any] = {"name": name, "folder": "/".join(path)}

    for prop in ("description", "styleUrl"):
        value = _text(el, prop)
        if value is not None:
            properties[prop] = value

    properties.update(_extended_data(el))

    feature_id = el.get("id") or name
    geometries = [geometry for child in el if (geometry := _geometry(child, feature_id)) is not None]
    if not geometries:
        logging.warning(f"KML placemark {'/'.join((*path, name))} has no geometry, skipping it")
        return None

    geometry = geometries[0] if len(geometries) == 1 else _collect(geometries)
    return Feature(feature_id, "Placemark", properties, geometry)


def _extended_data(el: etree._Element) -> dict[str, str]:
    """Reads <Data name><value> and <SchemaData><SimpleData name> entries."""
    data = {}
    for child in el.iter():
        tag = _local(child)
        if tag == "Data" and child.get("name"):
            data[child.get("name")] = _text(child, "value") or ""
        elif tag == "SimpleData" and child.get("name"):
            data[child.get("name")] = (child.text or "").strip()
    return data


def _geometry(el: etree._Element, feature_id: str) -> BaseGeometry | None:
    tag = _local(el)

    try:
        if tag == "Point":
            return Point(_coordinates(el)[0])
        if tag == "LineString":
            return LineString(_coordinates(el))
        if tag == "LinearRing":
            return LinearRing(_coordinates(el))
        if tag == "Polygon":
            return _polygon(el)
        if tag == "MultiGeometry":
            parts = [geometry for child in el if (geometry := _geometry(child, feature_id)) is not None]
            return _collect(parts) if parts else None
    except (MapbuilderException, ValueError, IndexError) as e:
        logging.warning(f"Skipping invalid {tag} of KML placemark {feature_id}: {e}")

    return None


def _polygon(el: etree._Element) -> Polygon:
    outer = _find(el, "outerBoundaryIs")
    if outer is None:
        msg = "Polygon without outerBoundaryIs"
        raise MapbuilderException(msg)

    inners = [_coordinates(inner) for inner in el if _local(inner) == "innerBoundaryIs"]
    return Polygon(_coordinates(outer), inners)


def _coordinates(el: etree._Element) -> list[tuple[float, float]]:
    """Reads the (first nested) <coordinates> as (lat, lon) tuples; KML stores lon,lat[,alt]."""
    coordinates = next((child for child in el.iter() if _local(child) == "coordinates"), None)
    if coordinates is None or not (coordinates.text or "").strip():
        raise MapbuilderException(f"{_local(el)} without coordinates")

    result = []
    for tuple_str in coordinates.text.split():
        values = tuple_str.split(",")
        result.append((float(values[1]), float(values[0])))
    return result


def _collect(geometries: list[BaseGeometry]) -> BaseGeometry:
    """Combines geometries into a multi-geometry if they share a type, otherwise into a collection."""
    kinds = {type(geometry) for geometry in geometries}
    if len(kinds) == 1 and (multi := MULTI_TYPES.get(kinds.pop())) is not None:
        return multi(geometries)
    return GeometryCollection(geometries)


def _find(el: etree._Element, tag: str) -> etree._Element | None:
    return next((child for child in el if _local(child) == tag), None)


def _text(el: etree._Element, tag: str) -> str | None:
    child = _find(el, tag)
    return child.text.strip() if child is not None and child.text is not None else None


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _describe(feature: Feature) -> str:
    return "/".join(filter(None, (feature.properties["folder"], feature.properties["name"])))
