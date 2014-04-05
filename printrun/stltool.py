# coding: utf-8

# This file is part of the Printrun suite.
#
# Printrun is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Printrun is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Printrun.  If not, see <http://www.gnu.org/licenses/>.

import sys
import struct
import math

import numpy
import numpy.linalg

def normalize(v):
    return v / numpy.linalg.norm(v)

def genfacet(v):
    veca = v[1] - v[0]
    vecb = v[2] - v[1]
    vecx = numpy.cross(veca, vecb)
    vlen = numpy.linalg.norm(vecx)
    if vlen == 0:
        vlen = 1
    normal = vecx / vlen
    return (normal, v)

I = numpy.identity(4)

def homogeneous(v, w = 1):
    return numpy.append(v, w)

def applymatrix(facet, matrix = I):
    return genfacet(map(lambda x: matrix.dot(homogeneous(x))[:3], facet[1]))

def emitstl(filename, facets = [], objname = "stltool_export", binary = True):
    if filename is None:
        return
    if binary:
        with open(filename, "wb") as f:
            buf = "".join(["\0"] * 80)
            buf += struct.pack("<I", len(facets))
            facetformat = struct.Struct("<ffffffffffffH")
            for facet in facets:
                l = list(facet[0][:])
                for vertex in facet[1]:
                    l += list(vertex[:])
                l.append(0)
                buf += facetformat.pack(*l)
            f.write(buf)
    else:
        with open(filename, "w") as f:
            f.write("solid " + objname + "\n")
            for i in facets:
                f.write("  facet normal " + " ".join(map(str, i[0])) + "\n   outer loop\n")
                for j in i[1]:
                    f.write("    vertex " + " ".join(map(str, j)) + "\n")
                f.write("   endloop" + "\n")
                f.write("  endfacet" + "\n")
            f.write("endsolid " + objname + "\n")

class stl(object):

    _dims = None

    def _get_dims(self):
        if self._dims is None:
            minx = float("inf")
            miny = float("inf")
            minz = float("inf")
            maxx = float("-inf")
            maxy = float("-inf")
            maxz = float("-inf")
            for normal, facet in self.facets:
                for vert in facet:
                    if vert[0] < minx:
                        minx = vert[0]
                    if vert[1] < miny:
                        miny = vert[1]
                    if vert[2] < minz:
                        minz = vert[2]
                    if vert[0] > maxx:
                        maxx = vert[0]
                    if vert[1] > maxy:
                        maxy = vert[1]
                    if vert[2] > maxz:
                        maxz = vert[2]
            self._dims = [minx, maxx, miny, maxy, minz, maxz]
        return self._dims
    dims = property(_get_dims)

    def __init__(self, filename = None):
        self.facet = (numpy.zeros(3), (numpy.zeros(3), numpy.zeros(3), numpy.zeros(3)))
        self.facets = []
        self.facetsminz = []
        self.facetsmaxz = []

        self.name = ""
        self.insolid = 0
        self.infacet = 0
        self.inloop = 0
        self.facetloc = 0
        if filename is None:
            return
        with open(filename) as f:
            data = f.read()
        if "facet normal" in data[1:300] and "outer loop" in data[1:300]:
            lines = data.split("\n")
            for line in lines:
                if not self.parseline(line):
                    return
        else:
            print "Not an ascii stl solid - attempting to parse as binary"
            f = open(filename, "rb")
            buf = f.read(84)
            while len(buf) < 84:
                newdata = f.read(84 - len(buf))
                if not len(newdata):
                    break
                buf += newdata
            facetcount = struct.unpack_from("<I", buf, 80)
            facetformat = struct.Struct("<ffffffffffffH")
            for i in xrange(facetcount[0]):
                buf = f.read(50)
                while len(buf) < 50:
                    newdata = f.read(50 - len(buf))
                    if not len(newdata):
                        break
                    buf += newdata
                fd = list(facetformat.unpack(buf))
                self.name = "binary soloid"
                facet = [fd[:3], [fd[3:6], fd[6:9], fd[9:12]]]
                self.facets.append(facet)
                self.facetsminz.append((min(map(lambda x: x[2], facet[1])), facet))
                self.facetsmaxz.append((max(map(lambda x: x[2], facet[1])), facet))
            f.close()
            return

    def intersect(self, ray_far, ray_near):
        """
        Möller–Trumbore intersection algorithm in pure python
        Based on http://en.wikipedia.org/wiki/M%C3%B6ller%E2%80%93Trumbore_intersection_algorithm
        """
        ray_near = numpy.array(ray_near)
        ray_far = numpy.array(ray_far)
        ray_dir = normalize(ray_far - ray_near)
        best_facet = None
        best_dist = float("inf")
        eps = 0.000001
        for facet_i, (normal, (v1, v2, v3)) in enumerate(self.facets):
            edge1 = v2 - v1
            edge2 = v3 - v1
            pvec = numpy.cross(ray_dir, edge2)
            det = edge1.dot(pvec)
            if abs(det) < eps:
                continue
            inv_det = 1. / det
            tvec = ray_near - v1
            u = tvec.dot(pvec) * inv_det
            if u < 0. or u > 1.:
                continue
            qvec = numpy.cross(tvec, edge1)
            v = ray_dir.dot(qvec) * inv_det
            if v < 0. or u + v > 1.:
                continue

            t = edge2.dot(qvec) * inv_det
            if t < eps:
                continue
            if t < best_dist:
                best_facet = facet_i
                best_dist = t
        return best_facet, best_dist

    def rebase(self, facet_i):
        normal, facet = self.facets[facet_i]
        u1 = facet[1] - facet[0]
        v2 = facet[2] - facet[0]
        n1 = u1.dot(u1)
        e1 = u1 / math.sqrt(n1)
        u2 = v2 - u1 * v2.dot(u1) / n1
        e2 = u2 / numpy.linalg.norm(u2)
        e3 = numpy.cross(e1, e2)
        # Ensure Z direction if opposed to the normal
        if normal.dot(e3) > 0:
            e2 = - e2
            e3 = - e3
        matrix = [[e1[0], e2[0], e3[0], 0],
                  [e1[1], e2[1], e3[1], 0],
                  [e1[2], e2[2], e3[2], 0],
                  [0, 0, 0, 1]]
        matrix = numpy.array(matrix)
        # Inverse change of basis matrix
        matrix = numpy.linalg.inv(matrix)
        # Set first vertex of facet as origin
        neworig = matrix.dot(homogeneous(facet[0]))
        matrix[:3, 3] = -neworig[:3]
        newmodel = self.transform(matrix)
        return newmodel

    def translation_matrix(self, v):
        matrix = [[1, 0, 0, v[0]],
                  [0, 1, 0, v[1]],
                  [0, 0, 1, v[2]],
                  [0, 0, 0, 1]
                  ]
        return numpy.array(matrix)

    def translate(self, v = [0, 0, 0]):
        return self.transform(self.translation_matrix(v))

    def rotation_matrix(self, v):
        z = v[2]
        matrix1 = [[math.cos(math.radians(z)), -math.sin(math.radians(z)), 0, 0],
                   [math.sin(math.radians(z)), math.cos(math.radians(z)), 0, 0],
                   [0, 0, 1, 0],
                   [0, 0, 0, 1]
                   ]
        matrix1 = numpy.array(matrix1)
        y = v[0]
        matrix2 = [[1, 0, 0, 0],
                   [0, math.cos(math.radians(y)), -math.sin(math.radians(y)), 0],
                   [0, math.sin(math.radians(y)), math.cos(math.radians(y)), 0],
                   [0, 0, 0, 1]
                   ]
        matrix2 = numpy.array(matrix2)
        x = v[1]
        matrix3 = [[math.cos(math.radians(x)), 0, -math.sin(math.radians(x)), 0],
                   [0, 1, 0, 0],
                   [math.sin(math.radians(x)), 0, math.cos(math.radians(x)), 0],
                   [0, 0, 0, 1]
                   ]
        matrix3 = numpy.array(matrix3)
        return matrix3.dot(matrix2.dot(matrix1))

    def rotate(self, v = [0, 0, 0]):
        return self.transform(self.rotation_matrix(v))

    def scale_matrix(self, v):
        matrix = [[v[0], 0, 0, 0],
                  [0, v[1], 0, 0],
                  [0, 0, v[2], 0],
                  [0, 0, 0, 1]
                  ]
        return numpy.array(matrix)

    def scale(self, v = [0, 0, 0]):
        return self.transform(self.scale_matrix(v))

    def transform(self, m = I):
        s = stl()
        s.facets = [applymatrix(i, m) for i in self.facets]
        s.insolid = 0
        s.infacet = 0
        s.inloop = 0
        s.facetloc = 0
        s.name = self.name
        for facet in s.facets:
            s.facetsminz += [(min(map(lambda x:x[2], facet[1])), facet)]
            s.facetsmaxz += [(max(map(lambda x:x[2], facet[1])), facet)]
        return s

    def export(self, f = sys.stdout):
        f.write("solid " + self.name + "\n")
        for i in self.facets:
            f.write("  facet normal " + " ".join(map(str, i[0])) + "\n")
            f.write("   outer loop" + "\n")
            for j in i[1]:
                f.write("    vertex " + " ".join(map(str, j)) + "\n")
            f.write("   endloop" + "\n")
            f.write("  endfacet" + "\n")
        f.write("endsolid " + self.name + "\n")
        f.flush()

    def parseline(self, l):
        l = l.strip()
        if l.startswith("solid"):
            self.insolid = 1
            self.name = l[6:]
            # print self.name

        elif l.startswith("endsolid"):
            self.insolid = 0
            return 0
        elif l.startswith("facet normal"):
            l = l.replace(", ", ".")
            self.infacet = 1
            self.facetloc = 0
            normal = numpy.array(map(float, l.split()[2:]))
            self.facet = (normal, (numpy.zeros(3), numpy.zeros(3), numpy.zeros(3)))
        elif l.startswith("endfacet"):
            self.infacet = 0
            self.facets.append(self.facet)
            facet = self.facet
            self.facetsminz += [(min(map(lambda x:x[2], facet[1])), facet)]
            self.facetsmaxz += [(max(map(lambda x:x[2], facet[1])), facet)]
        elif l.startswith("vertex"):
            l = l.replace(", ", ".")
            self.facet[1][self.facetloc][:] = numpy.array(map(float, l.split()[1:]))
            self.facetloc += 1
        return 1

if __name__ == "__main__":
    s = stl("../../Downloads/frame-vertex-neo-foot-x4.stl")
    for i in xrange(11, 11):
        working = s.facets[:]
        for j in reversed(sorted(s.facetsminz)):
            if j[0] > i:
                working.remove(j[1])
            else:
                break
        for j in (sorted(s.facetsmaxz)):
            if j[0] < i:
                working.remove(j[1])
            else:
                break

        print i, len(working)
    emitstl("../../Downloads/frame-vertex-neo-foot-x4-a.stl", s.facets, "emitted_object")
# stl("../prusamendel/stl/mendelplate.stl")
