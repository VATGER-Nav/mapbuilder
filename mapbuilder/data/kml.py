from typing import Dict, Optional
import xmltodict
from shapely import LineString, LinearRing, Point


class KMLParser:
    result: Optional[Dict]

    def __init__(self, file, root):
        self.result = None
        self.root = root
        with open(file, "rb") as f:
            self.xml_root = xmltodict.parse(f)

    @staticmethod
    def parse_pos_list(raw_geometry):
        parts = raw_geometry.split(" ")

        geometries = []

        for part in parts:
            raw_coord = part.split(",")
            geometries.append((float(raw_coord[1]), float(raw_coord[0])))

        return geometries

    def parse(self):
        result = {}
        self.parse_recursively(self.xml_root["kml"]["Document"], result)
        self.result = result
        if self.root is not None and self.root in self.result:
            self.result = self.result[self.root]
        return self.result

    def parse_recursively(self, root, result):
        if "Folder" in root:
            for folder in ensure_list(root["Folder"]):
                name = folder["name"]
                result[name] = {}
                self.parse_recursively(folder, result[name])

        if "Placemark" in root:
            for placemark in ensure_list(root["Placemark"]):
                if "LineString" in placemark:
                    geom = LineString(self.parse_pos_list(placemark["LineString"]["coordinates"]))
                elif "Polygon" in placemark:
                    geom = LinearRing(
                        self.parse_pos_list(
                            placemark["Polygon"]["outerBoundaryIs"]["LinearRing"]["coordinates"]
                        )
                    )
                elif "Point" in placemark:
                    geom = Point(self.parse_pos_list(placemark["Point"]["coordinates"]))
                else:
                    raise ValueError("Placemark {placemark} unknown")

                name = placemark["name"]
                if name not in result:
                    result[name] = [geom]
                else:
                    result[name].append(geom)


def ensure_list(thing):
    if isinstance(thing, list):
        return thing
    else:
        return [thing]
