import mido

def quick_connect(fabric, label):
    return [MidiController(name, fabric, label)
            for name in get_controller_names()]

def get_controller_names():
    return mido.get_input_names()

class MidiController:
    def __init__(self, name, fabric, label):
        self.connection = mido.open_input(name, callback=self._callback)
        self.fabric = fabric
        self.label = label
        self.synths = {}

    def close(self):
        for s in self.synths:
            s.set(gate = 0)
        self.connection.close()

    def _callback(self, msg):
        synths = self.synths
        match msg.type:
            case 'note_off':
                channel = msg.channel
                note = msg.note
                synths.pop((channel, note)).set(gate = 0)
            case 'note_on':
                channel = msg.channel
                velocity = msg.velocity / 127
                note = msg.note
                synths[channel, note] = self.fabric.synth(self.label, note=note)
            case _:
                pass

