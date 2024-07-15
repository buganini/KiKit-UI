#!/usr/bin/env /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
from kikit import panelize
from kikit.units import mm
from shapely import Point, Polygon, MultiPolygon, LineString
import pcbnew

import os
import sys
from PUI.PySide6 import *

VC_EXTENT = 3

def nbbox(x1, y1, x2, y2):
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

class PCB():
    def __init__(self, boardfile):
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
        self.state.cut_method = "mb"
        self.state.mb_diameter = 0.5 * mm
        self.state.mb_spacing = 0.75 * mm
        self.state.frame_width = 100
        self.state.frame_height = 100
        self.state.margin_top = 5
        self.state.margin_bottom = 5
        self.state.margin_left = 0
        self.state.margin_right = 0
        self.state.x_spacing = 5
        self.state.y_spacing = 5

        self.mousepos = None
        self.mouse_dragging = None
        self.mousehold = False

        inputs = sys.argv[1:]
        for boardfile in inputs:
            self._addPCB(boardfile)

        self.autoScale()
        self.build()

    def autoScale(self):
        x1, y1 = 0, 0
        x2, y2 = self.state.frame_width * mm, self.state.frame_height * mm
        for pcb in self.state.pcb:
            bbox = nbbox(*pcb.bbox)
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
            self._addPCB(boardfile)

    def _addPCB(self, boardfile):
        pcb = PCB(boardfile)
        if len(self.state.pcb) > 0:
            last = self.state.pcb[-1]
            pcb.y = last.y + last.height + self.state.y_spacing * mm
        else:
            pcb.y = self.state.margin_top * mm
        self.state.pcb.append(pcb)
        self.autoScale()
        self.build()

    def duplicate(self, pcb):
        self._addPCB(pcb.file)

    def remove(self, i):
        self.state.pcb.pop(i)
        self.autoScale()
        self.build()

    def build(self, save=False):
        pcbs = self.state.pcb
        if len(pcbs) == 0:
            return

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

        if self.state.use_frame:
            panel.appendSubstrate(Polygon([
                [pos_x, pos_y],
                [pos_x+0, pos_y+self.state.frame_width*mm],
                [pos_x+self.state.frame_height*mm, pos_y+self.state.frame_width*mm],
                [pos_x+self.state.frame_height*mm, pos_y],
            ]))

        for pcb in pcbs:
            x1, y1, x2, y2 = pcb.bbox
            panel.appendBoard(
                pcb.file,
                pcbnew.VECTOR2I(pos_x + x1, pos_y + y1),
                origin=panelize.Origin.TopLeft,
                tolerance=panelize.fromMm(1),
                rotationAngle=pcbnew.EDA_ANGLE(pcb.rotate * 90, pcbnew.DEGREES_T),
                inheritDrc=False
            )

        panel.buildPartitionLineFromBB()
        cuts = panel.buildFullTabs(cutoutDepth=3*mm)
        if not save:
            self.state.cuts = cuts
            self.state.boardSubstrate = panel.boardSubstrate

        cut_method = self.state.cut_method
        if cut_method == "mb":
            panel.makeMouseBites(cuts, diameter=self.state.mb_diameter, spacing=self.state.mb_spacing, offset=0 * mm, prolongation=0 * mm)
        if cut_method == "vc":
            panel.makeVCuts(cuts)

        if self.state.use_frame:
            if self.state.margin_top > 0:
                panel.addVCutH(pos_y + self.state.margin_top * mm)
            if self.state.margin_bottom > 0:
                panel.addVCutH(pos_y + self.state.frame_height * mm - self.state.margin_top * mm)
            if self.state.margin_left > 0:
                panel.addVCutV(pos_x + self.state.margin_left * mm)
            if self.state.margin_right > 0:
                panel.addVCutV(pos_x + self.state.frame_width * mm - self.state.margin_right * mm)

        if save:
            panel.save()

    def snap_top(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: nbbox(*pcb.bbox)[1])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = nbbox(*pcb.bbox)
            top = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(ax1, 0), (ax2, 0)]).intersects(LineString([(bx1, 0), (bx2, 0)])):
                    if top is None:
                        top = by2 + self.state.y_spacing * mm
                    else:
                        top = max(top, by2 + self.state.y_spacing * mm)
            if top is None:
                pcb.setTop(self.state.margin_top * mm)
            else:
                pcb.setTop(top)
        self.autoScale()
        self.build()

    def snap_bottom(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: -nbbox(*pcb.bbox)[3])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = nbbox(*pcb.bbox)
            bottom = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(ax1, 0), (ax2, 0)]).intersects(LineString([(bx1, 0), (bx2, 0)])):
                    if bottom is None:
                        bottom = by1 - self.state.y_spacing * mm
                    else:
                        bottom = min(bottom, by1 - self.state.y_spacing * mm)
            if bottom is None:
                pcb.setBottom((self.state.frame_height - self.state.margin_bottom) * mm)
            else:
                pcb.setBottom(bottom)
        self.autoScale()
        self.build()

    def snap_left(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: nbbox(*pcb.bbox)[0])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = nbbox(*pcb.bbox)
            left = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(0, ay1), (0, ay2)]).intersects(LineString([(0, by1), (0, by2)])):
                    if left is None:
                        left = bx2 + self.state.x_spacing * mm
                    else:
                        left = max(left, bx2 + self.state.x_spacing * mm)
            if left is None:
                pcb.setLeft(self.state.margin_left * mm)
            else:
                pcb.setLeft(left)
        self.autoScale()
        self.build()

    def snap_right(self, pcb=None):
        todo = list(self.state.pcb)
        if not todo:
            return
        todo.sort(key=lambda pcb: -nbbox(*pcb.bbox)[2])
        start = 0
        end = len(todo)
        if pcb:
            start = todo.index(pcb)
            end = start+1
        for i, pcb in enumerate(todo[start:end], start):
            ax1, ay1, ax2, ay2 = nbbox(*pcb.bbox)
            right = None
            for d in todo[:i][::-1]:
                bx1, by1, bx2, by2 = nbbox(*d.bbox)
                if LineString([(0, ay1), (0, ay2)]).intersects(LineString([(0, by1), (0, by2)])):
                    if right is None:
                        right = bx1 - self.state.x_spacing * mm
                    else:
                        right = min(right, bx1 - self.state.x_spacing * mm)
            if right is None:
                pcb.setRight((self.state.frame_width - self.state.margin_right) * mm)
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
        if self.mousehold:
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
                self.state()
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

    def drawPCB(self, canvas, index, pcb, highlight):
        stroke = 0x00FFFF if highlight else 0x777777
        fill = 0x222222 if highlight else None
        x1, y1, x2, y2 = pcb.bbox
        x1, y1 = self.toCanvas(x1, y1)
        x2, y2 = self.toCanvas(x2, y2)
        canvas.drawRect(x1, y1, x2, y2, stroke=stroke, fill=fill)

        if pcb.rotate % 4 == 0:
            tx1, ty1 = x1+10, y1+10
        elif pcb.rotate % 4 == 1:
            tx1, ty1 = x1+10, y1-10
        elif pcb.rotate % 4 == 2:
            tx1, ty1 = x1-10, y1-10
        elif pcb.rotate % 4 == 3:
            tx1, ty1 = x1-10, y1+10
        canvas.drawText(tx1, ty1, f"{index+1}", rotate=pcb.rotate*-90)

    def painter(self, canvas):
        offx, offy, scale = self.state.scale
        pcbs = self.state.pcb
        cuts = self.state.cuts
        if self.state.use_frame:
            x1, y1 = self.toCanvas(0, 0)
            x2, y2 = self.toCanvas(self.state.frame_width * mm, self.state.frame_height * mm)
            canvas.drawRect(x1, y1, x2, y2, stroke=0x333333)
        else:
            boardSubstrate = self.state.boardSubstrate
            if boardSubstrate:
                exterior = boardSubstrate.exterior()
                if isinstance(exterior, MultiPolygon):
                    for polygon in exterior.geoms:
                        coords = polygon.exterior.coords
                        for i in range(1, len(coords)):
                            x1, y1 = self.toCanvas(coords[i-1][0], coords[i-1][1])
                            x2, y2 = self.toCanvas(coords[i][0], coords[i][1])
                            canvas.drawLine(x1, y1, x2, y2, color=0x555555)
                elif isinstance(exterior, Polygon):
                    coords = exterior.exterior.coords
                    for i in range(1, len(coords)):
                        x1, y1 = self.toCanvas(coords[i-1][0], coords[i-1][1])
                        x2, y2 = self.toCanvas(coords[i][0], coords[i][1])
                        canvas.drawLine(x1, y1, x2, y2, color=0x555555)
                else:
                    print("Unhandled board substrate exterior", exterior)

        for i,pcb in enumerate(pcbs):
            if pcb is self.state.focus:
                continue
            self.drawPCB(canvas, i, pcb, False)

        for i,pcb in enumerate(pcbs):
            if pcb is not self.state.focus:
                continue
            self.drawPCB(canvas, i, pcb, True)

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

        if self.state.use_frame:
            if self.state.margin_top > 0:
                y = self.state.margin_top * mm
                x1, y1 = self.toCanvas(-VC_EXTENT*mm, y)
                x2, y2 = self.toCanvas((self.state.frame_width+VC_EXTENT)*mm, y)
                canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)
            if self.state.margin_bottom > 0:
                y = (self.state.frame_height - self.state.margin_top) * mm
                x1, y1 = self.toCanvas(-VC_EXTENT*mm, y)
                x2, y2 = self.toCanvas((self.state.frame_width+VC_EXTENT)*mm, y)
                canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)
            if self.state.margin_left > 0:
                x = self.state.margin_left * mm
                x1, y1 = self.toCanvas(x, -VC_EXTENT*mm)
                x2, y2 = self.toCanvas(x, (self.state.frame_height+VC_EXTENT)*mm)
                canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)
            if self.state.margin_right > 0:
                x = (self.state.frame_width - self.state.margin_right) * mm
                x1, y1 = self.toCanvas(x, -VC_EXTENT*mm)
                x2, y2 = self.toCanvas(x, (self.state.frame_height+VC_EXTENT)*mm)
                canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)


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
                                Spacer()
                                RadioButton("Mousebites", "mb", self.state("cut_method")).click(self.build)
                                RadioButton("V-Cut", "vc", self.state("cut_method")).click(self.build)
                                Spacer()

                            if self.state.use_frame:
                                with HBox():
                                    Label("Frame")
                                    TextField(self.state("frame_width"))
                                    TextField(self.state("frame_height"))

                                with HBox():
                                    Label("Margin")
                                    Label("Top")
                                    TextField(self.state("margin_top"))
                                    Label("Bottom")
                                    TextField(self.state("margin_bottom"))
                                    Label("Left")
                                    TextField(self.state("margin_left"))
                                    Label("Right")
                                    TextField(self.state("margin_right"))

                            with Grid():
                                r = 0

                                Label("V-Alignment").grid(row=r, column=1)
                                TextField(self.state("y_spacing")).layout(width=100).grid(row=r, column=2)
                                Button("⤒").grid(row=r, column=3).click(self.snap_top)
                                Button("⤓").grid(row=r, column=4).click(self.snap_bottom)
                                r += 1

                                Label("H-Alignment").grid(row=r, column=1)
                                TextField(self.state("x_spacing")).layout(width=100).grid(row=r, column=2)
                                Button("⇤").grid(row=r, column=3).click(self.snap_left)
                                Button("⇥").grid(row=r, column=4).click(self.snap_right)


                            with HBox():
                                Spacer()
                                Button("Save").click(self.build, True)

                            if self.state.focus:
                                Label("Selected PCB")

                                with HBox():
                                    Label("Rotate")
                                    Button("↺ (r)").click(self.rotateCCW)
                                    Button("↻ (R)").click(self.rotateCW)
                                    Spacer()

                                with HBox():
                                    Label("Align")
                                    Button("⤒").click(self.snap_top, pcb=self.state.focus)
                                    Button("⤓").click(self.snap_bottom, pcb=self.state.focus)
                                    Button("⇤").click(self.snap_left, pcb=self.state.focus)
                                    Button("⇥").click(self.snap_right, pcb=self.state.focus)
                                    Spacer()

                            Spacer()


ui = UI()
ui.run()
