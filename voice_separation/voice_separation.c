#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "voice_separation.h"

// Define constants for the LCG (from Numerical Recipes)
#define LCG_A 1664525
#define LCG_C 1013904223
#define LCG_M 4294967296  // 2^32

typedef struct slice {
    int     start;
    int     stop;
    double *offsets;
    int    *links;
    int    *cands;
} Slice;

int overlaps(Descriptor* m, int a, int b) {
    return (m->onset[a] <= m->onset[b] && m->offset[a] > m->onset[b]) ||
           (m->onset[a] >  m->onset[b] && m->offset[b] > m->onset[a]);
}

unsigned int lcg_random(Descriptor* m) {
    m->lcg = (LCG_A * m->lcg + LCG_C) % LCG_M;
    return m->lcg;
}

double random_double(Descriptor* m) {
    return (double)lcg_random(m) / (double)LCG_M;
}

int random_range(Descriptor* m, int min, int max) {
    return (lcg_random(m) % (max - min)) + min;
}

int next_slice(Descriptor* m, int* start, int* stop) {
    *start = *stop;
    while (*stop < m->max_notes) {
        int all_overlap = 1;
        for (int i = *start; i < *stop; i++) {
            all_overlap &= overlaps(m, i, *stop);
        }
        if (all_overlap) {
            *stop += 1;
        } else {
            break;
        }
    }
    return *start < *stop;
}

int previous_chord(Descriptor* m, int i) {
    int chord = m->chord[i];
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != chord) return i;
    }
    return -1;
}

int min_duration(Descriptor* m, int i) {
    int b = i;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return b;
        if (m->duration[i] < m->duration[b]) b = i;
    }
    return b;
}

int max_duration(Descriptor* m, int i) {
    int b = i;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return b;
        if (m->duration[i] > m->duration[b]) b = i;
    }
    return b;
}

int min_position(Descriptor* m, int i) {
    int b = i;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return b;
        if (m->position[i] < m->position[b]) b = i;
    }
    return b;
}

int max_position(Descriptor* m, int i) {
    int b = i;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return b;
        if (m->position[i] > m->position[b]) b = i;
    }
    return b;
}

int min_onset(Descriptor* m, int i) {
    int b = i;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return b;
        if (m->onset[i] < m->onset[b]) b = i;
    }
    return b;
}

int max_onset(Descriptor* m, int i) {
    int b = i;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return b;
        if (m->onset[i] > m->onset[b]) b = i;
    }
    return b;
}

int max_offset(Descriptor* m, int i) {
    int b = i;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return b;
        if (m->offset[i] > m->offset[b]) b = i;
    }
    return b;
}

double average_position(Descriptor* m, int i, int* count) {
    int chord = m->chord[i];
    double position = m->position[i];
    *count += 1;
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != chord) return position;
        position += m->position[i];
        *count += 1;
    }
    return position;
}

double chord_position(Descriptor* m, int i, double ref) {
    int b = i;
    double delta_b, delta_i;
    delta_b = fabs(m->position[b] - ref);
    while (m->link[i] >= 0) {
        i = m->link[i];
        if (m->chord[i] != m->chord[b]) return m->position[b];
        if ((delta_i = fabs(m->position[i] - ref)) < delta_b) {
            b = i;
            delta_b = delta_i;
        }
    }
    return m->position[b];
}

double calculate_pitch_penalty(Descriptor* m, int start, int stop, int* links) {
    double pD = 0.0, pvD, p;
    int i, j, k;
    for (int v = 0; v < m->max_voices; v++) {
        i = links[v];
        pvD = 0.0;
        while (start <= i) {
            if ((j = previous_chord(m, i)) >= 0) {
                p = chord_position(m, j, m->position[i]);
                k = 0;
                while (k < m->pitch_lookback && (j = previous_chord(m, j)) >= 0) {
                    k += 1;
                    p = 0.8*p + 0.2*chord_position(m, j, m->position[i]);
                }
                pvD += (1.0 - pvD) * fmin(1.0, fabs(m->position[i] - p) / 128.0);
            }
            i = m->link[i];
        }
        pD += (1.0 - pD) * pvD;
    }
    return pD;
}

double calculate_gap_penalty(Descriptor* m, Slice* s) {
    double gD = 0.0, mD;
    int cNotes = 0;
    int i;
    for (int v = 0; v < m->max_voices; v++) {
        i = s->cands[v];
        if (i < s->start) continue;
        while (s->start <= m->link[i]) { i = m->link[i]; }

        mD = 0.0;
        for (int w = 0; w < m->max_voices; w++) {
            mD = fmax(mD, m->onset[i] - s->offsets[w]);
        }
        if (mD > 0.0) {
            gD += fmax(0.0, (m->onset[i] - s->offsets[v]) / mD);
        }
        cNotes += 1;
    }
    if (cNotes == 0) {
        return 0.0;
    } else {
        return gD / cNotes;
    }
}

double calculate_chord_penalty(Descriptor* m, int start, int stop, int* links) {
    double cD = 0.0, minOnset, maxOnset, minDuration, maxDuration, minPosition, maxPosition;
    double pDuration, pRange, pOn, p;
    int i;
    for (int v = 0; v < m->max_voices; v++) {
        i = links[v];
        while (start <= i) {
            minOnset = m->onset[min_onset(m, i)];
            maxOnset = m->onset[max_onset(m, i)];
            minDuration = m->duration[min_duration(m, i)];
            maxDuration = m->duration[max_duration(m, i)];
            minPosition = m->position[min_position(m, i)];
            maxPosition = m->position[max_position(m, i)];
            pDuration = 1.0 - minDuration / maxDuration;
            pRange = fmin(1.0, (maxPosition - minPosition) / 24);
            pOn = (maxOnset - minOnset) / maxDuration;
            p = pDuration + (1.0 - pDuration) * pRange;
            p = p + (1.0 - p) * pOn;
            cD = cD + (1.0 - cD) * p;
            i = previous_chord(m, i);
        }
    }
    return cD;
}

double calculate_overlap_penalty(Descriptor* m, Slice* s) {
    double oD = 0.0, ovD, oDist;
    int i, j;
    for (int v = 0; v < m->max_voices; v++) {
        ovD = 0.0;
        i = s->links[v];
        for (j = s->start; j < s->stop; j++) {
            if (m->voice[j] != v) continue;
            if (i < 0) { i = j; continue; }
            if (overlaps(m, i, j)) {
                oDist = 1.0 - (m->onset[j] - m->onset[i]) / m->duration[i];
                ovD = ovD + (1.0 - ovD) * oDist;
            }
            if (m->chord[i] != m->chord[j]) { i = j; }
        }
        oD = oD + (1.0 - oD) * ovD;
    }
    return oD;
}

void swap(int* a, int* b) {
    int temp = *a;
    *a = *b;
    *b = temp;
}

void swap_double(double* a, double* b) {
    double temp = *a;
    *a = *b;
    *b = temp;
}

int partition(int voice[], int present[], double position0[], double position1[], int low, int high) {
    double pivot = position0[high];
    int i = low - 1;
    for (int j = low; j < high; j++) {
        if (position0[j] < pivot) {
            i++;
            swap_double(&position0[i], &position0[j]);
            swap_double(&position1[i], &position1[j]);
            swap(&voice[i], &voice[j]);
            swap(&present[i], &present[j]);
        }
    }
    swap_double(&position0[i + 1], &position0[high]);
    swap_double(&position1[i + 1], &position1[high]);
    swap(&voice[i + 1], &voice[high]);
    swap(&present[i + 1], &present[high]);
    return i + 1;
}

void quicksort(int voice[], int present[], double position0[], double position1[], int low, int high) {
    if (low < high) {
        int pi = partition(voice, present, position0, position1, low, high);
        quicksort(voice, present, position0, position1, low, pi - 1);
        quicksort(voice, present, position0, position1, pi + 1, high);
    }
}

double calculate_cross_penalty(Descriptor* m, int start, int stop, int* links) {
    int i, count;
    int voice[m->max_voices];
    int present[m->max_voices];
    double position0[m->max_voices];
    double position1[m->max_voices];
    double p;
    int k;
    for (int v = 0; v < m->max_voices; v++) {
        voice[v] = v;
        position0[v] = 0.0;
        position1[v] = 0.0;
        count = 0;
        i = links[v];
        if (i < 0) {
            present[v] = 0;
            continue;
        }
        do {
            position0[v] = average_position(m, i, &count);
            i = previous_chord(m, i);
        } while (start <= i);
        if (i >= 0) {
            position0[v] /= count;
            count = 0;
            position1[v] = average_position(m, i, &count);
            position1[v] /= count;
            present[v] = 1;
        } else {
            present[v] = 0;
        }
    }
    quicksort(voice, present, position0, position1, 0, m->max_voices-1);
    p = 0.0;
    k = 1;
    for (int i = 0; i < m->max_voices; i++) {
        if (present[i]) {
            if (k) { p = position1[i]; k = 0; }
            if (p > position1[i]) return 1.0;
            p = position1[i];
        }
    }
    return 0.0;
}

double calculate_total_cost(Descriptor* m, Slice* s, int print) {
    for (int i = 0; i < m->max_voices; i++) {
        s->cands[i] = s->links[i];
    }
    for (int i = s->start; i < s->stop; i++) {
        m->link[i] = s->cands[m->voice[i]];
        s->cands[m->voice[i]] = i;
    }
    double total_cost = 0.0, pp, gp, cp, op, rp;
    total_cost += pp = m->pitch_penalty * calculate_pitch_penalty(m, s->start, s->stop, s->cands);
    total_cost += gp = m->gap_penalty * calculate_gap_penalty(m, s);
    total_cost += cp = m->chord_penalty * calculate_chord_penalty(m, s->start, s->stop, s->cands);
    total_cost += op = m->overlap_penalty * calculate_overlap_penalty(m, s);
    total_cost += rp = m->cross_penalty * calculate_cross_penalty(m, s->start, s->stop, s->cands);
    if (print) {
        for (int k = 0; k < m->max_voices; k++) {
            printf("voice %d\n", k);
            for (int i = s->start; i < s->stop; i++) {
                if (m->voice[i] == k) printf("  note: %f:%f p=%d\n", m->onset[i], m->offset[i], m->position[i]);
            }
        }
        printf("total pen: %f\n", total_cost);
        printf("  pitch pen: %f\n", pp);
        printf("  gap pen: %f\n", gp);
        printf("  chord pen: %f\n", cp);
        printf("  overlap pen: %f\n", op);
        printf("  cross pen: %f\n", rp);
    }
    return total_cost;
}

void lowest_cost_neighbor(Descriptor* m, Slice* s) {
    int voice_index;
    int best_index = s->start;
    int best_voice = m->voice[s->start];
    double best_cost, new_cost;
    best_cost = calculate_total_cost(m, s, 0);
    for (int i = s->start; i < s->stop; i++) {
        voice_index = m->voice[i];
        for (int j = 0; j < m->max_voices; j++) {
            if (j != voice_index) {
                m->voice[i] = j;
                new_cost = calculate_total_cost(m, s, 0);
                if (new_cost < best_cost) {
                    best_index = i;
                    best_voice = j;
                    best_cost = new_cost;
                }
            }
        }
        m->voice[i] = voice_index;
    }
    m->voice[best_index] = best_voice;
}

void random_neighbour(Descriptor* m, int start, int stop) {
    int index, voice_index;
    index = random_range(m, start, stop);
    voice_index = random_range(m, 0, m->max_voices-1);
    if (voice_index >= m->voice[index]) voice_index++;
    m->voice[index] = voice_index;
}

void stochastic_local_search(Descriptor* m, Slice* s) {
    int no_improvement_counter;
    int max_iterations;
    int best[s->stop - s->start];
    double best_cost, new_cost;
    max_iterations = (s->stop - s->start) * m->max_voices * 3;
    for (int i = 0; i < s->stop - s->start; i++) {
        best[i] = m->voice[i+s->start] = 0;
    }
    best_cost = calculate_total_cost(m, s, 0);
    no_improvement_counter = 0;
    while (no_improvement_counter < max_iterations) {
        if (random_double(m) <= 0.8) {
            lowest_cost_neighbor(m, s);
        } else {
            random_neighbour(m, s->start, s->stop);
        }
        new_cost = calculate_total_cost(m, s, 0);
        if (new_cost < best_cost) {
            for (int i = 0; i < s->stop - s->start; i++) {
                best[i] = m->voice[i+s->start];
            }
            best_cost = new_cost;
            no_improvement_counter = 0;
        } else {
            no_improvement_counter += 1;
        }
    }
    for (int i = 0; i < s->stop - s->start; i++) {
        m->voice[i+s->start] = best[i];
        m->link[i+s->start] = s->links[best[i]];
        s->links[best[i]] = i+s->start;
        s->offsets[best[i]] = fmax(s->offsets[best[i]], m->offset[i+s->start]);
    }
}

void voice_separation(Descriptor* m) {
    double offsets[m->max_voices];
    int links[m->max_voices];
    int cands[m->max_voices];
    for (int i = 0; i < m->max_voices; i++) {
        offsets[i] = m->onset[0];
        links[i] = -1;
    }
    Slice slice = { 0, 0, offsets, links, cands };
    int    chord = 0;
    double onset = m->onset[0];
    while (next_slice(m, &slice.start, &slice.stop)) {
        for (int i = slice.start; i < slice.stop; i++) {
            if (m->onset[i] - onset > 0.1) {
                chord++;
                onset = m->onset[i];
            }
            m->chord[i] = chord;
        }
        chord++;

        stochastic_local_search(m, &slice);
    }
}
