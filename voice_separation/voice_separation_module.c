#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>
#include "voice_separation.h"

static void monitor_callback(Descriptor *m, int start, int stop, CostVector *cv, int stage) {
    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *py_cb = (PyObject*)m->data;
    if (py_cb && PyCallable_Check(py_cb)) {
        PyObject *voices_list = PyList_New(m->max_voices);
        if (!voices_list) { goto eject; }
        for (int v = 0; v < m->max_voices; ++v) {
            PyObject *lst = PyList_New(0);
            if (!lst) { Py_DECREF(voices_list); voices_list = NULL; goto eject; }
            for (int i = start; i < stop; ++i) {
                if (m->voice[i] == v) {
                    PyObject *note = Py_BuildValue("i", i);
                    PyList_Append(lst, note);
                    Py_DECREF(note);
                }
            }
            PyList_SetItem(voices_list, v, lst);  // steals reference
        }

        PyObject *args = Py_BuildValue("(iiO(ddddd)i)",
            start, stop, voices_list,
            cv->pp, cv->gp, cv->cp, cv->op, cv->rp,
            stage);
        if (!args) { Py_DECREF(voices_list); goto eject; }
        PyObject *result = PyObject_CallObject(py_cb, args);
        Py_DECREF(args);
        Py_DECREF(voices_list);
        if (!result) {
            goto eject;
        } else {
            Py_DECREF(result);
        }
    }
    else {
        PyErr_SetString(PyExc_TypeError, "Descriptor.monitor data is not a callable");
        goto eject;
    }

    PyGILState_Release(gstate);
    return;

    eject: PyGILState_Release(gstate); m->monitor = NULL; m->data = NULL; return;
}

static PyObject*
py_voice_separation(PyObject* self, PyObject* args, PyObject* kwargs)
{
    PyObject *onset_obj = NULL,
             *offset_obj = NULL, *pitch_obj = NULL;
    int    max_voices    = 6;
    double pitch_penalty = 1,
           gap_penalty   = 0.5,
           chord_penalty = 1,
           overlap_penalty = 1,
           cross_penalty = 1,
           chord_spread = 0.0;
    int    pitch_lookback = 2;
    unsigned int lcg       = 0;
    PyObject *py_monitor = NULL;
    PyObject *voices_list = NULL;

    static char *kwlist[] = {
        "onset", "offset", "pitch",
        "max_voices",
        "pitch_penalty", "gap_penalty", "chord_penalty",
        "overlap_penalty", "cross_penalty", "chord_spread",
        "pitch_lookback",
        "seed",
        "monitor",
        NULL
    };

    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs,
            "OOO|iddddddiIO",   // 4 PyObjects, 1 int, 6 doubles, 1 int, then optional unsigned int, and int
            kwlist,
            &onset_obj, &offset_obj, &pitch_obj,
            &max_voices,
            &pitch_penalty, &gap_penalty, &chord_penalty,
            &overlap_penalty, &cross_penalty, &chord_spread,
            &pitch_lookback,
            &lcg,
            &py_monitor))
    {
        return NULL;
    }

    PyArrayObject *onset_arr =
        (PyArrayObject*)PyArray_FROM_OTF(onset_obj,   NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *offset_arr =
        (PyArrayObject*)PyArray_FROM_OTF(offset_obj,  NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    PyArrayObject *pitch_arr =
        (PyArrayObject*)PyArray_FROM_OTF(pitch_obj,   NPY_INT32,  NPY_ARRAY_IN_ARRAY);

    if (!onset_arr || !offset_arr || !pitch_arr) {
        Py_XDECREF(onset_arr);
        Py_XDECREF(offset_arr);
        Py_XDECREF(pitch_arr);
        return NULL;
    }

    int max_notes = (int)PyArray_DIM(onset_arr, 0);
    int n_offset   = (int)PyArray_DIM(offset_arr, 0);
    int n_pitch    = (int)PyArray_DIM(pitch_arr, 0);
    if (max_notes == 0 || max_notes != n_offset || max_notes != n_pitch) {
        PyErr_SetString(PyExc_ValueError,
            "Arrays 'onset', 'offset' and 'pitch' must all have the same nonzero length");
        Py_DECREF(onset_arr);
        Py_DECREF(offset_arr);
        Py_DECREF(pitch_arr);
        return NULL;
    }

    double *duration = calloc(max_notes, sizeof(double));
    int *chord = calloc(max_notes, sizeof(int));
    int *voice = calloc(max_notes, sizeof(int));
    int *link  = calloc(max_notes, sizeof(int));
    if (!duration || !voice || !link) {
        PyErr_NoMemory();
        goto cleanup;
    }

    Descriptor desc;
    desc.max_notes       = max_notes;
    desc.onset           = (double*)PyArray_DATA(onset_arr);
    desc.duration        = duration;
    desc.offset          = (double*)PyArray_DATA(offset_arr);
    desc.position        = (int*)   PyArray_DATA(pitch_arr);
    desc.chord           = chord;
    desc.voice           = voice;
    desc.link            = link;
    desc.max_voices      = max_voices;
    desc.pitch_penalty   = pitch_penalty;
    desc.gap_penalty     = gap_penalty;
    desc.chord_penalty   = chord_penalty;
    desc.overlap_penalty = overlap_penalty;
    desc.cross_penalty   = cross_penalty;
    desc.chord_spread    = chord_spread;
    desc.pitch_lookback  = pitch_lookback;
    desc.lcg             = lcg;
    if (py_monitor != NULL && py_monitor != Py_None) {
        if (!PyCallable_Check(py_monitor)) {
            PyErr_SetString(PyExc_TypeError, "monitor must be callable");
            goto cleanup;
        }
        Py_INCREF(py_monitor);
        desc.monitor = monitor_callback;
        desc.data    = (void*)py_monitor;
    }
    else {
        desc.monitor = NULL;
        desc.data    = NULL;
    }

    for(int i=0; i<max_notes; ++i){
        desc.duration[i] = desc.offset[i] - desc.onset[i];
    }

    voice_separation(&desc);

    if (py_monitor != NULL && py_monitor != Py_None) {
        Py_DECREF(py_monitor);
    }

    if (PyErr_Occurred()) {
        goto cleanup;
    }

    voices_list = PyList_New(max_voices);
    if (!voices_list) goto cleanup;
    for (int v = 0; v < max_voices; ++v) {
        PyObject *lst = PyList_New(0);
        if (!lst) { Py_DECREF(voices_list); voices_list = NULL; goto cleanup; }
        for (int i = 0; i < max_notes; ++i) {
            if (voice[i] == v) {
                PyObject *note = Py_BuildValue("i", i);
                PyList_Append(lst, note);
                Py_DECREF(note);
            }
        }
        PyList_SetItem(voices_list, v, lst);  // steals reference
    }

cleanup:
    free(duration);
    free(chord);
    free(voice);
    free(link);
    Py_DECREF(onset_arr);
    Py_DECREF(offset_arr);
    Py_DECREF(pitch_arr);
    return voices_list;
}

static PyMethodDef VoiceMethods[] = {
    {
        "voice_separation",
        (PyCFunction)py_voice_separation,
        METH_VARARGS | METH_KEYWORDS,
        "Separate notes into voices.\n\n"
        "Required:\n"
        "  onset, offset, pitch (arrays)\n"
        "Optional:\n"
        "  max_voices (int)  # defaults to 6\n"
        "  pitch_penalty, gap_penalty, chord_penalty, # defaults to 1\n"
        "  overlap_penalty, cross_penalty (doubles) # defaults to 1\n"
        "  chord_spread # defaults to 0.0\n"
        "  pitch_lookback (int) # defaults to 2\n\n"
        "  seed (unsigned int)  # PRNG seed, defaults to 0\n"
    },
    { NULL, NULL, 0, NULL }
};

static struct PyModuleDef voice_module = {
    PyModuleDef_HEAD_INIT,
    "voice_separation",
    NULL,
    -1,
    VoiceMethods
};

PyMODINIT_FUNC
PyInit_voice_separation(void)
{
    import_array();
    return PyModule_Create(&voice_module);
}

