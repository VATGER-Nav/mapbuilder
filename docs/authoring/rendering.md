---
icon: lucide/map
---

# Rendering

Filters starting with `render_` end a pipeline and turn features into map statements. Like the
`feat_` filters, they accept single features, lists, dicts and bare geometries.

Most renderers take an optional `label`. If given, it is written as a comment line before the
output (`// C1`), which makes generated files easier to read.

## Overview

| Filter | GRP | TopSky | Draws |
|---|:-:|:-:|---|
| [`render_grp`](#render_grp) | ✓ | | Everything, by geometry type |
| [`render_ts`](#render_ts) | | ✓ | Everything, by geometry type |
| [`render_area`](#render_area) | ✓ | | Filled or outlined areas (`COORDTYPE`) |
| [`render_line`](#render_line) | ✓ | ✓ | Lines and outlines (`LINE`) |
| [`render_polyline`](#render_polyline) | ✓ | | Lines and outlines (`COORDTYPE:…:POLYLINE`) |
| [`render_coordline`](#render_coordline) | | ✓ | Lines and outlines (`COORDLINE`) |
| [`render_coordpoly`](#render_coordpoly) | | ✓ | Filled areas (`COORDPOLY`) |
| [`render_coords`](#render_coords) | ✓ | ✓ | Plain `COORD` lines, e.g. for stands |
| [`render_symbol`](#render_symbol) | ✓ | ✓ | Symbols, optionally labelled |
| [`render_text`](#render_text) | ✓ | ✓ | Text labels |

!!! note "What cannot be drawn"

    Neither plugin supports holes in areas. Areas with holes are drawn without them, and mapbuilder
    logs a warning. Geometries a renderer cannot draw, such as points in `render_area`, are skipped
    with a warning that names the feature.

## Render by geometry type

### `render_grp`

```jinja
things | render_grp(area='OTHER:REGION', lines='line', symbol=None, label=None)
```

Renders every part for Ground Radar according to its geometry type:

| Geometry | Output |
|---|---|
| Polygon, closed ring | `COORDTYPE:<area>` followed by `COORD` lines |
| Line | `LINE` statements, or with `lines='polyline'` a `COORDTYPE:OTHER:POLYLINE` block |
| Point | `SYMBOL:<symbol>:…` – points are skipped with a warning if no `symbol` is given |

```jinja
COLOR:closure
{{ data.eddp_kml['Construction'] | render_grp(area='TWYCLOSED:REGION', symbol='CROSS') }}
```

`lines='polyline'` produces smaller files than `LINE` statements, because every point is written only
once.

### `render_ts`

```jinja
things | render_ts(fill=100, symbol=None, label=None)
```

Renders every part for TopSky according to its geometry type:

| Geometry | Output |
|---|---|
| Polygon, closed ring | `COORD` lines followed by `COORDPOLY:<fill>` |
| Line | `COORD` lines followed by `COORDLINE` |
| Point | `SYMBOL:<symbol>:…` – points are skipped with a warning if no `symbol` is given |

`fill` must be a [fill pattern](#fill-patterns).

```jinja
COLOR:River
{% for name, river in data.rivers.items() %}
    {{- river | feat_simplify(0.000005) | render_ts(label=name) }}
{% endfor %}
```

## Areas

### `render_area`

```jinja
things | render_area(area_def, label=None)
```

**GRP.** Renders each polygon as a `COORDTYPE:<area_def>` line followed by its `COORD` lines.

`area_def` is everything after `COORDTYPE:` and follows the GRP syntax
`AreaType:DrawType[:HatchType[:FillType]]`:

- **AreaType:** `OTHER` (plain drawing), `TWYCLOSED`, `RWYCLOSED`, `APW`, `AREATYPE` or `TWYTYPE`
- **DrawType:** `REGION` (filled with outline), `REGION_FILLONLY`, `POLYGON` (outline only),
  `POLYLINE` or `NONE`
- **HatchType** (optional): `/`, `\`, `+`, `X`, `-`, `|` or `0` (none)
- **FillType** (optional): a [fill pattern](#fill-patterns)

```jinja
{{ data.eddm['ApronElement'] | render_area('OTHER:REGION') }}
{{ snow_areas | render_area('OTHER:REGION:/') }}   {# hatched #}
```

```text title="Output"
COORDTYPE:OTHER:REGION
COORD:48.3561234:11.7812345
COORD:48.3562345:11.7823456
COORD:48.3551234:11.7824567
COORD:48.3561234:11.7812345
```

!!! tip

    For `AREATYPE` and `TWYTYPE` areas, GRP expects the `RESTRICTION:` lines *before* the
    `COORDTYPE` line, so write them into the template before the `render_area` call.

### `render_coordpoly`

```jinja
things | render_coordpoly(fill, label=None, color=None)
```

**TopSky.** Renders each polygon as `COORD` lines followed by `COORDPOLY:<fill>`. If `color` is given,
a `COLOR:` line is written first. `fill` must be a [fill pattern](#fill-patterns).

```jinja
{{ data.cityscapes | render_coordpoly(100, 'cities', 'City') }}
```

## Lines

### `render_line`

```jinja
things | render_line(label=None)
```

**GRP and TopSky.** Renders lines as `LINE` statements, one per segment. Polygons are drawn as
outlines, including their holes.

```jinja
{{ taxilanes['C1'] | feat_join | render_line('C1') }}
```

```text title="Output"
// C1
LINE:48.3501234:11.7712345:48.3502345:11.7723456
LINE:48.3502345:11.7723456:48.3503456:11.7734567
```

### `render_polyline`

```jinja
things | render_polyline(line_def='OTHER:POLYLINE', label=None)
```

**GRP.** Renders each line as one `COORDTYPE:<line_def>` block followed by its `COORD` lines. Polygons
are drawn as outlines, including their holes. This is more compact than `render_line`.

### `render_coordline`

```jinja
things | render_coordline(label=None)
```

**TopSky.** Renders each line as `COORD` lines followed by `COORDLINE`. Polygons are drawn as outlines,
including their holes.

```jinja
LAYER:-3
STYLE:Solid:1
{{ data.eddm_kml['Tracks 1'] | render_coordline('tracks') }}
```

## Coordinates only

### `render_coords`

```jinja
things | render_coords
```

**GRP and TopSky.** Writes only the `COORD` lines of a single line or polygon, for statements that
you write yourself, such as stand definitions:

```jinja
{% set stands = data.eddm_stands['EDDM-stands'] %}
STAND:EDDM:101
{{ stands['101'] | render_coords }}
USE:C
CODE:C
```

If the input has more than one part, only the first one is written and a warning is logged.

## Symbols and text

Symbols and text are placed at each point of a feature. For lines and areas, a point inside the
geometry is used, so you can label an apron or taxiway area directly.

Labels are cleaned up automatically:

- Everything from a `#` onwards is removed, so KML placemarks named `A#1` and `A#2` are both
  labelled `A`.
- Colons are replaced with spaces, because colons separate fields in both formats. A warning is
  logged.
- If you label with a property (`prop=…`) that a feature does not have, a warning is logged and the
  feature gets no label.

### `render_symbol`

```jinja
things | render_symbol(symbol, text=None, prop=None, offset=(0, 0))
```

**GRP and TopSky.** Writes a `SYMBOL` statement for each point. The symbol must be defined in your
maps file (`SYMBOLDEF`) or be a built-in symbol of the plugin.

To add a label, pass a fixed `text` or the name of a property with `prop`. `offset` moves the label
by pixels: x to the right, y downwards.

```jinja
{{ data.eddp_kml['RRS']['08L_2400'] | render_symbol('rrs-down') }}
{{ stands | render_symbol('stand', prop='designator', offset=(0, 12)) }}
```

```text title="Output"
SYMBOL:rrs-down:51.4231234:12.2112345
SYMBOL:stand:48.3531234:11.7812345:101:0:12
```

### `render_text`

```jinja
things | render_text(text=None, prop=None, offset=None, align=None)
```

**GRP and TopSky.** Writes a `TEXT` statement for each point, with either a fixed `text` or the value
of property `prop`.

- `offset=(x, y)` moves the text by pixels: x to the right, y downwards.
- `align` sets the alignment: one of `L`, `C`, `R` (horizontal) followed by one of `T`, `C`, `B`
  (vertical), e.g. `'LT'` for left/top. Without it, the default alignment of the map applies.

```jinja
{{ data.eddp_kml['Labels'] | render_text(prop='name') }}
{{ holding_points | render_text(text='CAT II', offset=(10, -5), align='LC') }}
```

```text title="Output"
TEXT:48.3541234:11.7832345:APN 1
TEXT/LC:48.3512345:11.7756789:CAT II:10:-5
```

## Fill patterns

`render_ts`, `render_coordpoly` and the FillType of `render_area` accept these fill patterns, as
defined by both plugins:

| Value | Meaning |
|---|---|
| `0` | No fill |
| `5`, `10`, `20`, `25`, `30`, `40`, `50`, `60`, `70`, `75`, `80`, `90` | Fill percentage (a dot pattern) |
| `100` | Solid fill |
| `E0` … `E52` | Hatch styles (GDI+ HatchStyle values) |

Any other value stops the build with an error, because the plugins would ignore it silently.

## Output settings

The `[render]` section of `mapbuilder.toml` controls how the output is written.

```toml title="mapbuilder.toml"
[render]
# Decimal places of coordinates in generated maps (7 ~ 1 cm); omit for full precision
precision = 7
```

`precision`
:   Number of decimal places for coordinates, from `0` to `15`. Coordinates are rounded and trailing
    zeros are removed, e.g. `48.3671551307609` becomes `48.3671551`. Without this setting,
    coordinates are written with full precision. Seven decimal places are accurate to about 1 cm.

    The setting applies to all coordinates mapbuilder writes, including the older filters and
    the runway and ECL helpers. Coordinates you write into templates yourself are not changed.

Unknown settings in `[render]` stop the build with an error, so typos do not go unnoticed.
