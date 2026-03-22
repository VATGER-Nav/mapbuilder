def ecl(start: str, bearing: float, count: int, dist: float = 1, start_blank: bool = True):
    """
    Generates an extended center line (ECL) based on a starting point, bearing, number of segments,
    distance between points, and whether the sequence begins with a blank segment.

    Parameters:
        start (str): The starting coordinate identifier.
        bearing (float): The initial bearing in degrees, used to determine the direction of the line.
        count (int): The total number of segments in the resultant line.
        dist (float, optional): The distance between consecutive points in the line. Default is 1.
        start_blank (bool, optional): Indicates whether to start the sequence with a blank segment. Default is True.

    Returns:
        str: A concatenated series of coordinate line segments formatted as strings.
    """
    lines = []
    draw = not start_blank
    for idx in range(0, count):
        if draw and idx + 1 <= count:
            lines.append(f"COORD_PBD:{start}:{bearing}:{dist * idx}")
            lines.append(f"COORD_PBD:{start}:{bearing}:{dist * (idx + 1)}")
            lines.append("COORDLINE")

        draw = not draw

    return "\n".join(lines)
