from pathlib import Path

import fiona
from shapely.geometry import shape
from shapely.ops import transform

from mapbuilder import MapbuilderException
from mapbuilder.data.feature import Feature


def swap_xy(x, y, z=None):
    return (y, x) if z is None else (y, x, z)


def parse_gpkg(filename: Path, layers: list[str], id_property: str | None) -> dict:
    """Parse GeoPackage file and return data for specified layers.

    Args:
        filename (Path): Path to the GeoPackage file.
        layers (list[str]): List of layer names to parse.
        id_property (str, optional): Name of the ID property. Defaults to "fid".

    Returns:
        dict: Dictionary mapping layer names to their features by ID.
    """
    data = {}
    for layer in layers:
        data[layer] = {}
        with fiona.open(filename, "r", layer=layer) as source:
            for feature in source:
                try:
                    feature_id = feature.id if not id_property else feature.properties[id_property]

                    if not feature_id:
                        raise MapbuilderException(f"Feature {feature} is missing ID", file=filename)
                except KeyError as e:
                    raise MapbuilderException(f"Feature {feature} is missing ID", file=filename) from e

                geometry = None
                if feature.geometry is not None:
                    geometry = transform(lambda x, y, z=None: swap_xy(x, y, z), shape(feature.geometry))

                data[layer][feature_id] = Feature(str(feature_id), layer, dict(feature.properties), geometry)
    return data
