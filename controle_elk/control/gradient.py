FRAMES_PER_SECOND = 60


def changes(start: bytes, end: bytes, seconds: float):
    numerator, denominator = seconds.as_integer_ratio()
    count = max(1, numerator * FRAMES_PER_SECOND // denominator)
    channels = tuple((a, b - a) for a, b in zip(start, end))

    def color_at(index):
        fraction = index / count
        return bytes(round(a + delta * fraction) for a, delta in channels)

    index, color = 0, start
    while color != end:
        next_index = index + 1
        next_color = color_at(next_index)
        if next_color == color:
            # Each channel is monotonic, so a color never returns within a segment.
            low, high = next_index + 1, count
            while low < high:
                middle = (low + high) // 2
                if color_at(middle) == color:
                    low = middle + 1
                else:
                    high = middle
            next_index, next_color = low, color_at(low)
        yield seconds * ((next_index - index) / count), next_color
        index, color = next_index, next_color
    if index < count:
        yield seconds * ((count - index) / count), None
