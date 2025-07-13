#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "voice_separation.h"

// TODO: Lift CostVector out and use it to reduce amount of redundant
//       calls to "calculate_total_cost"

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
    if (min == max) return min;
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
    double gD = 0.0, onset, offset;
    int cNotes = 0;
    int i;
    for (int v = 0; v < m->max_voices; v++) {
        i = s->cands[v];
        if (i < s->start) continue;
        while (s->start <= m->link[i]) { i = m->link[i]; }

        offset = onset = m->onset[i];
        for (int w = 0; w < m->max_voices; w++) {
            offset = fmin(offset, s->offsets[w]);
        }
        if (s->offsets[v] < onset) {
            gD += fmax(0.0, fmin(1.0, (onset - s->offsets[v]) / (onset - offset)));
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
    int prev, next;
    for (int v = 0; v < m->max_voices; v++) {
        ovD = 0.0;
        prev = s->links[v];
        for (next = s->start; next < s->stop; next++) {
            if (m->voice[next] != v) continue;
            if (prev < 0) { prev = next; continue; }
            if (overlaps(m, prev, next)) {
                oDist = 1.0 - (m->onset[next] - m->onset[prev]) / m->duration[prev];
                ovD = ovD + (1.0 - ovD) * fmax(0.0, fmin(1.0, oDist));
            }
            if (m->chord[prev] != m->chord[next]) { prev = next; }
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

int partition(int voice[], double position[], int low, int high) {
    double pivot = position[high];
    int i = low - 1;
    for (int j = low; j < high; j++) {
        if (position[j] < pivot) {
            i++;
            swap_double(&position[i], &position[j]);
            swap(&voice[i], &voice[j]);
        }
    }
    swap_double(&position[i + 1], &position[high]);
    swap(&voice[i + 1], &voice[high]);
    return i + 1;
}

void quicksort(int voice[], double position[], int low, int high) {
    if (low < high) {
        int pi = partition(voice, position, low, high);
        quicksort(voice, position, low, pi - 1);
        quicksort(voice, position, pi + 1, high);
    }
}

double calculate_cross_penalty(Descriptor* m, Slice* s) {
    int count;
    int voice0[m->max_voices];
    double position0[m->max_voices];
    int voice1[m->max_voices];
    double position1[m->max_voices];
    int k;
    int voices_present = 0;
    for (int v = 0; v < m->max_voices; v++) {
        if (0 <= s->links[v]) { voices_present++; };
    }
    k = 0;
    for (int v = 0; v < m->max_voices; v++) {
        if (0 <= s->links[v]) {
            count = 0;
            voice0[k++] = v;
            position0[v] = average_position(m, s->links[v], &count);
            position0[v] /= count;
        }
    }
    k = 0;
    for (int v = 0; v < m->max_voices; v++) {
        if (0 <= s->cands[v] && 0 <= s->links[v]) {
            count = 0;
            voice1[k++] = v;
            position1[v] = average_position(m, s->cands[v], &count);
            position1[v] /= count;
        }
    }
    
    if (voices_present == 0) {
        return 0.0;
    }
    quicksort(voice0, position0, 0, voices_present-1);
    quicksort(voice1, position1, 0, voices_present-1);
    for (int i = 0; i < voices_present; i++) {
        if (voice0[i] != voice1[i]) return 1.0;
    }
    return 0.0;
}

double calculate_total_cost(Descriptor* m, Slice* s, int stage) {
    for (int i = 0; i < m->max_voices; i++) {
        s->cands[i] = s->links[i];
    }
    for (int i = s->start; i < s->stop; i++) {
        m->link[i] = s->cands[m->voice[i]];
        s->cands[m->voice[i]] = i;
    }
    CostVector cost = {.total = 0.0};
    cost.total += cost.pp = m->pitch_penalty * calculate_pitch_penalty(m, s->start, s->stop, s->cands);
    cost.total += cost.gp = m->gap_penalty * calculate_gap_penalty(m, s);
    cost.total += cost.cp = m->chord_penalty * calculate_chord_penalty(m, s->start, s->stop, s->cands);
    cost.total += cost.op = m->overlap_penalty * calculate_overlap_penalty(m, s);
    cost.total += cost.rp = m->cross_penalty * calculate_cross_penalty(m, s);
    if (m->monitor) {
        m->monitor(m, s->start, s->stop, &cost, stage);
    }
    return cost.total;
}

void lowest_cost_neighbor(Descriptor* m, Slice* s) {
    int voice_index;
    int best_index = s->start;
    int best_voice = m->voice[s->start];
    double best_cost, new_cost;
    best_cost = calculate_total_cost(m, s, 1);
    for (int i = s->start; i < s->stop; i++) {
        voice_index = m->voice[i];
        for (int j = 0; j < m->max_voices; j++) {
            if (j != voice_index) {
                m->voice[i] = j;
                new_cost = calculate_total_cost(m, s, 2);
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
        new_cost = calculate_total_cost(m, s, 3);
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

    if (m->monitor) {
        for (int i = 0; i < s->stop - s->start; i++) {
            m->voice[i+s->start] = best[i];
        }
        calculate_total_cost(m, s, 4);
    }

    for (int i = 0; i < s->stop - s->start; i++) {
        m->voice[i+s->start] = best[i];
        m->link[i+s->start] = s->links[best[i]];
        s->links[best[i]] = i+s->start;
    }

    for (int i = s->start; i < s->stop; i++) {
        s->offsets[m->voice[i]] = fmax(s->offsets[m->voice[i]], m->offset[i]);
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
    while (next_slice(m, &slice.start, &slice.stop)) {
        double onset = m->onset[slice.start];
        for (int i = slice.start; i < slice.stop; i++) {
            if (m->onset[i] - onset > m->chord_spread) {
                chord++;
                onset = m->onset[i];
            }
            m->chord[i] = chord;
        }
        chord++;

        stochastic_local_search(m, &slice);
    }
}
