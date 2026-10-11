from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from shapely import GeometryCollection
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True, slots=True, eq=False)
class Feature:
    """A geometry with properties.

    Features are immutable, as the loaded data is shared across all templates.
    Filters derive new features with :meth:`with_geometry` instead.
    """

    id: str | None
    type: str | None
    properties: Mapping[str, Any]
    geometry: BaseGeometry | None
    links: Mapping[str, Any] = field(default_factory=dict)
    # Named geometric properties (AIXM); only set on features as loaded from a data source
    geometries: Mapping[str, BaseGeometry] = field(default_factory=dict)
    part: int | None = None
    # IDs of the features this one was merged from (join/union)
    merged_from: tuple[str, ...] = ()

    @classmethod
    def from_geometries(cls, id: str | None, type: str | None, properties: Mapping[str, Any],
                        geometries: Mapping[str, BaseGeometry], **kwargs) -> "Feature":
        """Creates a feature from named geometries; several are combined into a GeometryCollection."""
        if not geometries:
            geometry = None
        elif len(geometries) == 1:
            geometry = next(iter(geometries.values()))
        else:
            geometry = GeometryCollection(list(geometries.values()))

        return cls(id, type, properties, geometry, geometries=geometries, **kwargs)

    def with_geometry(self, geometry: BaseGeometry | None) -> "Feature":
        """Returns a copy with a derived geometry. Named geometries no longer apply and are dropped."""
        return replace(self, geometry=geometry, geometries={})

    def __repr__(self) -> str:
        geometry = self.geometry.geom_type if self.geometry is not None else None
        return f"Feature({self.type} {self.id}, {geometry})"
