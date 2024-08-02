
from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from shapely import intersection

class Line():
    def __init__(self, p1, p2):
        self.x1 = p1[0]
        self.y1 = p1[1]
        self.x2 = p2[0]
        self.y2 = p2[1]

def project(point, obj, direction):
    if isinstance(obj, Line):
        l1 = LineString([point, (obj.x1, obj.y1)])
        l2 = LineString([point, (obj.x2, obj.y2)])
        l = max(l1.length, l2.length)
        dl = LineString([(0,0), direction]).length
        d = (direction[0]/dl, direction[1]/dl)
        return intersection(
            LineString([(obj.x1, obj.y1), (obj.x2, obj.y2)]),
            LineString([(point.x, point.y), (point.x + d[0]*l, point.y + d[1]*l)]),
        )

    elif isinstance(obj, Polygon):
        exterior = obj.exterior.coords
        l = len(exterior)
        for i in range(1, l):
            p = project(point, Line(exterior[i-1], exterior[i]), direction)
            if p:
                return p
        return None

if __name__=="__main__":
    p0 = Point(0, 0)

    line = Line((1, 0), (0, 1))
    p = project(p0, line, (1,1))
    assert (p.x, p.y)==(0.5, 0.5), "Line"


    polygon = Polygon([(1,1), (1,2), (2,2), (2,1)])
    p = project(p0, polygon, (1,1))
    assert (p.x, p.y)==(1, 1), "Polygon"

    p = project(p0, polygon, (1,0))
    assert p==None, "Polygon Missed"
