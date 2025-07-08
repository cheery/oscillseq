class StepRhythm:
    def __init__(self, table):
        self.table = table

    def to_events(self, start, duration):
        events = []
        duration /= len(self.table)
        for i, on in enumerate(self.table):
            if on:
                events.append((start + i*duration, duration))
        return events

    def __str__(self):
        return "".join(map(str, self.table))
