"""Geometry rules, independent of Explorer and monitor APIs."""


def free_slot(start, end, occupied, width, desired=None, padding=8):
    """Place in a proven empty interval; return None if it cannot fit."""
    intervals = []
    for a, b in occupied:
        a, b = max(start, a - padding), min(end, b + padding)
        if a < b:
            intervals.append((a, b))
    intervals.sort()
    gaps, cursor = [], start + padding
    for a, b in intervals:
        if a - cursor >= width:
            gaps.append((cursor, a - width))
        cursor = max(cursor, b)
    if end - padding - cursor >= width:
        gaps.append((cursor, end - padding - width))
    if not gaps:
        return None
    desired = end - width - padding if desired is None else desired
    choices = [max(a, min(b, desired)) for a, b in gaps]
    return min(choices, key=lambda x: abs(x - desired))


class WheelSteps:
    def __init__(self):
        self.remainder = 0
        self.mode = None

    def consume(self, delta, shift=False):
        mode = "seek" if shift else "volume"
        if mode != self.mode:
            self.remainder = 0
            self.mode = mode
        self.remainder += delta
        steps = int(self.remainder / 120)
        self.remainder -= steps * 120
        return mode, steps * (10 if shift else 5)
