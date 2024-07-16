#!/usr/bin/env /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
from kikit import panelize, substrate
from kikit.units import mm
from shapely.geometry import Point, Polygon, MultiPolygon, LineString, GeometryCollection, box
import pcbnew
from enum import Enum
import traceback
import os
import sys
sys.path.append("/Users/buganini/repo/buganini/PUI")
from PUI.PySide6 import *

VC_EXTENT = 3

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
        self.file = boardfile
        board = pcbnew.LoadBoard(boardfile)
        bbox = panelize.findBoardBoundingBox(board)
        self.ident = os.path.join(os.path.basename(os.path.dirname(boardfile)), os.path.basename(boardfile))
        self.pos_x, self.pos_y = bbox.GetPosition()
        self.width = bbox.GetWidth()
        self.height = bbox.GetHeight()
        self.x = 0
        self.y = 0
        self.rotate = 0

    def clone(self):
        pcb = PCB(self.file)
        pcb.rotate = self.rotate
        return pcb

    def setTop(self, top):
        if self.rotate % 4 == 0:
            self.y = top
        elif self.rotate % 4 == 1:
            self.y = top + self.width
        elif self.rotate % 4 == 2:
            self.y = top + self.height
        elif self.rotate % 4 == 3:
            self.y = top

    def setBottom(self, bottom):
        if self.rotate % 4 == 0:
            self.y = bottom - self.height
        elif self.rotate % 4 == 1:
            self.y = bottom
        elif self.rotate % 4 == 2:
            self.y = bottom
        elif self.rotate % 4 == 3:
            self.y = bottom - self.width

    def setLeft(self, left):
        if self.rotate % 4 == 0:
            self.x = left
        elif self.rotate % 4 == 1:
            self.x = left
        elif self.rotate % 4 == 2:
            self.x = left + self.width
        elif self.rotate % 4 == 3:
            self.x = left + self.height

    def setRight(self, right):
        if self.rotate % 4 == 0:
            self.x = right - self.width
        elif self.rotate % 4 == 1:
            self.x = right - self.height
        elif self.rotate % 4 == 2:
            self.x = right
        elif self.rotate % 4 == 3:
            self.x = right
    @property
    def bbox(self):
        if self.rotate % 4 == 0:
            x1, y1, x2, y2 = self.x, self.y, self.x+self.width, self.y+self.height
        elif self.rotate % 4 == 1:
            x1, y1, x2, y2 = self.x, self.y, self.x+self.height, self.y-self.width
        elif self.rotate % 4 == 2:
            x1, y1, x2, y2 = self.x, self.y, self.x-self.width, self.y-self.height
        elif self.rotate % 4 == 3:
            x1, y1, x2, y2 = self.x, self.y, self.x-self.height, self.y+self.width
        return x1, y1, x2, y2

    @property
    def nbbox(self):
        return nbbox(*self.bbox)

class UI(Application):
    def __init__(self):
        super().__init__()
        self.state = State()
        self.state.pcb = []
        self.state.scale = (0, 0, 1)
        self.state.output = ""
        self.state.canvas_width = 800
        self.state.canvas_height = 800
        self.state.focus = None
        self.state.cuts = []
        self.state.substrates = []
        self.state.use_frame = True
        self.state.tight = True
        self.state.auto_tab = True
        self.state.spacing = 3.0
        self.state.tab_width = 3.0
        self.state.cut_method = "mb"
        self.state.mb_diameter = 0.5 * mm
        self.state.mb_spacing = 0.75 * mm
        self.state.frame_width = 100
        self.state.frame_height = 100
        self.state.frame_top = 5
        self.state.frame_bottom = 5
        self.state.frame_left = 0
        self.state.frame_right = 0
        self.state.mill_fillets = 1.0

        self.mousepos = None
        self.mouse_dragging = None
        self.mousehold = False
        self.tool = Tool.NONE
        self.tool_args = None

        inputs = sys.argv[1:]
        for boardfile in inputs:
            self._addPCB(PCB(boardfile))

        self.autoScale()
        self.build()

    def autoScale(self):
        x1, y1 = 0, 0
        x2, y2 = self.state.frame_width * mm, self.state.frame_height * mm
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
            pcb.y = last.y + last.height + self.state.spacing * mm
        else:
            pcb.y = (self.state.frame_top + self.state.spacing if self.state.frame_top > 0 else 0) * mm
        self.state.pcb.append(pcb)
        self.autoScale()
        self.build()

    def duplicate(self, pcb):
        self._addPCB(pcb.clone())

    def remove(self, i):
        self.state.pcb.pop(i)
        self.autoScale()
        self.build()

    def build(self, save=False):
        pcbs = self.state.pcb
        if len(pcbs) == 0:
            return

        spacing = self.state.spacing
        tab_width = self.state.tab_width

        pos_x = 0
        pos_y = 0

        if save:
            output = SaveFile(self.state.output, "KiCad PCB (*.kicad_pcb)")
            if output:
                if not output.endswith(".kicad_pcb"):
                    output += ".kicad_pcb"
                self.state.output = output
            else:
                return
            pos_x = pcbs[0].pos_x
            pos_y = pcbs[0].pos_y

        panel = panelize.Panel(self.state.output)

        boundarySubstrates = []
        if self.state.use_frame and not self.state.tight:
            if self.state.frame_top > 0:
                polygon = Polygon([
                    [pos_x, pos_y],
                    [pos_x+self.state.frame_width*mm, pos_y],
                    [pos_x+self.state.frame_width*mm, pos_y+self.state.frame_top*mm],
                    [pos_x, pos_y+self.state.frame_top*mm],
                ])
                panel.appendSubstrate(polygon)
                sub = substrate.Substrate([])
                sub.union(polygon)
                boundarySubstrates.append(sub)
            if self.state.frame_bottom > 0:
                polygon = Polygon([
                    [pos_x, pos_y+self.state.frame_height*mm],
                    [pos_x+self.state.frame_width*mm, pos_y+self.state.frame_height*mm],
                    [pos_x+self.state.frame_width*mm, pos_y+self.state.frame_height*mm-self.state.frame_bottom*mm],
                    [pos_x, pos_y+self.state.frame_height*mm-self.state.frame_bottom*mm],
                ])
                panel.appendSubstrate(polygon)
                sub = substrate.Substrate([])
                sub.union(polygon)
                boundarySubstrates.append(sub)
            if self.state.frame_left > 0:
                polygon = Polygon([
                    [pos_x, pos_y],
                    [pos_x, pos_y+self.state.frame_height*mm],
                    [pos_x+self.state.frame_left*mm, pos_y+self.state.frame_height*mm],
                    [pos_x+self.state.frame_left*mm, pos_y],
                ])
                panel.appendSubstrate(polygon)
                sub = substrate.Substrate([])
                sub.union(polygon)
                boundarySubstrates.append(sub)
            if self.state.frame_right > 0:
                polygon = Polygon([
                    [pos_x+self.state.frame_width*mm, pos_y],
                    [pos_x+self.state.frame_width*mm, pos_y+self.state.frame_height*mm],
                    [pos_x+self.state.frame_width*mm-self.state.frame_right*mm, pos_y+self.state.frame_height*mm],
                    [pos_x+self.state.frame_width*mm-self.state.frame_right*mm, pos_y],
                ])
                panel.appendSubstrate(polygon)
                sub = substrate.Substrate([])
                sub.union(polygon)
                boundarySubstrates.append(sub)

        for pcb in pcbs:
            x1, y1, x2, y2 = pcb.bbox
            panel.appendBoard(
                pcb.file,
                pcbnew.VECTOR2I(round(pos_x + x1), round(pos_y + y1)),
                origin=panelize.Origin.TopLeft,
                tolerance=panelize.fromMm(1),
                rotationAngle=pcbnew.EDA_ANGLE(pcb.rotate * 90, pcbnew.DEGREES_T),
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
                x2 = max(x2, pos_x + self.state.frame_width*mm)
                y2 = max(y2, pos_y + self.state.frame_height*mm)

            for pcb in pcbs[1:]:
                bbox = pcb.nbbox
                x1 = min(x1, pos_x+bbox[0])
                y1 = min(y1, pos_y+bbox[1])
                x2 = max(x2, pos_x+bbox[2])
                y2 = max(y2, pos_y+bbox[3])

            # board hole
            frameBody = box(x1, y1, x2, y2)
            for s in panel.substrates:
                frameBody = frameBody.difference(s.exterior().buffer(spacing*mm, join_style="mitre"))
            panel.appendSubstrate(frameBody)

        tabs = []
        cuts = []
        if self.state.auto_tab:
            bboxes = [pcb.nbbox for pcb in pcbs]
            if self.state.use_frame:
                bboxes.append((0, 0, self.state.frame_width*mm, self.state.frame_height*mm))
            mx1, my1, mx2, my2 = zip(*bboxes)
            mx1 = min(mx1)
            my1 = min(my1)
            mx2 = max(mx2)
            my2 = max(my2)
            for pcb in pcbs:
                x1, y1, x2, y2 = pcb.nbbox
                if y1 != my1: # top
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + (x1 + x2)/2, pos_y + y1 - spacing/2*mm), (0,1), 1*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + (x1 + x2)/2, pos_y + y1 - spacing/2*mm), (0,-1), 1*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass

                if y2 != my2: # bottom
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + (x1 + x2)/2, pos_y + y2 + spacing/2*mm), (0,-1), 2*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + (x1 + x2)/2, pos_y + y2 + spacing/2*mm), (0,1), 2*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass

                if x1 != mx1: # left
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + x1 - spacing/2*mm , pos_y + (y1 + y2)/2), (1,0), 3*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + x1 - spacing/2*mm , pos_y + (y1 + y2)/2), (-1,0), 3*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass
                if x2 != mx2: # right
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + x2 + spacing/2*mm , pos_y + (y1 + y2)/2), (-1,0), 4*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass
                    try:
                        tab = panel.boardSubstrate.tab((pos_x + x2 + spacing/2*mm , pos_y + (y1 + y2)/2), (1,0), 4*mm)
                        if len(tab) == 2: # tab, tabface
                            tabs.append(tab[0])
                            cuts.append(tab[1])
                    except:
                        pass
        for tab in tabs:
            panel.appendSubstrate(tab)

        if not save:
            panel.addMillFillets(self.state.mill_fillets*mm)
            self.state.cuts = cuts
            self.state.boardSubstrate = panel.boardSubstrate

        cut_method = self.state.cut_method
        if cut_method == "mb":
            panel.makeMouseBites(cuts, diameter=self.state.mb_diameter, spacing=self.state.mb_spacing, offset=0 * mm, prolongation=0 * mm)
        if cut_method == "vc":
            panel.makeVCuts(cuts)

        if save:
            panel.save()

    def snap_top(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: pcb.nbbox[1])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = pcb.nbbox
            top = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(ax1, 0), (ax2, 0)]).intersects(LineString([(bx1, 0), (bx2, 0)])):
                    if top is None:
                        top = by2 + self.state.spacing * mm
                    else:
                        top = max(top, by2 + self.state.spacing * mm)
            if top is None:
                pcb.setTop((self.state.frame_top + (self.state.spacing if self.state.frame_top > 0 else 0)) * mm)
            else:
                pcb.setTop(top)
        self.autoScale()
        self.build()

    def snap_bottom(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: -pcb.nbbox[3])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = pcb.nbbox
            bottom = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(ax1, 0), (ax2, 0)]).intersects(LineString([(bx1, 0), (bx2, 0)])):
                    if bottom is None:
                        bottom = by1 - self.state.spacing * mm
                    else:
                        bottom = min(bottom, by1 - self.state.spacing * mm)
            if bottom is None:
                pcb.setBottom((self.state.frame_height - self.state.frame_bottom - (self.state.spacing if self.state.frame_bottom > 0 else 0)) * mm)
            else:
                pcb.setBottom(bottom)
        self.autoScale()
        self.build()

    def snap_left(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: pcb.nbbox[0])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = pcb.nbbox
            left = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(0, ay1), (0, ay2)]).intersects(LineString([(0, by1), (0, by2)])):
                    if left is None:
                        left = bx2 + self.state.spacing * mm
                    else:
                        left = max(left, bx2 + self.state.spacing * mm)
            if left is None:
                pcb.setLeft((self.state.frame_left + (self.state.spacing if self.state.frame_left > 0 else 0)) * mm)
            else:
                pcb.setLeft(left)
        self.autoScale()
        self.build()

    def snap_right(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: -pcb.nbbox[2])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = pcb.nbbox
            right = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(0, ay1), (0, ay2)]).intersects(LineString([(0, by1), (0, by2)])):
                    if right is None:
                        right = bx1 - self.state.spacing * mm
                    else:
                        right = min(right, bx1 - self.state.spacing * mm)
            if right is None:
                pcb.setRight((self.state.frame_width - self.state.frame_right - (self.state.spacing if self.state.frame_right > 0 else 0)) * mm)
            else:
                pcb.setRight(right)
        self.autoScale()
        self.build()

    def rotateCCW(self):
        pcb = self.state.focus
        if pcb:
            pcb.rotate += 1
            self.build()

    def rotateCW(self):
        pcb = self.state.focus
        if pcb:
            pcb.rotate -= 1
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
                self.state.focus.rotate += 1
                self.build()
            elif event.text == "R":
                self.state.focus.rotate -= 1
                self.build()

    def add_tab(self, arg):
        self.tool = Tool.TAB
        self.tool_args = arg

    def drawPCB(self, canvas, index, pcb, highlight):
        fill = 0x113311 if highlight else 0x112211
        x1, y1, x2, y2 = pcb.bbox
        x1, y1 = self.toCanvas(x1, y1)
        x2, y2 = self.toCanvas(x2, y2)
        canvas.drawRect(x1, y1, x2, y2, fill=fill)

        if pcb.rotate % 4 == 0:
            tx1, ty1 = x1+10, y1+10
        elif pcb.rotate % 4 == 1:
            tx1, ty1 = x1+10, y1-10
        elif pcb.rotate % 4 == 2:
            tx1, ty1 = x1-10, y1-10
        elif pcb.rotate % 4 == 3:
            tx1, ty1 = x1-10, y1+10
        canvas.drawText(tx1, ty1, f"{index+1}", rotate=pcb.rotate*-90)

    def drawLine(self, canvas, x1, y1, x2, y2, color):
        x1, y1 = self.toCanvas(x1, y1)
        x2, y2 = self.toCanvas(x2, y2)
        canvas.drawLine(x1, y1, x2, y2, color=color)

    def painter(self, canvas):
        offx, offy, scale = self.state.scale
        pcbs = self.state.pcb
        cuts = self.state.cuts

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
                    self.drawLine(canvas, coords[i-1][0], coords[i-1][1], coords[i][0], coords[i][1], color=0x555555)
                for interior in polygon.interiors:
                    coords = interior.coords
                    for i in range(1, len(coords)):
                        self.drawLine(canvas, coords[i-1][0], coords[i-1][1], coords[i][0], coords[i][1], color=0x555555)

        if not self.mousehold or not self.mousemoved or not self.mouse_dragging:
            cut_method = self.state.cut_method
            mb_diameter = self.state.mb_diameter
            mb_spacing = self.state.mb_spacing
            if cut_method == "mb":
                for line in cuts:
                    i = 0
                    while i * mb_spacing <= line.length:
                        p = line.interpolate(i*mb_spacing)
                        x, y = self.toCanvas(p.x, p.y)
                        canvas.drawEllipse(x, y, mb_diameter/2*scale, mb_diameter/2*scale, stroke=0xFFFF00)
                        i += 1
            if cut_method == "vc":
                for line in cuts:
                    p1 = line.coords[0]
                    p2 = line.coords[-1]
                    if p1[0]==p2[0]: # vertical
                        x1, y1 = self.toCanvas(p1[0], -VC_EXTENT*mm)
                        x2, y2 = self.toCanvas(p1[0], (self.state.frame_height+VC_EXTENT)*mm)
                        canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)
                    elif p1[1]==p2[1]: # horizontal
                        x1, y1 = self.toCanvas(-VC_EXTENT*mm, p1[1])
                        x2, y2 = self.toCanvas((self.state.frame_width+VC_EXTENT)*mm, p1[1])
                        canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)
                    else:
                        x1, y1 = self.toCanvas(p1[0], p1[1])
                        x2, y2 = self.toCanvas(p2[0], p2[1])
                        canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)

            if self.tool == Tool.TAB:
                x, y = self.mousepos[0], self.mousepos[1]
                canvas.drawLine(x-10, y, x+10, y, color=0xFF0000)
                canvas.drawLine(x, y-10, x, y+10, color=0xFF0000)

    def content(self):
        with Window(size=(1300, 768)).keypress(self.keypress):
            with VBox():
                with HBox():
                    with VBox():
                        with HBox():
                            with Grid():
                                for i,pcb in enumerate(self.state.pcb):
                                    Label(f"{i+1}. {pcb.ident}").grid(row=i, column=0)
                                    Button("Duplicate").grid(row=i, column=1).click(self.duplicate, pcb)
                                    Button("Remove").grid(row=i, column=2).click(self.remove, i)
                            Spacer()

                        self.state.pcb
                        self.state.cuts
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
                        Button("Add PCB").click(self.addPCB)

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

                            with HBox():
                                Label("Spacing")
                                TextField(self.state("spacing")).change(self.build)
                                Label("Tab Width")
                                TextField(self.state("tab_width")).change(self.build)
                                Label("Simulate Mill Fillets")
                                TextField(self.state("mill_fillets")).change(self.build)

                            with HBox():
                                Label("Cut Method")
                                RadioButton("Mousebites", "mb", self.state("cut_method")).click(self.build)
                                RadioButton("V-Cut", "vc", self.state("cut_method")).click(self.build)

                            if self.state.use_frame:
                                with HBox():
                                    Label("Frame Size")
                                    Label("Width")
                                    TextField(self.state("frame_width"))
                                    Label("Height")
                                    TextField(self.state("frame_height"))

                                with HBox():
                                    Label("Frame Width")
                                    Label("Top")
                                    TextField(self.state("frame_top"))
                                    Label("Bottom")
                                    TextField(self.state("frame_bottom"))
                                    Label("Left")
                                    TextField(self.state("frame_left"))
                                    Label("Right")
                                    TextField(self.state("frame_right"))

                            with HBox():
                                Label("Align")
                                Button("⤒").click(self.snap_top)
                                Button("⤓").click(self.snap_bottom)
                                Button("⇤").click(self.snap_left)
                                Button("⇥").click(self.snap_right)

                            with HBox():
                                Spacer()
                                Button("Save").click(self.build, True)

                            if self.state.focus:
                                Label("Selected PCB")

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

ui = UI()
ui.run()
