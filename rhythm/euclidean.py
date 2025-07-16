__all__ = [
    "EuclideanRhythm"
]

def bjorklund(pulses: int, steps: int) -> list[int]:
    """
    Generate a Euclidean rhythm pattern using the Bjorklund algorithm.
    Returns a list of 1s (onsets) and 0s (rests).
    """
    if pulses <= 0:
        return [0] * steps
    if pulses >= steps:
        return [1] * steps
    # Initialize
    pattern = [[1] for _ in range(pulses)] + [[0] for _ in range(steps - pulses)]
    # Repeatedly distribute
    while True:
        # Stop when grouping is no longer possible
        if len(pattern) <= 1:
            break
        # Partition into two parts: first group, rest
        first, rest = pattern[:pulses], pattern[pulses:]
        if not rest:
            break
        # Append each element of rest into first, one by one
        for i in range(min(len(rest), len(first))):
            first[i] += rest[i]
        # Rebuild pattern
        pattern = first + rest[min(len(first), len(rest)):]
    # Flatten
    return list(itertools.chain.from_iterable(pattern))


def rotate(l, n):
    return l[n:] + l[:n]

class EuclideanRhythm:
    def __init__(self, pulses, steps, rotation):
        self.pulses = pulses
        self.steps = steps
        self.rotation = rotation

    def to_step_sequence(self):
        table = rotate(bjorklund(self.pulses, self.steps), self.rotation)
        return StepRhythm(table)

    def to_events(self, start, duration):
        return self.to_step_sequence().to_events(start, duration)

    def __str__(self):
        return f"euclidean {self.pulses}, {self.steps}, {self.rotation}"

