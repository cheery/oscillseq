#pragma once

typedef struct {
  unsigned int max_notes;
  double *onset;
  double *duration;
  double *offset;
  int    *position;
  int    *chord;
  int    *voice;
  int    *link;
  unsigned max_voices;
  double pitch_penalty;
  double gap_penalty;
  double chord_penalty;
  double overlap_penalty;
  double cross_penalty;
  double chord_spread;
  unsigned int pitch_lookback;
  unsigned int lcg;
  int debug_print;
} Descriptor;

void voice_separation(Descriptor*);
