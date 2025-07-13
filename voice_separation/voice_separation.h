#pragma once

typedef struct {
    double total, pp, gp, cp, op, rp;
} CostVector;

typedef struct descriptor {
  int max_notes;
  double *onset;
  double *duration;
  double *offset;
  int    *position;
  int    *chord;
  int    *voice;
  int    *link;
  int max_voices;
  double pitch_penalty;
  double gap_penalty;
  double chord_penalty;
  double overlap_penalty;
  double cross_penalty;
  double chord_spread;
  int pitch_lookback;
  unsigned int lcg;
  void (*monitor)(struct descriptor*, int start, int stop, CostVector*, int stage);
  void *data;
} Descriptor;

void voice_separation(Descriptor*);
