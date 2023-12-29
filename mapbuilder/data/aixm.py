from typing import Dict, List, Optional
from shapely import LineString, Polygon, LinearRing
from lxml import etree

AIXM_NAMESPACES = {
    "gss": "http://www.isotc211.org/2005/gss",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "message": "http://www.aixm.aero/schema/5.1.1/message",
    "gsr": "http://www.isotc211.org/2005/gsr",
    "gco": "http://www.isotc211.org/2005/gco",
    "gml": "http://www.opengis.net/gml/3.2",
    "gmd": "http://www.isotc211.org/2005/gmd",
    "aixm": "http://www.aixm.aero/schema/5.1.1",
    "xlink": "http://www.w3.org/1999/xlink",
    "gts": "http://www.isotc211.org/2005/gts",
    "gmx": "http://www.isotc211.org/2005/gmx",
}


class AIXMParser:
    result: Optional[Dict]
    taxiways: Dict

    def __init__(self, file):
        self.result = None
        self.taxiways = {}
        with open(file) as f:
            self.xml_root = etree.parse(f)

    def parse(self):
        self.build_twy_cache()

        self.result = {
            "guidance_line": self.parse_generic_geometries(
                '//aixm:GuidanceLineTimeSlice[aixm:type="TWY" or aixm:type="APRON" or aixm:type="GATE_TLANE" or aixm:type="LI_TLANE"]',
                "./aixm:designator/text()",
                False,
            ),
            "guidance_line_by_id": self.parse_generic_geometries(
                '//aixm:GuidanceLineTimeSlice[aixm:type="TWY" or aixm:type="APRON" or aixm:type="GATE_TLANE" or aixm:type="LI_TLANE"]',
                "../../gml:identifier/text()",
                False,
            ),
            "guidance_line_marking": self.parse_generic_geometries(
                "//aixm:GuidanceLineMarkingTimeSlice",
                "../../gml:identifier/text()",
                False,
            ),
            "runway_marking": self.parse_generic_geometries(
                '//aixm:RunwayMarkingTimeSlice[aixm:markingLocation="THR" or aixm:markingLocation="DESIG" or aixm:markingLocation="CL" or aixm:markingLocation="TDZ" or aixm:markingLocation="AIM"]',
                "../../gml:identifier/text()",
                False,
            ),
            "runway_element": self.parse_generic_geometries(
                "//aixm:RunwayElementTimeSlice", "../../gml:identifier/text()", True
            ),
            "runway_blast_pad": self.parse_generic_geometries(
                "//aixm:RunwayBlastPadTimeSlice", "../../gml:identifier/text()", True
            ),
            "runway_blast_pad_marking": self.parse_generic_geometries(
                '//aixm:RunwayMarkingTimeSlice[aixm:markingLocation="OTHER:PRE_THR"]',
                "../../gml:identifier/text()",
                True,
            ),
            "deicing_area": self.parse_generic_geometries(
                "//aixm:DeicingAreaTimeSlice", "../../gml:identifier/text()", True
            ),
            "taxi_holding_position": self.parse_generic_geometries(
                "//aixm:TaxiHoldingPositionMarkingTimeSlice",
                "../../gml:identifier/text()",
                False,
            ),
            "vertical_structure": self.parse_generic_geometries(
                '//aixm:VerticalStructureTimeSlice[aixm:type="BUILDING" or aixm:type="CONTROL_TOWER"]',
                "./aixm:name/text()",
                True,
            ),
        }

        self.parse_taxiway_markings(self.xml_root)

        return self.result

    @staticmethod
    def parse_pos_list(raw_geometry):
        """Parses geometries into lat/lon pairs"""
        geometry_parts = iter(raw_geometry.split(" "))

        geometry = []

        for geo in geometry_parts:
            x = float(geo)
            y = float(next(geometry_parts))
            geometry.append((x, y))

        return geometry

    def parse_generic_geometries(self, container_xpath: str, id_xpath: str, poly: bool):
        """Parses generic geometries"""
        elements = self.xml_root.xpath(container_xpath, namespaces=AIXM_NAMESPACES)
        result = {}

        for element in elements:
            designator = element.xpath(id_xpath, namespaces=AIXM_NAMESPACES)[0]
            raw_geometries = element.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES)

            for raw_geometry in raw_geometries:
                if poly:
                    geometry = LinearRing(self.parse_pos_list(raw_geometry))
                else:
                    geometry = LineString(self.parse_pos_list(raw_geometry))

                if designator not in result:
                    result[designator] = [geometry]
                else:
                    result[designator].append(geometry)

        return result

    @staticmethod
    def parse_guidance_lines(xml_root):
        segments = xml_root.xpath(
            '//aixm:GuidanceLineTimeSlice[aixm:type="TWY" or aixm:type="APRON" or aixm:type="GATE_TLANE" or aixm:type="LI_TLANE"]',
            namespaces=AIXM_NAMESPACES,
        )
        guidance_lines = {}

        for segment in segments:
            designator = segment.xpath("./aixm:designator/text()", namespaces=AIXM_NAMESPACES)[0]
            raw_geometry = segment.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES)[0]
            geometry = LineString(AIXMParser.parse_pos_list(raw_geometry))

            if designator not in guidance_lines:
                guidance_lines[designator] = [geometry]
            else:
                guidance_lines[designator].append(geometry)

        return guidance_lines

    @staticmethod
    def parse_guidance_line_markings(xml_root):
        segments = xml_root.xpath("//aixm:GuidanceLineMarkingTimeSlice", namespaces=AIXM_NAMESPACES)
        guidance_lines = {}

        for segment in segments:
            segment_id = segment.xpath("../../gml:identifier/text()", namespaces=AIXM_NAMESPACES)[0]
            raw_geometry = segment.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES)[0]
            geometry = LineString(AIXMParser.parse_pos_list(raw_geometry))

            guidance_lines[segment_id] = geometry
            # if segment_id not in guidance_lines:
            #    guidance_lines[segment_id] = [geometry]
            # else:
            #    guidance_lines[segment_id].append(geometry)

        return guidance_lines

    @staticmethod
    def parse_runway_elements(xml_root):
        segments = xml_root.xpath("//aixm:RunwayElementTimeSlice", namespaces=AIXM_NAMESPACES)
        guidance_lines = {}

        for segment in segments:
            segment_id = segment.xpath("../../gml:identifier/text()", namespaces=AIXM_NAMESPACES)[0]
            raw_geometry = segment.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES)[0]
            geometry = LineString(AIXMParser.parse_pos_list(raw_geometry))

            guidance_lines[segment_id] = [geometry]
            # if segment_id not in guidance_lines:
            #    guidance_lines[segment_id] = [geometry]
            # else:
            #    guidance_lines[segment_id].append(geometry)

        return guidance_lines

    @staticmethod
    def parse_deicing_areas(xml_root):
        segments = xml_root.xpath("//aixm:DeicingAreaTimeSlice", namespaces=AIXM_NAMESPACES)
        guidance_lines = {}

        for segment in segments:
            segment_id = segment.xpath("../../gml:identifier/text()", namespaces=AIXM_NAMESPACES)[0]
            raw_geometry = segment.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES)[0]
            geometry = LineString(AIXMParser.parse_pos_list(raw_geometry))

            guidance_lines[segment_id] = [geometry]
            # if segment_id not in guidance_lines:
            #    guidance_lines[segment_id] = [geometry]
            # else:
            #    guidance_lines[segment_id].append(geometry)

        return guidance_lines

    @staticmethod
    def parse_runway_markings(xml_root):
        segments = xml_root.xpath(
            '//aixm:RunwayMarkingTimeSlice[aixm:markingLocation="THR" or aixm:markingLocation="DESIG" or aixm:markingLocation="CL" or aixm:markingLocation="TDZ" or aixm:markingLocation="AIM"]',
            namespaces=AIXM_NAMESPACES,
        )
        guidance_lines = {}

        for segment in segments:
            segment_id = segment.xpath("../../gml:identifier/text()", namespaces=AIXM_NAMESPACES)[0]
            for raw_geometry in segment.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES):
                geometry = LineString(AIXMParser.parse_pos_list(raw_geometry))

                if segment_id not in guidance_lines:
                    guidance_lines[segment_id] = [geometry]
                else:
                    guidance_lines[segment_id].append(geometry)

        return guidance_lines

    @staticmethod
    def parse_vertical_structures(xml_root):
        structures = xml_root.xpath(
            '//aixm:VerticalStructureTimeSlice[aixm:type="BUILDING" or aixm:type="CONTROL_TOWER"]',
            namespaces=AIXM_NAMESPACES,
        )
        vertical_structures = {}

        for structure in structures:
            name = structure.xpath("./aixm:name/text()", namespaces=AIXM_NAMESPACES)[0]
            raw_geometry = structure.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES)[0]
            geometry = LinearRing(AIXMParser.parse_pos_list(raw_geometry))

            if name not in vertical_structures:
                vertical_structures[name] = [geometry]
            else:
                vertical_structures[name].append(geometry)

        return vertical_structures

    def parse_taxiway_markings(self, xml_root):
        segments = xml_root.xpath(
            '//aixm:TaxiwayMarkingTimeSlice[aixm:markingLocation="TWY_INT"]',
            namespaces=AIXM_NAMESPACES,
        )
        marking_lines = {}
        twy_mapping = {}

        for segment in segments:
            segment_id = segment.xpath("../../gml:identifier/text()", namespaces=AIXM_NAMESPACES)[0]
            # segment_id = segment.get(f"{{{AIXM_NAMESPACES['gml']}}}id")
            marked_twy_id = segment.xpath(
                "./aixm:markedTaxiway/@xlink:href", namespaces=AIXM_NAMESPACES
            )[0]
            designator = self.taxiways[marked_twy_id.replace("urn:uuid:", "")] or "unknown"

            raw_geometry = segment.xpath(".//gml:posList/text()", namespaces=AIXM_NAMESPACES)[0]
            geometry = LineString(self.parse_pos_list(raw_geometry))

            marking_lines[segment_id] = [geometry]

            if designator not in twy_mapping:
                twy_mapping[designator] = [segment_id]
            else:
                twy_mapping[designator].append(segment_id)

        assert self.result is not None
        self.result["taxiway_marking"] = marking_lines
        self.result["taxiway_marking_mapping"] = twy_mapping

    def build_twy_cache(self):
        taxiways = self.xml_root.xpath("//aixm:Taxiway", namespaces=AIXM_NAMESPACES)

        for taxiway in taxiways:
            uuid = taxiway.xpath(".//gml:identifier/text()", namespaces=AIXM_NAMESPACES)[0]
            designator = taxiway.xpath(
                ".//aixm:TaxiwayTimeSlice/aixm:designator/text()",
                namespaces=AIXM_NAMESPACES,
            )[0]

            self.taxiways[uuid] = designator

    @staticmethod
    def get_elements_by_identifier(identifier: str, xml_root):
        identifier = identifier.replace("urn:uuid:", "")  # evil hack, I know
        return xml_root.xpath(
            '//*[gml:identifier="' + identifier + '"]', namespaces=AIXM_NAMESPACES
        )

    @staticmethod
    def get_designator(element):
        return element.xpath(".//aixm:designator/text()", namespaces=AIXM_NAMESPACES)[0]
