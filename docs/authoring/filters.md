---
icon: lucide/filter
---

# Selecting and transforming

Filters starting with `feat_` take features and return a list of features. Use them to pick the
features you want and to prepare their geometries before [rendering](rendering.md).

All of them accept a single feature, a list, a dict (values are used) or nested combinations, as well
as bare geometries.

## Selecting

### `feat_where`

```jinja
things | feat_where(prop, value, …)
```

Keeps the features whose property `prop` has one of the given values. Use `'id'` as `prop` to
match the feature ID.

```jinja
{{ data.eddm['RunwayMarking'] | feat_where('markingLocation', 'OTHER:PRE_THR') | render_grp }}
```

### `feat_exclude`

```jinja
things | feat_exclude(prop, value, …)
```

The opposite of `feat_where`: drops the features whose property has one of the given values. Useful
for leaving out individual segments:

```jinja
{{ taxilanes['C1']
   | feat_exclude('id', '3e99e6d5-131b-2fe6-e063-15baa8c0aafe')
   | feat_join | render_line('C1') }}
```

You can also pass a list with `*`: `feat_exclude('id', *excluded_ids)`.

### `feat_select_geometry`

```jinja
things | feat_select_geometry(name)
```

AIXM features can have several geometric properties. This filter uses only the one with the given
name and drops features that do not have it.

```jinja
{{ data.eddm['AircraftStand'] | feat_select_geometry('location') | render_symbol('stand') }}
```

!!! warning

    Use `feat_select_geometry` first in the pipeline. After a transforming filter such as
    `feat_simplify`, the named geometries are no longer available.

### `feat_min_area`

```jinja
things | feat_min_area(area)
```

Keeps the features whose area is at least `area`. Lines and points have no area and are always
dropped.

The area is measured in *square degrees*, so useful values are very small: `0.000000001` removes
areas below roughly 8 m² in central Europe. For multi-part features, the total area counts; use
`feat_explode` first to filter individual parts.

```jinja
{{ buildings | feat_explode | feat_min_area(0.000000001) | render_area('OTHER:REGION') }}
```

## Transforming

### `feat_simplify`

```jinja
things | feat_simplify(tolerance)
```

Simplifies each geometry by removing points that deviate less than `tolerance` from the simplified
shape. The tolerance is given in *degrees*: `0.000005` is about half a metre. Simplifying makes map
files smaller and faster to draw.

```jinja
{% set default = 0.000005 %}
{{ data.eddm['ApronElement'] | feat_simplify(default) | render_area('OTHER:REGION') }}
```

### `feat_explode`

```jinja
things | feat_explode
```

Splits multi-part geometries into one feature per part. Each part keeps the properties of its
feature.

### `feat_join`

```jinja
things | feat_join
```

Merges the lines of all features into as few lines as possible, joining segments that share an end
point. The result is a single feature; if the segments are not connected, its geometry has several
parts.

- Only lines are joined. Areas and points are skipped with a warning.
- The result keeps only the properties that are the same on all input features.

```jinja
{{ taxilanes['W1'] | feat_join | feat_simplify(default) | render_line('W1') }}
```

### `feat_join_by`

```jinja
things | feat_join_by(prop)
```

Joins features per value of a property, returning one feature per value in the order they first
appear. This replaces a loop over a `group(...)` result:

```jinja
{# one joined line per taxiway designator, labelled with the designator #}
{% for line in data.eddm['GuidanceLine'] | feat_join_by('designator') %}
    {{- line | render_line(line.properties.designator) }}
{% endfor %}
```

Features without the property are joined together into one feature.

### `feat_union`

```jinja
things | feat_union
```

Combines the geometries of all features into one, merging overlapping areas. Like `feat_join`, the
result keeps only the properties shared by all input features.

```jinja
{{ data.eddm['TaxiwayElement'] | feat_union | feat_simplify(default) | render_area('OTHER:REGION') }}
```
