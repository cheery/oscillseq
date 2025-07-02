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
what can be connected where and how.
