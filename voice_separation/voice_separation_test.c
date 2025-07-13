#include <stdio.h>
#include "voice_separation.h"

void monitor(Descriptor* m, int start, int stop, CostVector* cost, int stage) {
    printf("range %d:%d\n", start, stop);
    for (int k = 0; k < m->max_voices; k++) {
        for (int i = start; i < stop; i++) {
            if (m->voice[i] == k) printf("    note: %f:%f p=%d, voice=%d\n", m->onset[i], m->offset[i], m->position[i], k);
        }
    }
    printf("  total pen: %f\n", cost->total);
    printf("    pitch pen: %f\n", cost->pp);
    printf("    gap pen: %f\n", cost->gp);
    printf("    chord pen: %f\n", cost->cp);
    printf("    overlap pen: %f\n", cost->op);
    printf("    cross pen: %f\n", cost->rp);
}

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
        .monitor = monitor
    };
    voice_separation(&m);
}
