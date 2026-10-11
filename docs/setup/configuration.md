---
icon: lucide/settings
---

# Configuration

mapbuilder is configured with a `mapbuilder.toml` file in the source directory. It has four sections:

| Section | Required | Content |
|---|:-:|---|
| [`[render]`](#render) | | How output is written |
| [`[data]`](#data-sources) | ✓ | Data sources available to templates |
| [`[profiles]`](#profiles) | ✓ | Which maps are built into which files |
| [`[runways]`](#runways) | ✓ | Runway data for the runway drawing helpers (may be empty) |

A minimal configuration:

```toml title="mapbuilder.toml"
[render]
precision = 7

[data.eddm]
type = "aixm51"
source = "dfs:0:EDDM AerodromeMapping:AIXM 5.1.1"

[profiles.TWR]
maps = [
    { map = "grplugin", target = "Plugins/GRPlugin/GRpluginMaps.txt", add-version = true },
]
aliases = []

[runways]
```

## Render

```toml
[render]
# Decimal places of coordinates in generated maps (7 ~ 1 cm); omit for full precision
precision = 7
```

`precision`
:   Number of decimal places for coordinates, from `0` to `15`. Coordinates are rounded and trailing
    zeros are removed. Without this setting, coordinates are written with full precision. Seven decimal
    places are accurate to about 1 cm.

Unknown settings stop the build with an error.

## Data sources

Each entry in `[data]` defines a data source. Its name is how templates access it: a source
`[data.eddm]` is available as `data.eddm`.

```toml
[data.eddm]
type = "aixm51"
source = "dfs:0:EDDM AerodromeMapping:AIXM 5.1.1"
```

Every source has a `type` and, for most types, a `source`.

### Where data comes from

The `source` setting accepts three forms:

| Form | Example | Notes |
|---|---|---|
| Path | `"gis/EDDM.gpkg"` | Relative to the source directory |
| URL | `"https://example.org/data.xml"` | Downloaded and cached for 96 hours |
| DFS dataset | `"dfs:0:EDDM AerodromeMapping:AIXM 5.1.1"` | Downloaded from the DFS dataset service |

A DFS source has the form `dfs:<amendment>:<dataset>:<format>`:

- `<amendment>`: `0` for the AIRAC amendment currently in effect, `1` and `2` for the upcoming ones.
- `<dataset>`: the dataset name as published by DFS, e.g. `EDDM AerodromeMapping` or `ED MVA`.
- `<format>`: the release format, e.g. `AIXM 5.1.1` or `GeoJSON`.

!!! warning "License and usage rights"
    The DFS AIXM datasets are subject to the terms of use published on their AIP publication site.
    **It is the sole responsibility of the user to obtain permission to use the data.**

    Simlilar usage restrictions apply to other ANSPs.

Downloaded ZIP files are unpacked automatically. URL and DFS sources are only supported by the source
types that read a single file (`aixm`, `aixm2`, `aixm51`, `geojson`); the others read files from the
source directory.

### Source types

These types produce [features](../authoring/data.md) for the Feature API:

`aixm51`
:   AIXM 5.1 AerodromeMapping data.

    | Setting | Description |
    |---|---|
    | `source` | Path, URL or DFS dataset |

`gpkg`
:   Layers of a GeoPackage file.

    | Setting | Description |
    |---|---|
    | `source` | Path to the `.gpkg` file |
    | `layers` | List of layer names to load (optional, defaults to all feature layers) |
    | `id_property` | Property used as feature ID (optional, defaults to the GeoPackage feature ID) |

    Layers must use the WGS 84 coordinate system (EPSG:4326), the default in QGIS for new
    GeoPackages. Layers in other coordinate systems stop the build with an error.

`geojson`
:   GeoJSON file.

    | Setting | Description |
    |---|---|
    | `source` | Path, URL or DFS dataset |
    | `id_property` | Property used as feature ID (optional, defaults to the `id` of each feature, or its position in the file) |

    Coordinates must be WGS 84 (EPSG:4326), as required by the GeoJSON standard. Files declaring
    another coordinate system stop the build with an error.

`kml2`
:   KML file.

    | Setting | Description |
    |---|---|
    | `source` | Path to the `.kml` file |
    | `root` | Name of a top-level folder to use instead of the whole file (optional) |

These types are used with the older template filters or for special purposes:

`aixm`, `aixm2`
:   AIXM 5.1 AerodromeMapping data in older formats. Setting: `source`. Data from `aixm2` also works
    with the Feature API.

`kml`
:   KML file as plain geometries. Settings: `source`, `root` (optional; if the folder does not exist,
    the whole file is used).

`raw`
:   Text file inserted as-is, e.g. `{{ data.mva }}`. Setting: `source`. Read as ISO-8859-1.

`ese`
:   SID and STAR procedures from a EuroScope `.ese` file, available as `data.<name>.SIDSTAR`. Setting:
    `source`.

`sct`
:   Runways from a EuroScope `.sct` sector file, available as `data.<name>.RUNWAY`. Setting: `source`.

`sectors`
:   Sector definitions, available as `data.<name>.fixes` and `data.<name>.lines`. Setting: `source`.

An unknown `type` is logged as an error and the source is skipped.

## Profiles

A profile is one set of output files, for example the files of a day and a night display setup. Each
profile lists the maps to build:

```toml
[profiles.TWR_DAY]
maps = [
    { map = "grplugin-phoenix", target = "EDMM/Plugins/GRPlugin/TWR_PHX_DAY/GRpluginMaps.txt", add-version = true },
    { map = "grplugin-stands", target = "EDMM/Plugins/GRPlugin/TWR_PHX_DAY/GRpluginStands.txt" },
]
aliases = ["bright"]

[profiles.TWR_NIGHT]
maps = [
    { map = "grplugin-phoenix", target = "EDMM/Plugins/GRPlugin/TWR_PHX_NIGHT/GRpluginMaps.txt", add-version = true },
]
aliases = ["dark"]
```

`maps`
:   List of maps to build, each with these settings:

    | Setting | Description |
    |---|---|
    | `map` | Directory below `maps/` to build from |
    | `target` | Output file, relative to the target directory |
    | `add-version` | Adds a `//VERSION:` line with the build time to the header (optional) |

`aliases`
:   Alternative names used to pick [per-profile variants](project.md#per-profile-variants). Profiles
    that share an alias, such as several bright profiles, can share variant files. Use `[]` if you
    do not need any.

The same map directory can be built for several profiles; templates and `.d` variants decide what
differs between them.

## Runways

The `[runways]` section provides runway data for the runway drawing helpers in templates, such as
extended centrelines and localizer ticks. The section must exist, but can be empty.

```toml
[runways.EDDM.26R]
thr = [48.366886944, 11.821172778]   # threshold (lat, lon)
bearing = 263.4                      # runway bearing
loc = [48.361732556, 11.754140361]   # localizer antenna (lat, lon)
```

Templates access it as `runways['EDDM']['26R']`, for example:

```jinja
{{ ecl_dashes(runways['EDDM']['26R'], 10) }}
```

You can add further fields (e.g. a final approach point) for use in your own templates.
