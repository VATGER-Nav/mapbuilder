---
icon: lucide/database
---

# Data and features

Templates read their data from the data sources defined in the `[data]` section of
`mapbuilder.toml`. Each source is available in templates as `data.<name>`.

## What is a feature?

A **feature** is a geometry together with its properties, for example a guidance line with its
designator, or a stand with its designator and apron. Every feature has:

| Field | Description |
|---|---|
| `id` | Identifier, e.g. the AIXM UUID, the GeoPackage ID or the KML placemark name |
| `type` | Kind of feature, e.g. `GuidanceLine`, the GeoPackage layer name or `Placemark` |
| `properties` | Dict of properties, e.g. `feature.properties.designator` |
| `geometry` | The geometry: point, line, polygon, or a multi-part geometry |

Geometries can be multi-part: a feature can consist of several polygons or lines. The renderers
draw every part.

In templates, you can read properties directly:

```jinja
{% for stand in data.eddm['AircraftStand'] if stand.properties.type == 'NI' %}
    {{- stand | render_symbol('stand', prop='designator') }}
{% endfor %}
```

!!! info "Coordinates"

    All data sources store coordinates as *latitude, longitude*, and all renderers write them in this
    order, matching the GRP and TopSky formats.

## Data source types

These source types produce features for the Feature API:

| `type` | Source | Template access |
|---|---|---|
| `aixm51` | AIXM 5.1 AerodromeMapping data | `data.eddm['GuidanceLine']`, `data.eddm.group(…)` |
| `gpkg` | GeoPackage layers | `data.eddm_stands['EDDM-stands']['101']` |
| `geojson` | GeoJSON files | `data.mva['487']` |
| `kml2` | KML files | `data.eddp_kml['Construction']['M']` |

Data from `aixm2` sources also works with the Feature API. The older `aixm` and `kml` types are meant
for the [older filters](migration.md#data-sources).

### AIXM 5.1 (`aixm51`)

```toml title="mapbuilder.toml"
[data.eddm]
type = "aixm51"
source = "dfs:0:EDDM AerodromeMapping:AIXM 5.1.1"  # or a path or URL to an AIXM file
```

Features are grouped by AIXM feature type:

```jinja
{{ data.eddm['RunwayBlastPad'] | render_grp(area='OTHER:REGION') }}
```

The source offers some helpers:

`group(feature_type, prop, via=None)`
:   Groups the features of a type by a property value, e.g.
    `data.eddm.group('GuidanceLine', 'designator')['C1']`. With `via`, the property is read from a
    *linked* feature instead: `data.eddm.group('TaxiwayMarking', 'designator', via='markedTaxiway')`
    groups taxiway markings by the designator of the taxiway they mark. Features without the property
    are left out.

`find(id)`
:   Returns the features with an AIXM UUID, e.g.
    `data.eddm.find('9684c696-6119-c04e-ee05-315baa8c084d')`. Logs a warning if it does not exist.

`resolve(ref)`
:   Returns the feature a link points to, e.g. `data.eddm.resolve(stand.links.apronLocation)`.

Properties are named as in AIXM, e.g. `designator`, `type`, `markingLocation` or `colour`. Links to
other features are available in `feature.links`.

??? note "Features with several geometries"

    Some AIXM features consist of several parts with their own geometry, such as the individual
    elements of a taxiway marking. Each part becomes its own feature with the same `id`, the
    properties of the whole feature plus those of the part.

    If a feature has several geometric properties, they are combined into one geometry, and are
    also available by name. Use [`feat_select_geometry`](filters.md#feat_select_geometry) to pick
    one of them.

### GeoPackage (`gpkg`)

```toml title="mapbuilder.toml"
[data.eddm_stands]
type = "gpkg"
source = "gis/EDDM-stands.gpkg"
layers = ["EDDM-stands"]      # optional, defaults to all layers in the file
id_property = "designator"   # optional, defaults to the GeoPackage feature ID
```

Each layer is a dict of features by ID. The ID comes from `id_property` if set, otherwise it is
the feature ID as a string (`'1'`, `'2'`, …):

```jinja
{% set stands = data.eddm_stands['EDDM-stands'] %}
STAND:EDDM:101
{{ stands['101'] | render_coords }}

{# all features of a layer #}
{{ data.eddm_gis['aprons'] | render_area('OTHER:REGION') }}
```

The feature `type` is the layer name, its properties are the columns of the layer, and
`feat_where('id', …)` matches the `id_property` value.

!!! warning "Coordinate system and IDs"

    Layers must use WGS 84 (EPSG:4326); other coordinate systems stop the build with an error.
    If several features of a layer share an ID, the last one is used and a warning is logged.

### GeoJSON (`geojson`)

```toml title="mapbuilder.toml"
[data.mva]
type = "geojson"
source = "dfs:1:ED MVA:GeoJSON"   # or a path or URL to a GeoJSON file
id_property = "IDENT"             # optional
```

The source is a dict of features by ID. The ID comes from `id_property` if set, otherwise from the
`id` of each feature, or its position in the file (`'1'`, `'2'`, …) if it has none.

```jinja
{{ data.mva['487'] | render_coordline('MVA 487') }}

{% for area in data.mva.values() if area.properties.LEVEL == 'LOWER' %}
    {{- area | render_coordline(area.properties.NAME) }}
{% endfor %}
```

The properties are the `properties` of each GeoJSON feature. The feature `type` is the `name` of
the FeatureCollection if the file has one. Files containing a single feature or a bare geometry are
loaded as a dict with one feature.

!!! warning "Coordinate system and IDs"

    GeoJSON coordinates are always WGS 84 (EPSG:4326); files declaring another coordinate system
    stop the build with an error. If several features share an ID, the last one is used and a
    warning is logged.

### KML (`kml2`)

```toml title="mapbuilder.toml"
[data.eddp_kml]
type = "kml2"
source = "kml/EDDP.kml"
root = "EDDP"   # optional: only use the content of this top-level folder
```

The KML structure is kept: folders become dicts, and each placemark name maps to a **list** of
features, because names do not have to be unique.

```jinja
{{ data.eddp_kml['Construction']['M'] | render_area('TWYCLOSED:REGION') }}

{# a whole folder at once #}
{{ data.eddp_kml['Construction'] | render_grp(area='TWYCLOSED:REGION', symbol='CROSS') }}
```

Each placemark feature has these properties:

| Property | Content |
|---|---|
| `name` | Placemark name |
| `folder` | Folder path, e.g. `EDDP/Construction` |
| `description`, `styleUrl` | If set in the KML |
| *ExtendedData* | Every `<Data>` and `<SimpleData>` entry by its name |

Points, lines, polygons (including holes) and multi-geometries are supported. Placemarks without a
valid geometry are skipped with a warning. A `root` folder that does not exist stops the build.
