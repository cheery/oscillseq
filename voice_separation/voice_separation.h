#pragma once

typedef struct {
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
  int pitch_lookback;
  unsigned int lcg;
} Descriptor;

void voice_separation(Descriptor*);
