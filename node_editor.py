#import astar
import numpy as np
import math
import time
import random
import pygame
from typing import Tuple, Optional

class WireRouterBuilder:
    def __init__(self, rects):
        self.rects = rects
        self.hlines = []
        self.vlines = []
        if len(rects) > 0:
            self.cover = rects[0].unionall(rects).inflate((100, 100))
        else:
            self.cover = pygame.Rect(0,0, 100, 100)
        for rect in rects:
            rect = rect.inflate((50, 50))
            self.cast_point((rect.centerx, rect.top), down=False)
            self.cast_point((rect.centerx, rect.bottom), up=False)
            self.cast_point((rect.left, rect.centery), right=False)
            self.cast_point((rect.right, rect.centery), left=False)

    def cast_point(self, pt, up=True, right=True, down=True, left=True):
        if up:
            self.cast_ray(pt, (0, -1))
        if right:
            self.cast_ray(pt, (+1, 0))
        if down:
            self.cast_ray(pt, (0, +1))
        if left:
            self.cast_ray(pt, (-1, 0))

    def cast_ray(self, origin, direction):
        p = ray_intersect_aabb(origin, direction,
            self.cover.topleft, self.cover.bottomright)
        if p is None:
            return
        t, x, y = p
        for rect in self.rects:
            if p := ray_intersect_aabb(origin, direction, rect.topleft, rect.bottomright):
                if p[0] <= t:
                    t, x, y = p
        if origin[0] == x:
            self.vlines.append((origin, (x,y)))
        if origin[1] == y:
            self.hlines.append((origin, (x,y)))

    def build(self):
        indices = {}
        adj_list = []
        points = []
        linepoints = {}
        self.hlines.sort(key=lambda x: x[0][1])
        self.vlines.sort(key=lambda x: x[0][0])

        def connect(p, q):
            if p not in indices:
                indices[p] = len(adj_list)
                adj_list.append((p, [], []))
                points.append(p)
            if q not in indices:
                indices[q] = len(adj_list)
                adj_list.append((q, [], []))
                points.append(q)
            dist = manhattan(p, q)
            i, j = indices[p], indices[q]
            adj_list[i][1].append(j)
            adj_list[i][2].append(dist)
            adj_list[j][1].append(i)
            adj_list[j][2].append(dist)

        for p0, p1 in self.hlines:
            q = None
            for ki, (q0, q1) in enumerate(self.vlines):
                if not (min(q0[1], q1[1]) <= p0[1] <= max(q0[1], q1[1])):
                    continue
                if not (min(p0[0], p1[0]) <= q0[0] <= max(p0[0], p1[0])):
                    continue
                p = q0[0], p0[1]
                if q:
                    connect(p, q)
                if ki in linepoints:
                    s = linepoints[ki]
                    connect(s, p)
                linepoints[ki] = p
                q = p

        cost_map = np.zeros(len(adj_list), dtype=np.int32)
        #return WireRouter(cost_map,
        #    adj_map = astar.init_graph(adj_list),
        #    points = points)
        return PurePythonWireRouter(cost_map,
            adj_map = adj_list,
            points = points)

class PurePythonWireRouter:
    def __init__(self, cost_map, adj_map, points):
        self.cost_map = cost_map
        self.adj_map = adj_map
        self.points = points

    def get_nearest(self, point):
        return min(((i, manhattan(point, p))
                    for i, p in enumerate(self.points)), key=lambda x: x[1])[0]

    def route(self, start, end, add_cost=True):
        i = self.get_nearest(start)
        j = self.get_nearest(end)
        path = self.pathfind(i, j)
        if add_cost:
            for i in path:
                self.cost_map[i] += 50
        return Wire(self, start, path, end)

    def pathfind(self, start, end):
        import heapq
        adj_map = self.adj_map
        costfn = lambda i, j: manhattan(adj_map[i][0], adj_map[j][0])
        def dirfn(i, j):
            x0, y0 = adj_map[i][0]
            x1, y1 = adj_map[j][0]
            return int(math.atan2(x1-x0, y1-y0) * 2 / math.pi + 1)
        open_set = []
        g_scores = {start: 0}
        heapq.heappush(open_set, (costfn(start, end), 0, start, None))
        prev = {}
        end_state = None
        while open_set:
            f, g_cost, i, pdir = heapq.heappop(open_set)
            if i == end:
                end_state = i
                break
            for j, move_cost in zip(adj_map[i][1], adj_map[i][2]):
                d = dirfn(i, j)
                move_cost += self.cost_map[j]
                if pdir is not None and pdir != d:
                    move_cost += 200
                new_g = g_cost + move_cost
                if new_g < g_scores.get(j, float('inf')):
                    g_scores[j] = new_g
                    heapq.heappush(open_set, (new_g + costfn(j, end), new_g, j, d))
                    prev[j] = i
        # Build grid path (always returns at least two points)
        if end_state is not None:
            path = []
            cur = end_state
            while cur in prev:
                path.append(cur)
                cur = prev[cur]
            path.append(start)
            path.reverse()
            return path
        else:
            return []

#class WireRouter:
#    def __init__(self, cost_map, adj_map, points):
#        self.cost_map = cost_map
#        self.adj_map = adj_map
#        self.points = points
#
#    def get_nearest(self, point):
#        return min(((i, manhattan(point, p))
#                    for i, p in enumerate(self.points)), key=lambda x: x[1])[0]
#
#    def route(self, start, end, add_cost=True):
#        i = self.get_nearest(start)
#        j = self.get_nearest(end)
#        path = astar.route(self.cost_map, self.adj_map, i, j)
#        if add_cost:
#            for i in path:
#                self.cost_map[i] += 50
#        return Wire(self, start, path, end)

class Wire:
    def __init__(self, router, start, path, end):
        self.router = router
        self.start = start
        self.path = path
        self.end = end

        base_path = [start] + [self.router.points[i] for i in self.path] + [end]
        self.pts = smooth(spread(base_path, 25), 2)

    def __iter__(self):
        return iter(self.pts)

def manhattan(p, q):
    return abs(p[0] - q[0]) + abs(p[1] - q[1])

def spread(P, n):
    P = np.asarray(P, dtype=float)
    diffs = np.diff(P, axis=0)                      # shape (N-1, D)
    seg_lengths = np.sqrt((diffs**2).sum(axis=1))   # shape (N-1,)
    cumlen = np.concatenate(([0], np.cumsum(seg_lengths)))  # shape (N,)
    total_len = cumlen[-1]
    n = int(total_len / n)
    if n < 2:
        return np.array([P[0], P[-1]])
    target = np.linspace(0, total_len, n)
    Q = np.empty((n, P.shape[1]))
    for dim in range(P.shape[1]):
        Q[:, dim] = np.interp(target, cumlen, P[:, dim])
    return Q

def smooth(P, n=1):
    for _ in range(n):
        a = P
        b = np.roll(P,  1, axis=0)
        c = np.roll(P, -1, axis=0)
        b[0] = c[0] = a[0]
        b[-1] = c[-1] = a[-1]
        P = (a+b+c)/3
    return P

def ray_intersect_aabb(
    origin: Tuple[float, float],
    direction: Tuple[float, float],
    aabb_min: Tuple[float, float],
    aabb_max: Tuple[float, float]
) -> Optional[Tuple[float, float, float]]:
    """
    Calculate the intersection of a 2D ray and an axis-aligned bounding box (AABB).

    Parameters:
    - origin: (ox, oy) the starting point of the ray
    - direction: (dx, dy) the normalized direction vector of the ray
    - aabb_min: (min_x, min_y) the minimum corner of the AABB
    - aabb_max: (max_x, max_y) the maximum corner of the AABB

    Returns:
    - None if there is no intersection
    - Otherwise, a tuple (t_near, ix, iy) where:
        * t_near is the distance along the ray to the first intersection point
        * (ix, iy) is the intersection point coordinates

    Algorithm: Slab method
    """
    ox, oy = origin
    dx, dy = direction

    t_min = -math.inf  # furthest near intersection
    t_max = math.inf   # nearest far intersection

    # X slab
    if abs(dx) < 1e-8:
        # Ray is parallel to X slab. If origin not within slab, no hit.
        if ox < aabb_min[0] or ox > aabb_max[0]:
            return None
    else:
        inv_dx = 1.0 / dx
        t1 = (aabb_min[0] - ox) * inv_dx
        t2 = (aabb_max[0] - ox) * inv_dx
        t_near = min(t1, t2)
        t_far = max(t1, t2)
        t_min = max(t_min, t_near)
        t_max = min(t_max, t_far)
        if t_min > t_max:
            return None

    # Y slab
    if abs(dy) < 1e-8:
        if oy < aabb_min[1] or oy > aabb_max[1]:
            return None
    else:
        inv_dy = 1.0 / dy
        t1 = (aabb_min[1] - oy) * inv_dy
        t2 = (aabb_max[1] - oy) * inv_dy
        t_near = min(t1, t2)
        t_far = max(t1, t2)
        t_min = max(t_min, t_near)
        t_max = min(t_max, t_far)
        if t_min > t_max:
            return None

    # If t_max < 0, the AABB is behind the ray
    if t_max < 0:
        return None

    # Intersection occurs at t_min (entering point)
    t_hit = t_min if t_min >= 0 else t_max
    ix = ox + dx * t_hit
    iy = oy + dy * t_hit

    return (t_hit, ix, iy)

def line_intersect_line(
    p0: Tuple[float, float], p1: Tuple[float, float],
    q0: Tuple[float, float], q1: Tuple[float, float]
) -> Optional[Tuple[float, float]]:
    """
    Compute intersection point of two line segments (p0->p1 and q0->q1).
    Returns the intersection point as (x, y), or None if there is no intersection.
    """
    x1, y1 = p0
    x2, y2 = p1
    x3, y3 = q0
    x4, y4 = q1

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-8:
        return None  # Lines are parallel or coincident

    px = ((x1*y2 - y1*x2)*(x3 - x4) - (x1 - x2)*(x3*y4 - y3*x4)) / denom
    py = ((x1*y2 - y1*x2)*(y3 - y4) - (y1 - y2)*(x3*y4 - y3*x4)) / denom

    # Check if intersection is within both segments
    if (min(x1, x2) - 1e-8 <= px <= max(x1, x2) + 1e-8 and
        min(y1, y2) - 1e-8 <= py <= max(y1, y2) + 1e-8 and
        min(x3, x4) - 1e-8 <= px <= max(x3, x4) + 1e-8 and
        min(y3, y4) - 1e-8 <= py <= max(y3, y4) + 1e-8):
        return (px, py)

    return None

