from kikit import panelize, substrate
from kikit.defs import Layer
from kikit.units import mm, mil
from kikit.common import *
from kikit.substrate import NoIntersectionError, TabFilletError, closestIntersectionPoint, biteBoundary
import numpy as np
import shapely
from shapely.geometry import Point, Polygon, MultiPolygon, LineString, GeometryCollection, box
from shapely import transform, distance, affinity
import pcbnew
import math
from enum import Enum
import traceback
import os
import sys
import json
from PUI.PySide6 import *

VC_EXTENT = 3
PNL_SUFFIX = ".kikit_pnl"
PCB_SUFFIX = ".kicad_pcb"

class Tool(Enum):
    NONE = 0
    TAB = 1
class Direction(Enum):
    Up = 0
    Down = 1
    Left = 2
    Right = 3

def nbbox(x1, y1, x2, y2):
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

class PCB(StateObject):
    def __init__(self, boardfile):
        super().__init__()
        boardfile = os.path.realpath(boardfile)
        self.file = boardfile
        board = pcbnew.LoadBoard(boardfile)

        panel = panelize.Panel("")
        panel.appendBoard(
            boardfile,
            pcbnew.VECTOR2I(0, 0),
            origin=panelize.Origin.TopLeft,
            tolerance=panelize.fromMm(1),
            rotationAngle=pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T),
            inheritDrc=False
        )
        s = panel.substrates[0]
        bbox = s.bounds()

        if isinstance(s.substrates, MultiPolygon):
            self._shapes = s.substrates.geoms
        elif isinstance(s.substrates, Polygon):
            self._shapes = [s.substrates]
        else:
            self._shapes = []

        folder = os.path.basename(os.path.dirname(boardfile))
        name = os.path.splitext(os.path.basename(boardfile))[0]
        if folder != name:
            name = os.path.join(folder, name)
        self.ident = name

        self.x = 0
        self.y = 0
        self.width = bbox[2] - bbox[0]
        self.height = bbox[3] - bbox[1]
        self.rotate = 0

    @property
    def shapes(self):
        ret = []
        for shape in self._shapes:
            shape = affinity.rotate(shape, self.rotate*-1, origin=(0,0))
            shape = transform(shape, lambda x: x+[self.x, self.y])
            ret.append(shape)
        return ret

    def clone(self):
        pcb = PCB(self.file)
        pcb.rotate = self.rotate
        return pcb

    def distance(self, obj, pos_x, pos_y):
        mdist = None
        for shape in self.shapes:
            shape = transform(shape, lambda x: x+[pos_x, pos_y])
            dist = distance(shape, obj)
            if mdist is None:
                mdist = dist
            else:
                mdist = min(mdist, dist)
        return mdist

    def rotateCCW(self):
        x, y = self.center
        self.rotate = self.rotate + 90
        self.setCenter((x, y))

    def rotateCW(self):
        x, y = self.center
        self.rotate = self.rotate - 90
        self.setCenter((x, y))

    def setTop(self, top):
        if round(self.rotate/90) % 4 == 0:
            self.y = top
        elif round(self.rotate/90) % 4 == 1:
            self.y = top + self.width
        elif round(self.rotate/90) % 4 == 2:
            self.y = top + self.height
        elif round(self.rotate/90) % 4 == 3:
            self.y = top

    def setBottom(self, bottom):
        if round(self.rotate/90) % 4 == 0:
            self.y = bottom - self.height
        elif round(self.rotate/90) % 4 == 1:
            self.y = bottom
        elif round(self.rotate/90) % 4 == 2:
            self.y = bottom
        elif round(self.rotate/90) % 4 == 3:
            self.y = bottom - self.width

    def setLeft(self, left):
        if round(self.rotate/90) % 4 == 0:
            self.x = left
        elif round(self.rotate/90) % 4 == 1:
            self.x = left
        elif round(self.rotate/90) % 4 == 2:
            self.x = left + self.width
        elif round(self.rotate/90) % 4 == 3:
            self.x = left + self.height

    def setRight(self, right):
        if round(self.rotate/90) % 4 == 0:
            self.x = right - self.width
        elif round(self.rotate/90) % 4 == 1:
            self.x = right - self.height
        elif round(self.rotate/90) % 4 == 2:
            self.x = right
        elif round(self.rotate/90) % 4 == 3:
            self.x = right

    @property
    def center(self):
        x1, y1, x2, y2 = self.nbbox
        return (x1+x2)/2, (y1+y2)/2

    def setCenter(self, value):
        self.setLeft(value[0] - self.rwidth/2)
        self.setTop(value[1] - self.rheight/2)

    @property
    def rwidth(self):
        x1, y1, x2, y2 = self.bbox
        return abs(x2 - x1)

    @property
    def rheight(self):
        x1, y1, x2, y2 = self.bbox
        return abs(y2 - y1)

    @property
    def bbox(self):
        if round(self.rotate/90) % 4 == 0:
            x1, y1, x2, y2 = self.x, self.y, self.x+self.width, self.y+self.height
        elif round(self.rotate/90) % 4 == 1:
            x1, y1, x2, y2 = self.x, self.y, self.x+self.height, self.y-self.width
        elif round(self.rotate/90) % 4 == 2:
            x1, y1, x2, y2 = self.x, self.y, self.x-self.width, self.y-self.height
        elif round(self.rotate/90) % 4 == 3:
            x1, y1, x2, y2 = self.x, self.y, self.x-self.height, self.y+self.width
        return x1, y1, x2, y2

    @property
    def nbbox(self):
        return nbbox(*self.bbox)

# Modified from tab() in kikit:
# 1. Don't stop at first hit substrate, it may not be the closest one
# 2. Fix origin inside a hole
def autotabs(boardSubstrate, origin, direction, width,
            maxHeight=pcbnew.FromMM(50), fillet=0):
    """
    Create a tab for the substrate. The tab starts at the specified origin
    (2D point) and tries to penetrate existing substrate in direction (a 2D
    vector). The tab is constructed with given width. If the substrate is
    not penetrated within maxHeight, exception is raised.

    When partitionLine is specified, the tab is extended to the opposite
    side - limited by the partition line. Note that if tab cannot span
    towards the partition line, then the tab is not created - it returns a
    tuple (None, None).

    If a fillet is specified, it allows you to add fillet to the tab of
    specified radius.

    Returns a pair tab and cut outline. Add the tab it via union - batch
    adding of geometry is more efficient.
    """
    boardSubstrate.orient()

    if boardSubstrate.substrates.contains(Point(origin)) and not boardSubstrate.substrates.boundary.contains(Point(origin)):
        print(origin, direction, ["Tab annotation is placed inside the board. It has to be on edge or outside the board."])
        return []

    origin = np.array(origin)
    direction = np.around(normalize(direction), 4)
    tabs = []
    for geom in listGeometries(boardSubstrate.substrates):
        try:
            sideOriginA = origin + makePerpendicular(direction) * width / 2
            sideOriginB = origin - makePerpendicular(direction) * width / 2
            boundary = geom.exterior
            splitPointA = closestIntersectionPoint(sideOriginA, direction,
                boundary, maxHeight)
            splitPointB = closestIntersectionPoint(sideOriginB, direction,
                boundary, maxHeight)
            tabFace = biteBoundary(boundary, splitPointB, splitPointA)
            # There is nothing else to do, return the tab
            tab = Polygon(list(tabFace.coords) + [sideOriginA, sideOriginB])
            tabs.append(boardSubstrate._makeTabFillet(tab, tabFace, fillet))

            for boundary in geom.interiors:
                splitPointA = closestIntersectionPoint(sideOriginA, direction,
                    boundary, maxHeight)
                splitPointB = closestIntersectionPoint(sideOriginB, direction,
                    boundary, maxHeight)
                tabFace = biteBoundary(boundary, splitPointB, splitPointA)
                # There is nothing else to do, return the tab
                tab = Polygon(list(tabFace.coords) + [sideOriginA, sideOriginB])
                tabs.append(boardSubstrate._makeTabFillet(tab, tabFace, fillet))


        except NoIntersectionError as e:
            continue
        except TabFilletError as e:
            continue
    return tabs

def autotab(boardSubstrate, origin, direction, width,
            maxHeight=pcbnew.FromMM(50), fillet=0):
    tabs = autotabs(boardSubstrate, origin, direction, width, maxHeight, fillet)
    if tabs:
        if direction[0]==0: # vertical
            if direction[1] < 0: # up
                tabs.sort(key=lambda t: -t[0].bounds[1])
            elif direction[1] > 0: # down
                tabs.sort(key=lambda t: t[0].bounds[3])
        elif direction[1]==0: # horizontal
            if direction[0] < 0: # left
                tabs.sort(key=lambda t: -t[0].bounds[0])
            elif direction[0] > 0: # right
                tabs.sort(key=lambda t: t[0].bounds[2])
        return tabs[0]
    return None

class UI(Application):
    def __init__(self):
        super().__init__()

        self.unit = mm

        self.state = State()
        self.state.debug = False
        self.state.show_mb = True
        self.state.show_vc = True

        self.state.pcb = []
        self.state.scale = (0, 0, 1)

        self.state.target_path = ""
        self.state.export_path = ""

        self.state.canvas_width = 800
        self.state.canvas_height = 800

        self.state.focus = None

        self.state.vcuts = []
        self.state.bites = []
        self.state.dbg_points = []
        self.state.dbg_rects = []
        self.state.dbg_text = []
        self.state.substrates = []
        self.state.conflicts = []

        self.state.use_frame = True
        self.state.tight = True
        self.state.auto_tab = True
        self.state.spacing = 1.6
        self.state.max_tab_spacing = 50.0
        self.state.cut_method = "auto"
        self.state.mb_diameter = 0.6
        self.state.mb_spacing = round(0.3 + self.state.mb_diameter, 1)
        mb_count = 5
        self.state.tab_width = math.ceil((self.state.mb_spacing * (mb_count-1)) * 10) / 10
        self.state.vc_layer = "Cmts.User"
        self.state.frame_width = 100
        self.state.frame_height = 100
        self.state.frame_top = 5
        self.state.frame_bottom = 5
        self.state.frame_left = 0
        self.state.frame_right = 0
        self.state.mill_fillets = 0.5

        self.state.boardSubstrate = None

        self.mousepos = None
        self.mouse_dragging = None
        self.mousehold = False
        self.tool = Tool.NONE
        self.tool_args = None

    def autoScale(self):
        x1, y1 = 0, 0
        x2, y2 = self.state.frame_width * self.unit, self.state.frame_height * self.unit
        for pcb in self.state.pcb:
            bbox = pcb.nbbox
            x1 = min(x1, bbox[0])
            y1 = min(y1, bbox[1])
            x2 = max(x2, bbox[2])
            y2 = max(y2, bbox[3])

        dw = x2-x1
        dh = y2-y1

        if dw == 0 or dh == 0:
            return

        cw = self.state.canvas_width
        ch = self.state.canvas_height
        sw = cw / dw
        sh = ch / dh
        scale = min(sw, sh) * 0.75
        self.scale = scale
        offx = (cw - (dw+x1) * scale) / 2
        offy = (ch - (dh+y1) * scale) / 2
        self.state.scale = (offx, offy, scale)

    def addPCB(self):
        boardfile = OpenFile("Open PCB", "KiCad PCB (*.kicad_pcb)")
        if boardfile:
            self._addPCB(PCB(boardfile))

    def _addPCB(self, pcb):
        if len(self.state.pcb) > 0:
            last = self.state.pcb[-1]
            pcb.y = last.y + last.rheight + self.state.spacing * self.unit
        else:
            pcb.y = (self.state.frame_top + self.state.spacing if self.state.frame_top > 0 else 0) * self.unit
        self.state.pcb.append(pcb)
        self.autoScale()
        self.build()

    def duplicate(self, pcb):
        self._addPCB(pcb.clone())

    def remove(self, pcb):
        self.state.pcb = [p for p in self.state.pcb if p is not pcb]
        self.autoScale()
        self.build()

    def save(self, target=None):
        if target is None:
            print(self.state.target_path)
            target = SaveFile(self.state.target_path, "KiKit Panelization (*.kikit_pnl)")
        if not target:
            return

        suffix = ".kikit_pnl"
        if not target.endswith(suffix):
            target += suffix

        target = os.path.realpath(target)

        self.state.target_path = target

        pcbs = []
        for pcb in self.state.pcb:
            try:
                file = os.path.relpath(pcb.file, os.path.dirname(target))
            except ValueError:
                file = pcb.file
            pcbs.append({
                "file": file,
                "x": pcb.x,
                "y": pcb.y,
                "rotate": pcb.rotate,
            })
        data = {
            "use_frame": self.state.use_frame,
            "tight": self.state.tight,
            "auto_tab": self.state.auto_tab,
            "spacing": self.state.spacing,
            "max_tab_spacing": self.state.max_tab_spacing,
            "cut_method": self.state.cut_method,
            "mb_diameter": self.state.mb_diameter,
            "mb_spacing": self.state.mb_spacing,
            "tab_width": self.state.tab_width,
            "vc_layer": self.state.vc_layer,
            "frame_width": self.state.frame_width,
            "frame_height": self.state.frame_height,
            "frame_top": self.state.frame_top,
            "frame_bottom": self.state.frame_bottom,
            "frame_left": self.state.frame_left,
            "frame_right": self.state.frame_right,
            "mill_fillets": self.state.mill_fillets,
            "pcb": pcbs,
        }
        with open(target, "w") as f:
            json.dump(data, f, indent=4)


    def load(self, target=None):
        if target is None:
            target = OpenFile("Load Panelization", "KiKit Panelization (*.kikit_pnl)")
        if target:
            target = os.path.realpath(target)
            self.state.target_path = target
        else:
            return

        with open(target, "r") as f:
            data = json.load(f)
            if "use_frame" in data:
                self.state.use_frame = data["use_frame"]
            if "tight" in data:
                self.state.tight = data["tight"]
            if "auto_tab" in data:
                self.state.auto_tab = data["auto_tab"]
            if "spacing" in data:
                self.state.spacing = data["spacing"]
            if "max_tab_spacing" in data:
                self.state.max_tab_spacing = data["max_tab_spacing"]
            if "cut_method" in data:
                self.state.cut_method = data["cut_method"]
            if "mb_diameter" in data:
                self.state.mb_diameter = data["mb_diameter"]
            if "mb_spacing" in data:
                self.state.mb_spacing = data["mb_spacing"]
            if "tab_width" in data:
                self.state.tab_width = data["tab_width"]
            if "vc_layer" in data:
                self.state.vc_layer = data["vc_layer"]
            if "frame_width" in data:
                self.state.frame_width = data["frame_width"]
            if "frame_height" in data:
                self.state.frame_height = data["frame_height"]
            if "frame_top" in data:
                self.state.frame_top = data["frame_top"]
            if "frame_bottom" in data:
                self.state.frame_bottom = data["frame_bottom"]
            if "frame_left" in data:
                self.state.frame_left = data["frame_left"]
            if "frame_right" in data:
                self.state.frame_right = data["frame_right"]
            if "mill_fillets" in data:
                self.state.mill_fillets = data["mill_fillets"]

            self.state.pcb = []
            for p in data.get("pcb", []):
                file = p["file"]
                if not os.path.isabs(file):
                    file = os.path.realpath(os.path.join(os.path.dirname(target), file))
                pcb = PCB(file)
                pcb.x = p["x"]
                pcb.y = p["y"]
                pcb.rotate = p["rotate"]
                self.state.pcb.append(pcb)
            self.autoScale()
            self.build()

    def build(self, export=False):
        pcbs = self.state.pcb
        if len(pcbs) == 0:
            return

        spacing = self.state.spacing
        tab_width = self.state.tab_width
        max_tab_spacing = self.state.max_tab_spacing
        mb_diameter = self.state.mb_diameter
        mb_spacing = self.state.mb_spacing

        if export is True:
            export = SaveFile(self.state.export_path, "KiCad PCB (*.kicad_pcb)")
            if export:
                if not export.endswith(PCB_SUFFIX):
                    export += PCB_SUFFIX
                self.state.export_path = export
            else:
                return
        elif export:
            if not export.endswith(PCB_SUFFIX):
                export += PCB_SUFFIX
            self.state.export_path = export

        pos_x = 0
        pos_y = 0

        if export:
            pos_x = 20 * self.unit
            pos_y = 20 * self.unit

        panel = panelize.Panel(self.state.export_path)
        panel.vCutLayer = {
            "Edge.Cuts": Layer.Edge_Cuts,
            "User.1": Layer.User_1,
        }.get(self.state.vc_layer, Layer.Cmts_User)


        if self.state.use_frame and self.state.frame_top > 0:
            frame_top_polygon = Polygon([
                [pos_x, pos_y],
                [pos_x+self.state.frame_width*self.unit, pos_y],
                [pos_x+self.state.frame_width*self.unit, pos_y+self.state.frame_top*self.unit],
                [pos_x, pos_y+self.state.frame_top*self.unit],
            ])
        else:
            frame_top_polygon = None

        if self.state.use_frame and self.state.frame_bottom > 0:
            frame_bottom_polygon = Polygon([
                [pos_x, pos_y+self.state.frame_height*self.unit],
                [pos_x+self.state.frame_width*self.unit, pos_y+self.state.frame_height*self.unit],
                [pos_x+self.state.frame_width*self.unit, pos_y+self.state.frame_height*self.unit-self.state.frame_bottom*self.unit],
                [pos_x, pos_y+self.state.frame_height*self.unit-self.state.frame_bottom*self.unit],
            ])
        else:
            frame_bottom_polygon = None

        if self.state.use_frame and self.state.frame_left > 0:
            frame_left_polygon = Polygon([
                [pos_x, pos_y],
                [pos_x, pos_y+self.state.frame_height*self.unit],
                [pos_x+self.state.frame_left*self.unit, pos_y+self.state.frame_height*self.unit],
                [pos_x+self.state.frame_left*self.unit, pos_y],
            ])
        else:
            frame_left_polygon = None

        if self.state.use_frame and self.state.frame_right > 0:
            frame_right_polygon = Polygon([
                [pos_x+self.state.frame_width*self.unit, pos_y],
                [pos_x+self.state.frame_width*self.unit, pos_y+self.state.frame_height*self.unit],
                [pos_x+self.state.frame_width*self.unit-self.state.frame_right*self.unit, pos_y+self.state.frame_height*self.unit],
                [pos_x+self.state.frame_width*self.unit-self.state.frame_right*self.unit, pos_y],
            ])
        else:
            frame_right_polygon = None

        boundarySubstrates = []
        if self.state.use_frame and not self.state.tight:
            if frame_top_polygon:
                panel.appendSubstrate(frame_top_polygon)
                sub = substrate.Substrate([])
                sub.union(frame_top_polygon)
                boundarySubstrates.append(sub)
            if frame_bottom_polygon:
                panel.appendSubstrate(frame_bottom_polygon)
                sub = substrate.Substrate([])
                sub.union(frame_bottom_polygon)
                boundarySubstrates.append(sub)
            if frame_left_polygon:
                panel.appendSubstrate(frame_left_polygon)
                sub = substrate.Substrate([])
                sub.union(frame_left_polygon)
                boundarySubstrates.append(sub)
            if frame_right_polygon:
                panel.appendSubstrate(frame_right_polygon)
                sub = substrate.Substrate([])
                sub.union(frame_right_polygon)
                boundarySubstrates.append(sub)

        for pcb in pcbs:
            x1, y1, x2, y2 = pcb.bbox
            panel.appendBoard(
                pcb.file,
                pcbnew.VECTOR2I(round(pos_x + x1), round(pos_y + y1)),
                origin=panelize.Origin.TopLeft,
                tolerance=panelize.fromMm(1),
                rotationAngle=pcbnew.EDA_ANGLE(pcb.rotate, pcbnew.DEGREES_T),
                inheritDrc=False
            )

        if self.state.tight:
            x1, y1, x2, y2 = nbbox(*pcbs[0].bbox)
            x1 += pos_x
            y1 += pos_y
            x2 += pos_x
            y2 += pos_y

            if self.state.use_frame:
                x1 = min(x1, pos_x)
                y1 = min(y1, pos_y)
                x2 = max(x2, pos_x + self.state.frame_width*self.unit)
                y2 = max(y2, pos_y + self.state.frame_height*self.unit)

            for pcb in pcbs[1:]:
                bbox = pcb.nbbox
                x1 = min(x1, pos_x+bbox[0])
                y1 = min(y1, pos_y+bbox[1])
                x2 = max(x2, pos_x+bbox[2])
                y2 = max(y2, pos_y+bbox[3])

            # board hole
            frameBody = box(x1, y1, x2, y2)
            for s in panel.substrates:
                frameBody = frameBody.difference(s.exterior().buffer(spacing*self.unit, join_style="mitre"))
            panel.appendSubstrate(frameBody)

        dbg_points = []
        dbg_rects = []
        dbg_text = []
        tabs = []
        cuts = []

        # (x, y), inward_direction, score_divider
        tab_candidates = []

        x_parts = []
        y_parts = []
        for pcb in pcbs:
            x1, y1, x2, y2 = pcb.nbbox
            x_parts.append(x1)
            y_parts.append(y1)

        if self.state.auto_tab and max_tab_spacing > 0:
            for pcb in pcbs:
                bboxes = [p.nbbox for p in pcbs if p is not pcb]
                if self.state.use_frame:
                    if self.state.tight:
                        bboxes.append((0, 0, self.state.frame_width*self.unit, self.state.frame_height*self.unit))
                    else:
                        if self.state.frame_top > 0:
                            bboxes.append((0, 0, self.state.frame_width*self.unit, self.state.frame_top*self.unit))
                        if self.state.frame_bottom > 0:
                            bboxes.append((0, self.state.frame_height*self.unit-self.state.frame_bottom*self.unit, self.state.frame_width*self.unit, self.state.frame_height*self.unit))
                        if self.state.frame_left > 0:
                            bboxes.append((0, 0, self.state.frame_left*self.unit, self.state.frame_height*self.unit))
                        if self.state.frame_right > 0:
                            bboxes.append((self.state.frame_width*self.unit-self.state.frame_right*self.unit, 0, self.state.frame_width*self.unit, self.state.frame_height*self.unit))

                x1, y1, x2, y2 = pcb.nbbox
                row_bboxes = [(b[0],b[2]) for b in bboxes if LineString([(0, b[1]), (0, b[3])]).intersects(LineString([(0, y1), (0, y2)]))]
                col_bboxes = [(b[1],b[3]) for b in bboxes if LineString([(b[0], 0), (b[2], 0)]).intersects(LineString([(x1, 0), (x2, 0)]))]

                # top
                if col_bboxes and y1 != min([b[0] for b in col_bboxes]):
                    n = math.ceil((x2-x1) / (max_tab_spacing*self.unit))+1
                    for i in range(1,n):
                        p = (pos_x + x1 + (x2-x1)*i/n, pos_y + y1 - spacing/2*self.unit)
                        partition = len([x for x in x_parts if x < p[0]])
                        tab_candidates.append((p, (0,1), partition, (x2-x1)/n))

                # bottom
                if col_bboxes and y2 != max([b[1] for b in col_bboxes]):
                    n = math.ceil((x2-x1) / (max_tab_spacing*self.unit))+1
                    for i in range(1,n):
                        p = (pos_x + x1 + (x2-x1)*i/n, pos_y + y2 + spacing/2*self.unit)
                        partition = len([x for x in x_parts if x < p[0]])
                        tab_candidates.append((p, (0,-1), partition, (x2-x1)/n))

                # left
                if row_bboxes and x1 != min([b[0] for b in row_bboxes]):
                    n = math.ceil((y2-y1) / (max_tab_spacing*self.unit))+1
                    for i in range(1,n):
                        p = (pos_x + x1 - spacing/2*self.unit , pos_y + y1 + (y2-y1)*i/n)
                        partition = len([y for y in y_parts if y < p[1]])
                        tab_candidates.append((p, (1,0), partition, (y2-y1)/n))

                # right
                if row_bboxes and x2 != max([b[1] for b in row_bboxes]):
                    n = math.ceil((y2-y1) / (max_tab_spacing*self.unit))+1
                    for i in range(1,n):
                        p = (pos_x + x2 + spacing/2*self.unit , pos_y + y1 + (y2-y1)*i/n)
                        partition = len([y for y in y_parts if y < p[1]])
                        tab_candidates.append((p, (-1,0), partition, (y2-y1)/n))

        tab_candidates.sort(key=lambda t: t[3]) # sort by divided edge length

        for p, inward_direction, partiion, score_divider in tab_candidates:
            dbg_points.append((p, 1))

        tab_substrates = []
        # x, y, abs(direction)
        tabs = []
        tab_dist = max_tab_spacing*self.unit/3
        for p, inward_direction, partiion, score_divider in tab_candidates:
            # prevent overlapping tabs
            if len([t for t in tabs if
                    (abs(inward_direction[0]), abs(inward_direction[1]))==(abs(t[2][0]), abs(t[2][1])) # same axis
                    and
                    t[3] == partiion # same partition
                    and
                    ( # nearby
                        ( # horizontal
                            abs(inward_direction[1]) == 1
                            and
                            t[1] == p[1]
                            and
                            abs(t[0]-p[0]) < tab_dist
                        )
                        or
                        ( # vertical
                            abs(inward_direction[0]) == 1
                            and
                            t[0] == p[0]
                            and
                            abs(t[1]-p[1]) < tab_dist
                        )
                    )

                ]) > 0:
                continue
            dbg_points.append((p, 5))

            # outward
            tab = autotab(panel.boardSubstrate, p, (inward_direction[0]*-1,inward_direction[1]*-1), tab_width*self.unit)
            if tab: # tab, tabface
                tabs.append((
                    p[0],
                    p[1],
                    (abs(inward_direction[0]), abs(inward_direction[1])),
                    partiion,
                ))
                tab_substrates.append(tab[0])
                for pcb in pcbs:
                    dist = pcb.distance(tab[1], pos_x, pos_y)
                    if dist == 0:
                        cuts.append(tab[1])
                        break

                # inward
                tab = autotab(panel.boardSubstrate, p, inward_direction, tab_width*self.unit)
                if tab: # tab, tabface
                    tab_substrates.append(tab[0])
                    cuts.append(tab[1])

        for t in tab_substrates:
            dbg_rects.append(t.bounds)
            try:
                panel.appendSubstrate(t)
            except:
                traceback.print_exc()

        conflicts = []
        shapes = [shapely.union_all(p.shapes) for p in pcbs]
        if frame_top_polygon:
            shapes.append(frame_top_polygon)
        if frame_bottom_polygon:
            shapes.append(frame_bottom_polygon)
        if frame_left_polygon:
            shapes.append(frame_left_polygon)
        if frame_right_polygon:
            shapes.append(frame_right_polygon)
        for i,a in enumerate(shapes):
            for b in shapes[i+1:]:
                conflict = shapely.intersection(a, b)
                if not conflict.is_empty:
                    conflicts.append(conflict)

        for pcb in pcbs:
            shapes = pcb.shapes
            for s in shapes:
                dbg_rects.append(s.bounds)

        if not export:
            panel.addMillFillets(self.state.mill_fillets*self.unit)
            self.state.conflicts = conflicts
            self.state.dbg_points = dbg_points
            self.state.dbg_rects = dbg_rects
            self.state.dbg_text = dbg_text
            self.state.boardSubstrate = panel.boardSubstrate

        vcuts = []
        bites = []
        cut_method = self.state.cut_method
        if cut_method == "mb":
            bites.extend(cuts)
            panel.makeMouseBites(cuts, diameter=mb_diameter * self.unit, spacing=mb_spacing * self.unit, offset=0 * self.unit, prolongation=0 * self.unit)
        elif cut_method == "vc":
            panel.makeVCuts(cuts)
            vcuts.extend(cuts)
        elif cut_method == "auto":
            for line in cuts:
                p1 = line.coords[0]
                p2 = line.coords[-1]
                if p1[0]==p2[0]: # vertical
                    for pcb in pcbs:
                        x1, y1, x2, y2 = pcb.nbbox
                        if pos_x+x1 < p1[0] and p1[0] < pos_x+x2:
                            panel.makeMouseBites([line], diameter=mb_diameter * self.unit, spacing=mb_spacing * self.unit, offset=0 * self.unit, prolongation=0 * self.unit)
                            bites.append(line)
                            break
                    else:
                        panel.makeVCuts([line])
                        vcuts.append(line)

                elif p1[1]==p2[1]: # horizontal
                    for pcb in pcbs:
                        x1, y1, x2, y2 = pcb.nbbox
                        if pos_y+y1 < p1[1] and p1[1] < pos_y+y2:
                            panel.makeMouseBites([line], diameter=mb_diameter * self.unit, spacing=mb_spacing * self.unit, offset=0 * self.unit, prolongation=0 * self.unit)
                            bites.append(line)
                            break
                    else:
                        panel.makeVCuts([line])
                        vcuts.append(line)

        if not export:
            self.state.vcuts = vcuts
            self.state.bites = bites

        if export:
            panel.save()

    def snap_top(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: pcb.nbbox[1])

        topmost = (self.state.frame_top + (self.state.spacing if self.state.frame_top > 0 else 0)) * self.unit
        if pcb:
            ys = [topmost]
            for p in todo:
                x1, y1, x2, y2 = p.nbbox
                ys.append(y1)
                ys.append(y2 + self.state.spacing * self.unit)
                ys.append(y2 - pcb.rheight)
            ys.sort()

        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, p in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = p.nbbox
            top = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(ax1, 0), (ax2, 0)]).intersects(LineString([(bx1, 0), (bx2, 0)])):
                    if top is None:
                        top = by2 + self.state.spacing * self.unit
                    else:
                        top = max(top, by2 + self.state.spacing * self.unit)

            if pcb:
                if top is None:
                    p.setTop(([y for y in ys if y < ay1] or [ys[0]])[-1])
                else:
                    p.setTop(([y for y in ys if y < ay1 and y>=top] or [top])[-1])
            else:
                if top is None:
                    p.setTop(topmost)
                else:
                    p.setTop(top)
        self.autoScale()
        self.build()

    def snap_bottom(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: -pcb.nbbox[3])

        bottommost = (self.state.frame_height - self.state.frame_bottom - (self.state.spacing if self.state.frame_bottom > 0 else 0)) * self.unit
        if pcb:
            ys = [bottommost]
            for p in todo:
                x1, y1, x2, y2 = p.nbbox
                ys.append(y1 - self.state.spacing * self.unit)
                ys.append(y2)
                ys.append(y1 + pcb.rheight)
            ys.sort()

        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, p in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = p.nbbox
            bottom = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(ax1, 0), (ax2, 0)]).intersects(LineString([(bx1, 0), (bx2, 0)])):
                    if bottom is None:
                        bottom = by1 - self.state.spacing * self.unit
                    else:
                        bottom = min(bottom, by1 - self.state.spacing * self.unit)
            if pcb:
                if bottom is None:
                    p.setBottom(([y for y in ys if y > ay2] or [ys[-1]])[0])
                else:
                    p.setBottom(([y for y in ys if y > ay2 and y<=bottom] or [bottom])[0])
            else:
                if bottom is None:
                    p.setBottom(bottommost)
                else:
                    p.setBottom(bottom)
        self.autoScale()
        self.build()

    def snap_left(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: pcb.nbbox[0])

        leftmost = (self.state.frame_left + (self.state.spacing if self.state.frame_left > 0 else 0)) * self.unit
        if pcb:
            xs = [leftmost]
            for p in todo:
                x1, y1, x2, y2 = p.nbbox
                xs.append(x1)
                xs.append(x2 + self.state.spacing * self.unit)
                xs.append(x2 - pcb.rwidth)
            xs.sort()

        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, p in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = p.nbbox
            left = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(0, ay1), (0, ay2)]).intersects(LineString([(0, by1), (0, by2)])):
                    if left is None:
                        left = bx2 + self.state.spacing * self.unit
                    else:
                        left = max(left, bx2 + self.state.spacing * self.unit)
            if pcb:
                if left is None:
                    p.setLeft(([x for x in xs if x < ax1] or [xs[0]])[-1])
                else:
                    p.setLeft(([x for x in xs if x < ax1 and x>=left] or [left])[-1])
            else:
                if left is None:
                    p.setLeft(leftmost)
                else:
                    p.setLeft(left)
        self.autoScale()
        self.build()

    def snap_right(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: -pcb.nbbox[2])

        rightmost = (self.state.frame_width - self.state.frame_right - (self.state.spacing if self.state.frame_right > 0 else 0)) * self.unit
        if pcb:
            xs = [rightmost]
            for p in todo:
                x1, y1, x2, y2 = p.nbbox
                xs.append(x1 - self.state.spacing * self.unit)
                xs.append(x2)
                xs.append(x1 + pcb.rwidth)
            xs.sort()

        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, p in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = p.nbbox
            right = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(0, ay1), (0, ay2)]).intersects(LineString([(0, by1), (0, by2)])):
                    if right is None:
                        right = bx1 - self.state.spacing * self.unit
                    else:
                        right = min(right, bx1 - self.state.spacing * self.unit)
            if pcb:
                if right is None:
                    p.setRight(([x for x in xs if x > ax2] or [xs[-1]])[0])
                else:
                    p.setRight(([x for x in xs if x > ax2 and x<=right] or [right])[0])
            else:
                if right is None:
                    p.setRight(rightmost)
                else:
                    p.setRight(right)
        self.autoScale()
        self.build()

    def rotateCCW(self):
        pcb = self.state.focus
        if pcb:
            pcb.rotateCCW()
            self.build()

    def rotateCW(self):
        pcb = self.state.focus
        if pcb:
            pcb.rotateCW()
            self.build()

    def toCanvas(self, x, y):
        offx, offy, scale = self.state.scale
        return x * scale + offx, y * scale + offy

    def fromCanvas(self, x, y):
        offx, offy, scale = self.state.scale
        return (x - offx)/scale, (y - offy)/scale

    def mousedown(self, e):
        self.mousepos = e.x, e.y
        self.mousehold = True
        self.mousemoved = 0

        if self.tool == Tool.TAB:
            pass
        else:
            pcbs = self.state.pcb
            x, y = self.fromCanvas(e.x, e.y)
            p = Point(x, y)

            self.mouse_dragging = None
            if self.state.focus:
                x1, y1, x2, y2 = self.state.focus.bbox
                if Polygon([(x1,y1), (x2,y1), (x2,y2), (x1,y2), (x1,y1)]).contains(p):
                    self.mouse_dragging = self.state.focus
            # if self.mouse_dragging is None:
            #     for pcb in [pcb for pcb in pcbs if pcb is not self.state.focus]:
            #         x1, y1, x2, y2 = pcb.bbox
            #         if Polygon([(x1,y1), (x2,y1), (x2,y2), (x1,y2), (x1,y1)]).contains(p):
            #             self.mouse_dragging = pcb
            #             break

    def mouseup(self, e):
        self.mousehold = False
        if self.tool == Tool.TAB:
            pass
        else:
            if self.mousemoved < 5:
                found = False
                pcbs = self.state.pcb
                x, y = self.fromCanvas(e.x, e.y)
                p = Point(x, y)
                for pcb in [pcb for pcb in pcbs if pcb is not self.state.focus]:
                    x1, y1, x2, y2 = pcb.bbox
                    if Polygon([(x1,y1), (x2,y1), (x2,y2), (x1,y2), (x1,y1)]).contains(p):
                        found = True
                        if self.state.focus is pcb:
                            continue
                        else:
                            self.state.focus = pcb
                if not found:
                    self.state.focus = None
            self.build()

    def mousemove(self, e):
        if self.tool == Tool.TAB:
            self.state()
        elif self.mousehold:
            pdx = e.x - self.mousepos[0]
            pdy = e.y - self.mousepos[1]
            self.mousemoved += (pdx**2 + pdy**2)**0.5

            x1, y1 = self.fromCanvas(*self.mousepos)
            x2, y2 = self.fromCanvas(e.x, e.y)
            dx = x2 - x1
            dy = y2 - y1
            self.state.focus = self.mouse_dragging

            if self.mouse_dragging:
                self.mouse_dragging.x += int(dx)
                self.mouse_dragging.y += int(dy)
            else:
                offx, offy, scale = self.state.scale
                offx += pdx
                offy += pdy
                self.state.scale = offx, offy, scale
        self.mousepos = e.x, e.y

    def wheel(self, e):
        offx, offy, scale = self.state.scale
        nscale = scale + e.v_delta / 120 * scale
        nscale = min(self.scale*2, max(self.scale/8, nscale))
        offx = e.x - (e.x - offx)*nscale/scale
        offy = e.y - (e.y - offy)*nscale/scale
        self.state.scale = offx, offy, nscale

    def keypress(self, event):
        if self.state.focus:
            if event.text == "r":
                self.rotateCCW()
                self.build()
            elif event.text == "R":
                self.rotateCW()
                self.build()

    def add_tab(self, arg):
        self.tool = Tool.TAB
        self.tool_args = arg

    def drawPCB(self, canvas, index, pcb, highlight):
        fill = 0x225522 if highlight else 0x112211
        x1, y1, x2, y2 = pcb.bbox
        x1, y1 = self.toCanvas(x1, y1)
        x2, y2 = self.toCanvas(x2, y2)
        canvas.drawRect(x1, y1, x2, y2, fill=fill)

        if round(pcb.rotate/90) % 4 == 0:
            tx1, ty1 = x1+10, y1+10
        elif round(pcb.rotate/90) % 4 == 1:
            tx1, ty1 = x1+10, y1-10
        elif round(pcb.rotate/90) % 4 == 2:
            tx1, ty1 = x1-10, y1-10
        elif round(pcb.rotate/90) % 4 == 3:
            tx1, ty1 = x1-10, y1+10
        canvas.drawText(tx1, ty1, f"{index+1}. {pcb.ident}\n{pcb.width/self.unit:.2f}*{pcb.height/self.unit:.2f}", rotate=pcb.rotate*-1)

    def drawLine(self, canvas, x1, y1, x2, y2, color):
        x1, y1 = self.toCanvas(x1, y1)
        x2, y2 = self.toCanvas(x2, y2)
        canvas.drawLine(x1, y1, x2, y2, color=color)

    def drawPolygon(self, canvas, polygon, stroke=None, fill=None):
        ps = []
        for p in polygon:
            ps.append(self.toCanvas(*p))
        canvas.drawPolygon(ps, stroke=stroke, fill=fill)

    def drawVCutV(self, canvas, x):
        x1, y1 = self.toCanvas(x, -VC_EXTENT*self.unit)
        x2, y2 = self.toCanvas(x, (self.state.frame_height+VC_EXTENT)*self.unit)
        canvas.drawLine(x1, y1, x2, y2, color=0x4396E2)

    def drawVCutH(self, canvas, y):
        x1, y1 = self.toCanvas(-VC_EXTENT*self.unit, y)
        x2, y2 = self.toCanvas((self.state.frame_width+VC_EXTENT)*self.unit, y)
        canvas.drawLine(x1, y1, x2, y2, color=0x4396E2)

    def drawMousebites(self, canvas, line):
        offx, offy, scale = self.state.scale
        mb_diameter = self.state.mb_diameter
        mb_spacing = self.state.mb_spacing
        i = 0
        while i * mb_spacing * self.unit <= line.length:
            p = line.interpolate(i * mb_spacing * self.unit)
            x, y = self.toCanvas(p.x, p.y)
            canvas.drawEllipse(x, y, mb_diameter*self.unit/2*scale, mb_diameter*self.unit/2*scale, stroke=0xFFFF00)
            i += 1

    def painter(self, canvas):
        offx, offy, scale = self.state.scale
        pcbs = self.state.pcb

        if self.state.use_frame:
            x1, y1 = self.toCanvas(0, 0)
            x2, y2 = self.toCanvas(self.state.frame_width*self.unit, self.state.frame_height*self.unit)
            canvas.drawRect(x1, y1, x2, y2, fill=0x151515)

        for i,pcb in enumerate(pcbs):
            if pcb is self.state.focus:
                continue
            self.drawPCB(canvas, i, pcb, False)

        for i,pcb in enumerate(pcbs):
            if pcb is not self.state.focus:
                continue
            self.drawPCB(canvas, i, pcb, True)

        boardSubstrate = self.state.boardSubstrate
        if boardSubstrate:
            if isinstance(boardSubstrate.substrates, MultiPolygon):
                geoms = boardSubstrate.substrates.geoms
            elif isinstance(boardSubstrate.substrates, Polygon):
                geoms = [boardSubstrate.substrates]
            else:
                geoms = []
            for polygon in geoms:
                coords = polygon.exterior.coords
                for i in range(1, len(coords)):
                    self.drawLine(canvas, coords[i-1][0], coords[i-1][1], coords[i][0], coords[i][1], color=0x777777)
                for interior in polygon.interiors:
                    coords = interior.coords
                    for i in range(1, len(coords)):
                        self.drawLine(canvas, coords[i-1][0], coords[i-1][1], coords[i][0], coords[i][1], color=0x777777)

        for conflict in self.state.conflicts:
            try:
                if hasattr(conflict, "exterior"):
                    coords = conflict.exterior.coords
                    self.drawPolygon(canvas, coords, fill=0xFF0000)
                else:
                    coords = conflict.coords
                    for i in range(1, len(coords)):
                        self.drawLine(canvas, coords[i-1][0], coords[i-1][1], coords[i][0], coords[i][1], color=0xFF0000)
            except:
                traceback.print_exc()

        if not self.mousehold or not self.mousemoved or not self.mouse_dragging:
            bites = self.state.bites
            vcuts = self.state.vcuts
            if self.state.show_mb:
                for line in bites:
                    self.drawMousebites(canvas, line)

            if self.state.show_vc:
                for line in vcuts:
                    p1 = line.coords[0]
                    p2 = line.coords[-1]

                    if p1[0]==p2[0]: # vertical
                        self.drawVCutV(canvas, p1[0])
                    elif p1[1]==p2[1]: # horizontal
                        self.drawVCutH(canvas, p1[1])

            if self.state.debug:
                for point, size in self.state.dbg_points:
                    x, y = self.toCanvas(point[0], point[1])
                    canvas.drawEllipse(x, y, size, size, stroke=0xFF0000)
                for rect in self.state.dbg_rects:
                    x1, y1 = self.toCanvas(rect[0], rect[1])
                    x2, y2 = self.toCanvas(rect[2], rect[3])
                    canvas.drawRect(x1, y1, x2, y2, stroke=0xFF0000)
                for text in self.state.dbg_text:
                    x, y = self.toCanvas(text[0], text[1])
                    canvas.drawText(x, y, text[2])

            if self.tool == Tool.TAB:
                x, y = self.mousepos[0], self.mousepos[1]
                canvas.drawLine(x-10, y, x+10, y, color=0xFF0000)
                canvas.drawLine(x, y-10, x, y+10, color=0xFF0000)

    def content(self):
        with Window(size=(1300, 768)).keypress(self.keypress):
            with VBox():
                with HBox():
                    self.state.pcb
                    self.state.bites
                    self.state.vcuts
                    self.state.cut_method
                    self.state.mb_diameter
                    self.state.mb_spacing
                    (Canvas(self.painter)
                        .mousedown(self.mousedown)
                        .mouseup(self.mouseup)
                        .mousemove(self.mousemove)
                        .wheel(self.wheel)
                        .layout(width=self.state.canvas_width, height=self.state.canvas_height)
                        .style(bgColor=0x000000))

                    with VBox():
                        with HBox():
                            Button("Load").click(self.load)
                            Button("Save").click(self.save)
                            Button("Add PCB").click(self.addPCB)

                            Spacer()

                            Button("Export").click(self.build, True)

                        with HBox():
                            Checkbox("Display Mousebites", self.state("show_mb"))
                            Checkbox("Display V-Cut", self.state("show_vc"))
                            Checkbox("Debug", self.state("debug")).click(self.build)

                        if self.state.pcb:
                            with HBox():
                                Label("Global")
                                Spacer()
                                Label("Unit: mm")

                            with HBox():
                                Checkbox("Use Frame", self.state("use_frame")).click(self.build)
                                Checkbox("Tight", self.state("tight")).click(self.build)
                                Checkbox("Auto Tab", self.state("auto_tab")).click(self.build)
                                Spacer()
                                Label("Max Tab Spacing")
                                TextField(self.state("max_tab_spacing")).layout(width=50).change(self.build)

                            with HBox():
                                Label("Spacing")
                                TextField(self.state("spacing")).change(self.build)
                                Label("Tab Width")
                                TextField(self.state("tab_width")).change(self.build)
                                Label("Simulate Mill Fillets")
                                TextField(self.state("mill_fillets")).change(self.build)

                            with HBox():
                                Label("Cut Method")
                                RadioButton("Auto", "auto", self.state("cut_method")).click(self.build)
                                RadioButton("Mousebites", "mb", self.state("cut_method")).click(self.build)
                                # RadioButton("V-Cut", "vc", self.state("cut_method")).click(self.build)
                                Label("V-Cut Layer")
                                with ComboBox(editable=False, text_model=self.state("vc_layer")):
                                    ComboBoxItem("User.1")
                                    ComboBoxItem("Cmts.User")

                                Spacer()
                            with HBox():
                                Label("Mousebites")
                                Label("Spacing")
                                TextField(self.state("mb_spacing")).change(self.build)
                                Label("Diameter")
                                TextField(self.state("mb_diameter")).change(self.build)
                                Spacer()

                            if self.state.use_frame:
                                with HBox():
                                    Label("Frame Size")
                                    Label("Width")
                                    TextField(self.state("frame_width")).change(self.build)
                                    Label("Height")
                                    TextField(self.state("frame_height")).change(self.build)

                                with HBox():
                                    Label("Frame Width")
                                    Label("Top")
                                    TextField(self.state("frame_top")).change(self.build)
                                    Label("Bottom")
                                    TextField(self.state("frame_bottom")).change(self.build)
                                    Label("Left")
                                    TextField(self.state("frame_left")).change(self.build)
                                    Label("Right")
                                    TextField(self.state("frame_right")).change(self.build)

                            with HBox():
                                Label("Align")
                                Button("⤒").click(self.snap_top)
                                Button("⤓").click(self.snap_bottom)
                                Button("⇤").click(self.snap_left)
                                Button("⇥").click(self.snap_right)

                            if self.state.focus:
                                with HBox():
                                    Label("Selected PCB")

                                    Spacer()

                                    Button("Duplicate").click(self.duplicate, self.state.focus)
                                    Button("Remove").click(self.remove, self.state.focus)

                                with Grid():
                                    r = 0

                                    Label("Rotate").grid(row=r, column=0)
                                    with HBox().grid(row=r, column=1):
                                        Button("↺ (r)").click(self.rotateCCW)
                                        Button("↻ (R)").click(self.rotateCW)
                                        Spacer()
                                    r += 1

                                    Label("Align").grid(row=r, column=0)
                                    with HBox().grid(row=r, column=1):
                                        Button("⤒").click(self.snap_top, pcb=self.state.focus)
                                        Button("⤓").click(self.snap_bottom, pcb=self.state.focus)
                                        Button("⇤").click(self.snap_left, pcb=self.state.focus)
                                        Button("⇥").click(self.snap_right, pcb=self.state.focus)
                                        Spacer()
                                    r += 1

                                    # Label("Add Tab").grid(row=r, column=0)
                                    # with HBox().grid(row=r, column=1):
                                    #     Button("↥").click(self.add_tab, Direction.Up)
                                    #     Button("↧").click(self.add_tab, Direction.Down)
                                    #     Button("↤").click(self.add_tab, Direction.Left)
                                    #     Button("↦").click(self.add_tab, Direction.Right)
                                    #     Spacer()
                                    # r += 1

                        Spacer()

                        Label(f"Conflicts: {len(self.state.conflicts)}")

ui = UI()

inputs = sys.argv[1:]
if inputs:
    if inputs[0].endswith(PNL_SUFFIX):
        ui.load(inputs[0])
        if len(inputs) > 1:
            ui.build(inputs[1])
            sys.exit(0)
        else:
            ui.autoScale()
            ui.build()
    else:
        for boardfile in inputs:
            if boardfile.endswith(PCB_SUFFIX):
                ui._addPCB(PCB(boardfile))

        ui.autoScale()
        ui.build()
ui.run()
