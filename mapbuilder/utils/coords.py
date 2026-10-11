"""Formatting of decimal coordinates in generated map files."""

from mapbuilder.render_context import current_render_context


def format_coord(lat, lon) -> str:
    """Formats a coordinate as ``lat:lon`` in decimal degrees."""
    return f"{format_degrees(lat)}:{format_degrees(lon)}"


def format_degrees(value) -> str:
    """Formats decimal degrees, rounded to the precision of the render context without trailing zeros."""
    precision = current_render_context().precision
    if precision is None:
        return f"{value}"

    result = f"{float(value):.{precision}f}"
    if "." in result:
        result = result.rstrip("0")
        if result.endswith("."):
            result += "0"

    # Avoid "-0.0" for tiny negative values
    return result.removeprefix("-") if set(result) <= set("-0.") else result
