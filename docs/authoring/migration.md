---
icon: lucide/arrow-right-left
---

# Migrating templates

Templates written for earlier versions of mapbuilder keep working. This page shows how to move them to
the Feature API and what changes in the output.

## Renamed filters

Some Feature API filters had different names during development. The old names still work, but log a
deprecation warning once per run:

| Old name | New name |
|---|---|
| `geom_simplify` | [`feat_simplify`](filters.md#feat_simplify) |
| `geom_join` | [`feat_join`](filters.md#feat_join) |
| `geom_filter_min_area` | [`feat_min_area`](filters.md#feat_min_area) |
| `feat_exclude_property` | [`feat_exclude`](filters.md#feat_exclude) |
| `geom_raw_coords` | [`render_coords`](rendering.md#render_coords) or [`render_area`](rendering.md#render_area) |

The `geom_raw_coords` loop is replaced by a single filter:

=== "Before"

    ```jinja
    STAND:EDDN:01
    {%- for c in (s['01'] | geom_raw_coords)[0] %}
        {{ c -}}
    {% endfor %}
    ```

=== "After"

    ```jinja
    STAND:EDDN:01
    {{ s['01'] | render_coords }}
    ```

## Older filters

| Older filter | Feature API |
|---|---|
| `simplify` | [`feat_simplify`](filters.md#feat_simplify) |
| `join_segments` | [`feat_join`](filters.md#feat_join) |
| `geoms` | not needed: filters work on features directly |
| `filter_smaller_than` | [`feat_min_area`](filters.md#feat_min_area) (see below) |
| `combine` | [`feat_union`](filters.md#feat_union) |
| `to_line` | [`render_line`](rendering.md#render_line) |
| `to_poly(name, color)` | [`render_area('OTHER:REGION', name, color=color)`](rendering.md#render_area) |
| `to_poly(name, color, fill)` | [`render_coordpoly(fill, name, color)`](rendering.md#render_coordpoly) |
| `to_coordline` | [`render_coordline`](rendering.md#render_coordline) |
| `to_symbol` | [`render_symbol`](rendering.md#render_symbol) |
| `to_text` | [`render_text`](rendering.md#render_text) |
| `to_text_buffer(name, color, True)` | [`feat_text_box(text=name)`](filters.md#feat_text_box) + `render_area('OTHER:REGION', color=color)` |

Differences to be aware of:

- `filter_smaller_than` compared the area of the *bounding box*, so it also kept long lines.
  `feat_min_area` uses the real area and always drops lines.
- `to_coordline` and `to_poly` with a fill wrote a single `COORDLINE` or `COORDPOLY` after *all*
  lines or polygons, so TopSky connected them into one shape. The new renderers end every line and
  polygon separately. Maps with several lines or polygons per call will look different, as intended.
- `render_line` also draws the holes of polygons; `to_line` did not.
- `render_text` and `render_symbol` [clean up labels](rendering.md#symbols-and-text): they cut off
  everything from `#` like `to_text` did, and also replace colons.

### Mixed geometry types

Templates often check the geometry type to choose a renderer. `render_grp` and `render_ts` do this for
you:

=== "Before"

    ```jinja
    {% for name, geom in data.rivers.items() %}
        {% if geom[0].__class__.__name__ == 'LinearRing' %}
        {{- geom | simplify(default) | to_poly(name, 'River', '100') }}
        {% else %}
        {{- geom | simplify(default) | to_coordline(name) }}
        {% endif %}
    {% endfor %}
    ```

=== "After"

    ```jinja
    COLOR:River
    {% for name, geom in data.rivers.items() %}
        {{- geom | feat_simplify(default) | render_ts(label=name) }}
    {% endfor %}
    ```

## Data sources

To use the Feature API with full access to properties, use these source types:

| Data | Older type | Feature API type |
|---|---|---|
| AIXM 5.1 AerodromeMapping | `aixm`, `aixm2` | `aixm51` (`aixm2` data also works) |
| KML | `kml` | `kml2` |
| GeoPackage | `gpkg` | `gpkg` (unchanged) |

!!! warning "Switch a data source and its templates together"

    The older filters cannot read data from `kml2` sources. When you change a source from `kml` to
    `kml2`, migrate all templates that use it at the same time.

    Data from `aixm` and `aixm2` sources is best switched to `aixm51`. Data is then organised by AIXM
    feature type, so templates change a little:

    | Older | `aixm51` |
    |---|---|
    | `data.x['GuidanceLine'].items()` | `data.x['GuidanceLine']` (a list; the feature ID is `feature.id`) |
    | `data.x['GuidanceLineByDesig']['A']` | `data.x.group('GuidanceLine', 'designator')['A']` |
    | `data.x['VerticalStructureByName']['N']` | `data.x.group('VerticalStructure', 'name')['N']` |
    | `data.x['RunwayElement']['<uuid>']` | `data.x.find('<uuid>')` |
    | `line.type`, `geom.marking_location` | `line.properties.type`, `geom.properties.markingLocation` |

When switching from `kml` to `kml2`, the structure of the data stays the same: folders are dicts and
placemark names map to lists. Two things change:

- KML polygons become real polygons, including their holes, instead of plain outlines.
- A `root` folder that does not exist stops the build instead of silently using the whole file.
