#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <numpy/arrayobject.h>
#include "voice_separation.h"

static PyObject*
py_voice_separation(PyObject* self, PyObject* args, PyObject* kwargs)
{
    PyObject *onset_obj = NULL,
             *offset_obj = NULL, *pitch_obj = NULL;
    int    max_voices    = 6;
    double pitch_penalty = 1,
           gap_penalty   = 1,
           chord_penalty = 1,
           overlap_penalty = 1,
           cross_penalty = 1;
    int    pitch_lookback = 2;
    unsigned int lcg       = 0;

    static char *kwlist[] = {
        "onset", "offset", "pitch",
        "max_voices",
        "pitch_penalty", "gap_penalty", "chord_penalty",
        "overlap_penalty", "cross_penalty",
        "pitch_lookback",
        "seed",
        NULL
    };

    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs,
            "OOO|idddddiI",   // 4 PyObjects, 1 int, 5 doubles, 1 int, then optional unsigned int
            kwlist,
            &onset_obj, &offset_obj, &pitch_obj,
            &max_voices,
            &pitch_penalty, &gap_penalty, &chord_penalty,
            &overlap_penalty, &cross_penalty,
            &pitch_lookback,
            &lcg))
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
    if (max_notes != n_offset || max_notes != n_pitch) {
        PyErr_SetString(PyExc_ValueError,
            "Arrays 'onset', 'offset' and 'pitch' must all have the same length");
        Py_DECREF(onset_arr);
        Py_DECREF(offset_arr);
        Py_DECREF(pitch_arr);
        return NULL;
    }

    double *duration = calloc(max_notes, sizeof(double));
    int *voice = calloc(max_notes, sizeof(int));
    int *link  = calloc(max_notes, sizeof(int));
    if (!duration || !voice || !link) {
        PyErr_NoMemory();
        Py_DECREF(onset_arr);
        Py_DECREF(offset_arr);
        Py_DECREF(pitch_arr);
        free(duration);
        free(voice);
        free(link);
        return NULL;
    }

    Descriptor desc;
    desc.max_notes       = max_notes;
    desc.onset           = (double*)PyArray_DATA(onset_arr);
    desc.duration        = duration;
    desc.offset          = (double*)PyArray_DATA(offset_arr);
    desc.position        = (int*)   PyArray_DATA(pitch_arr);
    desc.voice           = voice;
    desc.link            = link;
    desc.max_voices      = max_voices;
    desc.pitch_penalty   = pitch_penalty;
    desc.gap_penalty     = gap_penalty;
    desc.chord_penalty   = chord_penalty;
    desc.overlap_penalty = overlap_penalty;
    desc.cross_penalty   = cross_penalty;
    desc.pitch_lookback  = pitch_lookback;
    desc.lcg             = lcg;

    for(int i=0; i<max_notes; ++i){
        desc.duration[i] = desc.offset[i] - desc.onset[i];
    }

    voice_separation(&desc);

    PyObject *voices_list = PyList_New(max_voices);
    if (!voices_list) goto cleanup;
    for (int v = 0; v < max_voices; ++v) {
        PyObject *lst = PyList_New(0);
        if (!lst) { Py_DECREF(voices_list); voices_list = NULL; goto cleanup; }
        for (int i = 0; i < max_notes; ++i) {
            if (voice[i] == v) {
                PyObject *note = Py_BuildValue("(d,d,i)",
                    desc.onset[i],
                    desc.offset[i],
                    desc.position[i]
                );
                PyList_Append(lst, note);
                Py_DECREF(note);
            }
        }
        PyList_SetItem(voices_list, v, lst);  // steals reference
    }

cleanup:
    free(duration);
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
        "  overlap_penalty, cross_penalty (floats) # defaults to 1\n"
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

