#include "voice_separation.h"

int main() {
    double onset[] = {0.0, 2.0};
    double offset[] = {1.0, 3.0};
    double duration[] = {1.0, 1.0};
    int position[] = {69, 72};
    int chord[] = {0,0};
    int voice[] = {0,0};
    int link[] = {0,0};

    Descriptor m = {
        .max_notes = 2,
        .onset = onset,
        .offset = offset,
        .duration = duration,
        .position = position,
        .chord = chord,
        .voice = voice,
        .link = link,
        .max_voices = 6,
        .pitch_penalty = 1.0,
        .gap_penalty = 1.0,
        .chord_penalty = 1.0,
        .overlap_penalty = 1.0,
        .cross_penalty = 1.0,
        .chord_spread = 0.0,
        .pitch_lookback = 2,
        .lcg = 0,
        .debug_print = 0
    };
    voice_separation(&m);
}
