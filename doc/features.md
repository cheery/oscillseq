# Why this project is cool

## SuperCollider synthdef annotations (.desc files)

Although everything in SC is a float or float array,
it's useful to know in which range and which kind of value is carried.
Furthermore it's useful to know which parameters represent ports.

Here's how low pass filter is annotated:

    source: ar in 2
    out: ar out 2
    frequency: hz

And here's a saw oscillator's annotation:

    out: ar out 2
    note: pitch
    volume: db

Available descriptors at the time of writing this document are:

    boolean unipolar bipolar number pitch hz db duration

The descriptors provide a base reference for
how the sequencer treats different parameters,
and what can be connected where and how.

## Directed-acyclic graph timeline

The timeline consists of following elements (called brushes) that form a directed acyclic graph:

- Clip, a structure that holds other brushes.
- Tracker, a note generating brush.
- Control point, a control command, for instance to adjust tempo.
- Key, a key signature to adjust the tracker view.

The timeline objects are positioned on integer increments, per-measure.

## Rhythm-generators-view tracker

Tracker in this program is divided to three pieces:

- Rhythmic source.
- List of note generators or "tracks".
- A view that displays the tracks.

The rhythm generated (onset,duration) -events that are fed to the generators.
The generators decorate the events with details,
eg. pitch, volume, anything described in the synthetizer.

There are three rhythm models at the time of writing:
Rhythm trees, euclidean rhythms and step sequencer.
The later two are self-explanatory, the first one is a bit novel.

## Views with selectable piano roll, tracker, staff display

The view may be adjusted to work like a traditional tracker, but it also
has a musical staff representation and a piano roll available.

## Rhythm trees

The early version used a bit unusual [rhythm trees](https://www.pdonatbouillud.com/project/rythm-quantization/). Since then I've moved on to a more usual format.

## Rhythm quantizer

There's a quantizer that imitates [qparse's](https://qparse.gitlabpages.inria.fr/) algorithm.
In the current model it's used to edit rhythms: The rhythm is rendered into fractional representation,
the user does their thing on the fractional representation of rhythm in a mouse controller editor,
and it is quantized back into a rhythm tree.

## Voice separation

I've included my C language implementation of
["Voice Separation - A Local Optimisation Approach"](https://ismir2002.ismir.net/proceedings/02-FP01-6.pdf).
I used this to render a staff notation display in a previous project and needed a fast version of this algorithm.
My Python-version of this algorithm was way too slow so I rewrote it in C. Benchmarking revealed that it was effective.

However the correct implementation of this algorithm is very hard, it likely still needs some work before it's perfected.

When combined with rhythm quantizer, this algorithm enables transcription of MIDI into Tracker's format.

## Musical pitch class

Musical pitches are represented with (pitch, accidental) -pair, MIDI numbers and
frequencies.

## Node editor's wire obstacle avoidance

The node editor comes with a libavoid-inspired obstacle avoidance system.
This automatically routes the connections and makes the node graph more readable.

## Fabric and the audio playback stack

Fabric represents an instantiated node graph. It does automatical topological sorting
and maps node connections into buses.

The audio playback can be in several states and editor can freely transition between these states.

- OFFLINE - the server is down, this is used when producing nonrealtime scores.
- ONLINE - the base state of the server when it's merely online.
- FABRIC - the server has instantiated the node network and playing sound.
- PLAYING - the sequence playback is on and the node network is under control. 

Parts of the playback stack are restartable, allowing some structures to be swapped
while the program is playing.

## Node connection mapping to supercollider buses and relays

The supercollider provides a fixed number of buses to connect synthetizers together.
Multiple synthetizers can write into same bus, and multiple can read from it.
However, this is not too convenient to represent in the node editor, therefore
node editor allows any input to be connected to any output.

To map arbitrary connection graph into a set of buses is an interesting problem.
We solve the problem by performing a biclique decomposition.
The decomposition provides an initial mapping to buses, each biclique cover
represents one bus essentially.
The resulting decomposition is rewritten by rewriting ports that appear multiple times in biclique cover, until there are no two bicliques sharing a port.

## Sequence builder and sequence playback

The sequencer builder is placed between the document model and playback.
It allows the document model to output relatively abstract note events
that are then build into a sequence.

The sequence player is simple, consisting of a current play point,
loop start point, looping entry point and ending point.
The player sweeps over the sequence and makes sure the events are played in order.

## Quadratic control and envelopes

The sequencer builder processes tempo events into quadratic control signals.
These happen through building envelopes. Envelope is basically a connected segment
of linear functions.

Tempo is a linear function over time and it's used to drive other envelopes. The result is a spliced set of quadratic control events per controller.

The quadratic control is described in [SuperCollider forum](https://scsynth.org/t/linearly-changing-tempo-control-signals/11870).

## UPCOMING

- semi-automatic MIDI connection to nodes
- MIDI recording
