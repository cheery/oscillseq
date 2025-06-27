#include <Python.h>
#include <structmember.h>
#include <stdlib.h>
#include <stdio.h>
#include <limits.h>
#include <math.h>

// -----------------------------
// Core Data Structures
// -----------------------------

typedef struct AdjList {
    float x, y;      // node coordinates
    int *nodes;      // neighbor indices
    int *costs;      // move costs corresponding to neighbors
    int count;
    int capacity;
} AdjList;

typedef struct {
    int node_count;
    AdjList *adj;
} GraphHandle;

// Priority queue node
typedef struct {
    int f;
    int g;
    int idx;
} PQNode;

// Min-heap structure
typedef struct {
    PQNode *data;
    int size;
    int capacity;
} MinHeap;

// -----------------------------
// Utility: Manhattan Heuristic
// -----------------------------
static inline int manhattan(const GraphHandle *g, int idx1, int idx2) {
    const AdjList *adj = g->adj;
    float dx = fabsf(adj[idx1].x - adj[idx2].x);
    float dy = fabsf(adj[idx1].y - adj[idx2].y);
    return (int)(dx + dy);
}

// -----------------------------
// Min-Heap Implementation
// -----------------------------
static void heap_init(MinHeap *h, int cap) {
    h->data = malloc(sizeof(PQNode) * cap);
    h->size = 0;
    h->capacity = cap;
}

static void heap_push(MinHeap *h, PQNode node) {
    if (h->size >= h->capacity) {
        h->capacity *= 2;
        h->data = realloc(h->data, sizeof(PQNode) * h->capacity);
    }
    int i = h->size++;
    while (i > 0) {
        int p = (i - 1) / 2;
        if (h->data[p].f <= node.f) break;
        h->data[i] = h->data[p];
        i = p;
    }
    h->data[i] = node;
}

static PQNode heap_pop(MinHeap *h) {
    PQNode ret = h->data[0];
    PQNode last = h->data[--h->size];
    int i = 0;
    while (1) {
        int l = 2*i + 1;
        int r = 2*i + 2;
        int s = i;
        if (l < h->size && h->data[l].f < last.f) s = l;
        if (r < h->size && h->data[r].f < h->data[s].f) s = r;
        if (s == i) break;
        h->data[i] = h->data[s];
        i = s;
    }
    h->data[i] = last;
    return ret;
}

static int heap_empty(MinHeap *h) {
    return h->size == 0;
}

// -----------------------------
// A* Routing Implementation
// -----------------------------
static int* do_a_star(const GraphHandle *g, const int *cost_map,
                       int start_idx, int end_idx) {
    int N = g->node_count;
    int *g_scores = malloc(sizeof(int) * N);
    int *prev = malloc(sizeof(int) * N);
    for (int i = 0; i < N; i++) {
        g_scores[i] = INT_MAX;
        prev[i] = -1;
    }

    MinHeap open;
    heap_init(&open, 128);
    g_scores[start_idx] = 0;
    heap_push(&open, (PQNode){.f = manhattan(g, start_idx, end_idx),
                              .g = 0, .idx = start_idx});

    while (!heap_empty(&open)) {
        PQNode cur = heap_pop(&open);
        int u = cur.idx;
        if (u == end_idx) break;
        const AdjList *al = &g->adj[u];
        for (int k = 0; k < al->count; k++) {
            int v = al->nodes[k];
            int cost = al->costs[k] + cost_map[v];
            int ng = cur.g + cost;
            if (ng < g_scores[v]) {
                g_scores[v] = ng;
                prev[v] = u;
                heap_push(&open, (PQNode){.f = ng + manhattan(g, v, end_idx),
                                          .g = ng, .idx = v});
            }
        }
    }
    // backtrack path into dynamically sized array
    int *path = malloc(sizeof(int) * (N + 1));
    int len = 0;
    for (int cur = end_idx; cur != -1; cur = prev[cur]) {
        path[len++] = cur;
    }
    // Do not return degenerate paths.
    if (len == 1) {
        len = 0;
    }
    // reverse
    for (int i = 0; i < len/2; i++) {
        int tmp = path[i]; path[i] = path[len-1-i]; path[len-1-i] = tmp;
    }
    path[len] = -1;

    free(g_scores);
    free(prev);
    free(open.data);
    return path;
}

// -----------------------------
// Capsule Destructor
// -----------------------------
static void graph_handle_destructor(PyObject *capsule) {
    GraphHandle *g = PyCapsule_GetPointer(capsule, "GraphHandle");
    if (!g) return;
    for (int i = 0; i < g->node_count; i++) {
        free(g->adj[i].nodes);
        free(g->adj[i].costs);
    }
    free(g->adj);
    free(g);
}

// -----------------------------
// Python Extension Interface
// -----------------------------
// init_graph(adj_list) -> capsule
static PyObject* py_init_graph(PyObject *self, PyObject *args) {
    PyObject *adj_list;
    if (!PyArg_ParseTuple(args, "O", &adj_list)) return NULL;
    int N = PyList_Size(adj_list);
    GraphHandle *g = malloc(sizeof(GraphHandle));
    g->node_count = N;
    g->adj = calloc(N, sizeof(AdjList));
    for (int i = 0; i < N; i++) {
        PyObject *item = PyList_GetItem(adj_list, i);
        PyObject *coord = PyTuple_GetItem(item, 0);
        PyObject *nodes = PyTuple_GetItem(item, 1);
        PyObject *costs = PyTuple_GetItem(item, 2);
        g->adj[i].x = (float)PyFloat_AsDouble(PyTuple_GetItem(coord, 0));
        g->adj[i].y = (float)PyFloat_AsDouble(PyTuple_GetItem(coord, 1));
        int len = PyList_Size(nodes);
        g->adj[i].count = len;
        g->adj[i].capacity = len;
        g->adj[i].nodes = malloc(len * sizeof(int));
        g->adj[i].costs = malloc(len * sizeof(int));
        for (int j = 0; j < len; j++) {
            g->adj[i].nodes[j] = PyLong_AsLong(PyList_GetItem(nodes, j));
            g->adj[i].costs[j] = PyLong_AsLong(PyList_GetItem(costs, j));
        }
    }
    PyObject *caps = PyCapsule_New(g, "GraphHandle", graph_handle_destructor);
    return caps;
}

// route(cost_map_bytes, handle, start_idx, end_idx) -> list of ints
static PyObject* py_route(PyObject *self, PyObject *args) {
    Py_buffer cost_buf;
    PyObject *caps;
    int start_idx, end_idx;
    if (!PyArg_ParseTuple(args, "y*Oii", &cost_buf, &caps, &start_idx, &end_idx))
        return NULL;
    GraphHandle *g = PyCapsule_GetPointer(caps, "GraphHandle");
    const int *cost_map = (int*)cost_buf.buf;

    int *path = do_a_star(g, cost_map, start_idx, end_idx);
    PyObject *py_path = PyList_New(0);
    for (int i = 0; path[i] != -1; i++) {
        PyList_Append(py_path, PyLong_FromLong(path[i]));
    }
    free(path);
    PyBuffer_Release(&cost_buf);
    return py_path;
}

static PyMethodDef AStarMethods[] = {
    {"init_graph", py_init_graph, METH_VARARGS, "Initialize graph and return handle."},
    {"route", py_route, METH_VARARGS, "Compute path: route(cost_map, handle, start, end)."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef astarmodule = {
    PyModuleDef_HEAD_INIT,
    "astar",
    NULL,
    -1,
    AStarMethods
};

PyMODINIT_FUNC PyInit_astar(void) {
    return PyModule_Create(&astarmodule);
}

