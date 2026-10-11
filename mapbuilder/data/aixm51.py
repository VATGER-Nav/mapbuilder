import logging
from collections import UserDict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from lxml import etree
from pygeodesy import ellipsoidalExact as geo_model
from shapely import GeometryCollection, LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from mapbuilder import MapbuilderException
from mapbuilder.data.feature import Feature

GML = "http://www.opengis.net/gml/3.2"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"

POINT_TAGS = {"Point", "ElevatedPoint"}
CURVE_TAGS = {"Curve", "ElevatedCurve", "LineString"}
SURFACE_TAGS = {"Surface", "ElevatedSurface", "Polygon"}
GEOMETRY_TAGS = POINT_TAGS | CURVE_TAGS | SURFACE_TAGS

# TimeSlice bookkeeping that is not useful as feature properties
SKIPPED_PROPERTIES = {"interpretation", "sequenceNumber", "correctionNumber", "timeSliceMetadata", "featureLifetime"}

# Uncommitted TimeSlice interpretations (TEMPDELTA, PERMDELTA) are not applied.
USABLE_INTERPRETATIONS = {"BASELINE", "SNAPSHOT"}

UOM_TO_METERS = {"M": 1.0, "KM": 1000.0, "NM": 1852.0, "[nmi_i]": 1852.0, "FT": 0.3048, "[ft_i]": 0.3048}
CIRCLE_SEGMENTS = 72


class AIXMDataset(UserDict[str, list[Feature]]):
    """Features grouped by AIXM feature type, e.g. ``dataset["TaxiwayElement"]``."""

    def __init__(self) -> None:
        super().__init__()
        # Base feature per id (properties and links, but possibly no geometry)
        self.by_id: dict[str, Feature] = {}
        # Renderable features per id, i.e. the base feature or its geometric parts
        self.parts_by_id: dict[str, list[Feature]] = {}
        self._groups: dict[tuple[str, str, str | None], dict[Any, list[Feature]]] = {}

    def resolve(self, ref: str | None) -> Feature | None:
        """Returns the feature an xlink reference (as stored in ``Feature.links``) points to."""
        return self.by_id.get(ref) if ref else None

    def find(self, feature_id: str) -> list[Feature]:
        """Returns the renderable features (the feature itself or all its parts) for an id."""
        if feature_id not in self.parts_by_id:
            logging.warning(f"AIXM feature {feature_id} not found")
            return []
        return self.parts_by_id[feature_id]

    def group(self, feature_type: str, prop: str, via: str | None = None) -> dict[Any, list[Feature]]:
        """Groups the features of a type by a property, e.g. ``group("GuidanceLine", "designator")``.

        With ``via``, the property is read from the feature referenced by that link instead, e.g.
        ``group("TaxiwayMarking", "designator", via="markedTaxiway")``. Features lacking the
        property are left out; groups keep document order.
        """
        key = (feature_type, prop, via)
        if key not in self._groups:
            groups: dict[Any, list[Feature]] = {}
            for feature in self.get(feature_type, []):
                source = self.resolve(feature.links.get(via)) if via else feature
                value = source.properties.get(prop) if source else None
                if value is not None:
                    groups.setdefault(value, []).append(feature)
            self._groups[key] = groups

        return self._groups[key]


@dataclass(slots=True)
class _Object:
    properties: dict[str, Any] = field(default_factory=dict)
    links: dict[str, Any] = field(default_factory=dict)
    geometries: dict[str, BaseGeometry] = field(default_factory=dict)
    parts: list["_Object"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _CRS:
    lon_lat: bool = False
    dimension: int = 2

    def child(self, el: etree._Element) -> "_CRS":
        """Returns the CRS in effect for el, honoring srsName/srsDimension overrides."""
        name = el.get("srsName")
        dimension = el.get("srsDimension")
        if name is None and dimension is None:
            return self
        return _CRS(
            lon_lat=_is_lon_lat(name) if name is not None else self.lon_lat,
            dimension=int(dimension) if dimension is not None else self.dimension,
        )


def _is_lon_lat(srs_name: str) -> bool:
    if "CRS84" in srs_name:
        return True
    if srs_name.endswith(("4326", "4258")):
        return False
    raise MapbuilderException(f"Unsupported CRS {srs_name}")


def parse_aixm(source: Path | str, at: datetime | None = None) -> AIXMDataset:
    """Parses an AIXM 5.1(.1) message file.

    :param source: Path to the AIXM XML file
    :param at: If given, only TimeSlices valid at this (timezone-aware) instant are considered and
        features whose lifetime ended before it are dropped. Otherwise the latest BASELINE/SNAPSHOT
        TimeSlice of each feature is used.
    """
    dataset = AIXMDataset()
    context = etree.iterparse(
        str(source),
        events=("end",),
        tag="{*}hasMember",
        huge_tree=True,
        resolve_entities=False,
        no_network=True,
    )

    for _, member in context:
        feature_el = next(_children(member), None)
        if feature_el is not None:
            _add_feature(dataset, feature_el, at)

        # Free already processed members, elem.clear() alone keeps empty elements around
        member.clear(keep_tail=False)
        while member.getprevious() is not None:
            del member.getparent()[0]

    return dataset


def _add_feature(dataset: AIXMDataset, feature_el: etree._Element, at: datetime | None) -> None:
    feature_type = _local(feature_el)
    feature_id = feature_el.findtext(f"{{{GML}}}identifier") or feature_el.get(f"{{{GML}}}id")
    if not feature_id:
        logging.warning(f"Skipping {feature_type} without identifier")
        return

    timeslice = _select_timeslice(feature_el, at)
    if timeslice is None:
        return

    try:
        obj = _read_object(timeslice, _CRS())
    except (MapbuilderException, ValueError, IndexError) as e:
        logging.warning(f"Skipping {feature_type} {feature_id}: {e}")
        return

    base = Feature.from_geometries(feature_id, feature_type, obj.properties, obj.geometries, links=obj.links)
    dataset.by_id[feature_id] = base
    emitted = dataset.parts_by_id[feature_id] = []

    if obj.geometries or not obj.parts:
        emitted.append(base)

    for idx, part in enumerate(_geometric_parts(obj)):
        emitted.append(
            Feature.from_geometries(
                feature_id,
                feature_type,
                {**obj.properties, **part.properties},
                part.geometries,
                links={**obj.links, **part.links},
                part=idx,
            ),
        )

    dataset.setdefault(feature_type, []).extend(emitted)


def _geometric_parts(obj: _Object) -> Iterator[_Object]:
    """Yields all (nested) parts carrying geometry, with properties of intermediate parts merged in."""
    for part in obj.parts:
        if part.geometries:
            yield part
        for sub in _geometric_parts(part):
            yield _Object({**part.properties, **sub.properties}, {**part.links, **sub.links}, sub.geometries)


def _select_timeslice(feature_el: etree._Element, at: datetime | None) -> etree._Element | None:
    best = None
    best_key = (-1, -1)

    for ts_prop in feature_el.iterfind("{*}timeSlice"):
        timeslice = next(_children(ts_prop), None)
        if timeslice is None or timeslice.findtext("{*}interpretation") not in USABLE_INTERPRETATIONS:
            continue
        if at is not None and not _valid_at(timeslice, at):
            continue

        key = (int(timeslice.findtext("{*}sequenceNumber") or 0), int(timeslice.findtext("{*}correctionNumber") or 0))
        if key > best_key:
            best, best_key = timeslice, key

    return best


def _valid_at(timeslice: etree._Element, at: datetime) -> bool:
    period = timeslice.find(f"{{{GML}}}validTime/{{{GML}}}TimePeriod")
    if period is not None and not _in_period(period, at):
        return False

    lifetime = timeslice.find(f"{{*}}featureLifetime/{{{GML}}}TimePeriod")
    return lifetime is None or _in_period(lifetime, at)


def _in_period(period: etree._Element, at: datetime) -> bool:
    begin = period.findtext(f"{{{GML}}}beginPosition")
    end = period.findtext(f"{{{GML}}}endPosition")
    if begin and at < datetime.fromisoformat(begin):
        return False
    return not end or at < datetime.fromisoformat(end)


def _read_object(el: etree._Element, crs: _CRS) -> _Object:
    """Converts an AIXM object (TimeSlice or nested object) into properties, links, geometries and parts."""
    obj = _Object()

    for prop in _children(el):
        name = _local(prop)
        if name in SKIPPED_PROPERTIES or etree.QName(prop).namespace == GML:
            continue

        href = prop.get(XLINK_HREF)
        if href is not None:
            _put(obj.links, name, _ref_id(href))
            continue

        if prop.get(XSI_NIL) == "true":
            continue

        value = next(_children(prop), None)
        if value is None:
            if prop.text and prop.text.strip():
                _put(obj.properties, name, prop.text.strip())
        elif _local(value) in GEOMETRY_TAGS:
            geometry = _geometry(value, crs)
            existing = obj.geometries.get(name)
            obj.geometries[name] = geometry if existing is None else GeometryCollection([existing, geometry])
        else:
            sub = _read_object(value, crs)
            if sub.geometries or sub.parts:
                obj.parts.append(sub)
            elif sub.properties or sub.links:
                _put(obj.properties, name, {**sub.properties, **sub.links})

    return obj


def _ref_id(href: str) -> str:
    """Normalises xlink references (urn:uuid:…, #uuid.…, #local-id) to the bare id."""
    if href.startswith("urn:uuid:"):
        return href[9:]
    if href.startswith("#uuid."):
        return href[6:]
    return href.removeprefix("#")


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    """Sets a property, collecting repeated properties into a list."""
    if key not in target:
        target[key] = value
    elif isinstance(target[key], list):
        target[key].append(value)
    else:
        target[key] = [target[key], value]


def _geometry(el: etree._Element, crs: _CRS) -> BaseGeometry:
    crs = crs.child(el)
    tag = _local(el)

    if tag in POINT_TAGS:
        return Point(_positions(el, crs)[0])
    if tag in CURVE_TAGS:
        return LineString(_curve(el, crs))
    if tag in SURFACE_TAGS:
        return _surface(el, crs)

    raise MapbuilderException(f"Unsupported geometry {tag}")


def _positions(el: etree._Element, crs: _CRS) -> list[tuple[float, float]]:
    """Reads a gml:posList or a sequence of gml:pos children as (lat, lon) tuples."""
    pos_list = el.find(f"{{{GML}}}posList")
    if pos_list is not None:
        dimension = int(pos_list.get("srsDimension") or crs.dimension)
        values = [float(v) for v in (pos_list.text or "").split()]
        if len(values) % dimension:
            raise MapbuilderException(f"posList length {len(values)} does not match dimension {dimension}")
        coords = [(values[i], values[i + 1]) for i in range(0, len(values), dimension)]
    else:
        coords = []
        for pos in el.iterfind(f"{{{GML}}}pos"):
            parts = (pos.text or "").split()
            coords.append((float(parts[0]), float(parts[1])))

    if not coords:
        raise MapbuilderException(f"No coordinates in {_local(el)}")

    return [(y, x) for x, y in coords] if crs.lon_lat else coords


def _curve(el: etree._Element, crs: _CRS) -> list[tuple[float, float]]:
    """Concatenates the segments of a gml:Curve (or reads a gml:LineString)."""
    if _local(el) == "LineString":
        return _positions(el, crs)

    segments = el.find(f"{{{GML}}}segments")
    if segments is None:
        msg = "Curve without segments"
        raise MapbuilderException(msg)

    coords: list[tuple[float, float]] = []
    for segment in _children(segments):
        _extend(coords, _segment(segment, crs.child(segment)))

    return coords


def _segment(segment: etree._Element, crs: _CRS) -> list[tuple[float, float]]:
    tag = _local(segment)

    if tag in {"LineStringSegment", "GeodesicString", "Geodesic"}:
        return _positions(segment, crs)
    if tag == "CircleByCenterPoint":
        return _circle(segment, crs)

    # Arcs need a defined angle convention which is not settled for the data we consume - fail loudly.
    raise MapbuilderException(f"Unsupported curve segment {tag}")


def _circle(segment: etree._Element, crs: _CRS) -> list[tuple[float, float]]:
    lat, lon = _positions(segment, crs)[0]
    radius_el = segment.find(f"{{{GML}}}radius")
    if radius_el is None or radius_el.text is None:
        msg = "CircleByCenterPoint without radius"
        raise MapbuilderException(msg)

    uom = radius_el.get("uom", "M")
    if uom not in UOM_TO_METERS:
        raise MapbuilderException(f"Unsupported radius unit {uom}")

    radius = float(radius_el.text) * UOM_TO_METERS[uom]
    center = geo_model.LatLon(lat, lon)
    points = [center.destination(radius, 360 * i / CIRCLE_SEGMENTS) for i in range(CIRCLE_SEGMENTS)]
    coords = [(p.lat, p.lon) for p in points]
    return [*coords, coords[0]]


def _ring(el: etree._Element, crs: _CRS) -> list[tuple[float, float]]:
    """Reads a gml:LinearRing or a gml:Ring composed of curve members, closing it if necessary."""
    crs = crs.child(el)

    if _local(el) == "LinearRing":
        coords = _positions(el, crs)
    else:
        coords = []
        for member in el.iterfind(f"{{{GML}}}curveMember"):
            curve = next(_children(member), None)
            if curve is None:
                msg = "Empty curveMember"
                raise MapbuilderException(msg)
            _extend(coords, _curve(curve, crs.child(curve)))

    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])

    return coords


def _surface(el: etree._Element, crs: _CRS) -> Polygon | MultiPolygon:
    if _local(el) == "Polygon":
        patches = [el]
    else:
        patches_el = el.find(f"{{{GML}}}patches")
        if patches_el is None:
            msg = "Surface without patches"
            raise MapbuilderException(msg)
        patches = list(_children(patches_el))

    polygons = []
    for patch in patches:
        exterior = patch.find(f"{{{GML}}}exterior")
        if exterior is None or len(exterior) == 0:
            msg = "Polygon without exterior"
            raise MapbuilderException(msg)

        polygons.append(
            Polygon(
                _ring(exterior[0], crs),
                [_ring(interior[0], crs) for interior in patch.iterfind(f"{{{GML}}}interior")],
            ),
        )

    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def _extend(coords: list[tuple[float, float]], segment: list[tuple[float, float]]) -> None:
    """Appends segment coordinates, dropping the shared vertex between consecutive segments."""
    if coords and segment and coords[-1] == segment[0]:
        segment = segment[1:]
    coords.extend(segment)


def _children(el: etree._Element) -> Iterator[etree._Element]:
    """Element children, skipping comments and processing instructions."""
    return (child for child in el if isinstance(child.tag, str))


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname
