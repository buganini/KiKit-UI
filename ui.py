#!/usr/bin/env /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
from kikit import panelize
from kikit.units import mm
from shapely import Point, Polygon
import pcbnew

import sys
sys.path.append("/Users/buganini/repo/buganini/PUI")
from PUI.PySide6 import *

class PCB():
    def __init__(self, boardfile):
        self.file = boardfile
        board = pcbnew.LoadBoard(boardfile)
        bbox = panelize.findBoardBoundingBox(board)
        self.pos_x, self.pos_y = bbox.GetPosition()
        self.width = bbox.GetWidth()
        self.height = bbox.GetHeight()
        self.x = 0
        self.y = 0
        self.rotate = 0

    def moveUp(self):
        self.y -= 1 * mm

    def moveLeft(self):
        self.x -= 1 * mm

    def moveRight(self):
        self.x += 1 * mm

    def moveDown(self):
        self.y += 1 * mm

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
        self.state.scale = (1, 0, 0)
        self.state.output = ""
        self.state.canvas_width = 800
        self.state.canvas_height = 600
        self.state.focus = None
        self.state.cuts = []
        self.state.cut_method = "mb"
        self.state.mb_diameter = 0.5 * mm
        self.state.mb_spacing = 0.75 * mm

        self.mousehold = False

        inputs = sys.argv[1:]
        for boardfile in inputs:
            pcb = PCB(boardfile)
            if len(self.state.pcb) > 0:
                pcb.x = self.state.pcb[0].x + self.state.pcb[0].width + 1 * mm
            self.state.pcb.append(pcb)

        self.autoScale()
        self.build()

    def autoScale(self):
        mw = 0
        mh = 0
        for pcb in self.state.pcb:
            mw = max(mw, pcb.width)
            mh = max(mh, pcb.height)

        if mw == 0 or mh == 0:
            return

        sw = self.state.canvas_width / mw
        sh = self.state.canvas_height / mh
        self.state.scale = (min(sw, sh) / 2, mw/2, mh/2)

    def addPCB(self):
        boardfile = OpenFile("Open PCB", "KiCad PCB (*.kicad_pcb)")
        pcb = PCB(boardfile)
        if len(self.state.pcb) > 0:
            pcb.x = self.state.pcb[0].x + 10 * mm
        self.state.pcb.append(pcb)
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
            pos_x = pcbs[0].pos_x
            pos_y = pcbs[0].pos_y

        panel = panelize.Panel(self.state.output)
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

        cut_method = self.state.cut_method
        if cut_method == "mb":
            panel.makeMouseBites(cuts, diameter=self.state.mb_diameter, spacing=self.state.mb_spacing, offset=0 * mm, prolongation=0 * mm)
        if cut_method == "vc":
            panel.makeVCuts(cuts)

        if save:
            panel.save()

    def rotateCCW(self):
        pcb = self.state.focus
        if pcb:
            pcb.rotate += 1
            self.autoScale()
            self.build()

    def rotateCW(self):
        pcb = self.state.focus
        if pcb:
            pcb.rotate -= 1
            self.autoScale()
            self.build()

    def toCanvas(self, x, y):
        scale, offx, offy = self.state.scale
        return (offx + x) * scale, (offy + y) * scale

    def fromCanvas(self, x, y):
        scale, offx, offy = self.state.scale
        return x/scale - offx, y/scale - offy

    def mousedown(self, e):
        self.mousepos = e.x, e.y
        self.mousehold = True
        self.mousemoved = False

    def mouseup(self, e):
        self.mousehold = False
        if not self.mousemoved:
            pcbs = self.state.pcb
            x, y = self.fromCanvas(e.x, e.y)
            p = Point(x, y)
            for pcb in [pcb for pcb in pcbs if pcb is not self.state.focus]:
                x1, y1, x2, y2 = pcb.bbox
                if Polygon([(x1,y1), (x2,y1), (x2,y2), (x1,y2), (x1,y1)]).contains(p):
                    if self.state.focus is pcb:
                        continue
                    else:
                        self.state.focus = pcb
        self.build()

    def mousemove(self, e):
        self.mousemoved = True
        if self.mousehold:
            x1, y1 = self.fromCanvas(*self.mousepos)
            x2, y2 = self.fromCanvas(e.x, e.y)
            dx = x2 - x1
            dy = y2 - y1
            if self.state.focus:
                self.state.focus.x += int(dx)
                self.state.focus.y += int(dy)
                self.state()
        self.mousepos = e.x, e.y

    def drawPCB(self, canvas, pcb, highlight):
        stroke = 0x00FFFF if highlight else 0x0000FF
        x1, y1, x2, y2 = pcb.bbox
        x1, y1 = self.toCanvas(x1, y1)
        x2, y2 = self.toCanvas(x2, y2)
        canvas.drawRect(x1, y1, x2, y2, stroke=stroke)

    def painter(self, canvas):
        pcbs = self.state.pcb
        cuts = self.state.cuts
        for pcb in pcbs:
            if pcb is self.state.focus:
                continue
            self.drawPCB(canvas, pcb, False)

        for pcb in pcbs:
            if pcb is not self.state.focus:
                continue
            self.drawPCB(canvas, pcb, True)

        if not self.mousehold or not self.mousemoved:
            cut_method = self.state.cut_method
            mb_diameter = self.state.mb_diameter
            mb_spacing = self.state.mb_spacing
            scale, offx, offy = self.state.scale
            if cut_method == "mb":
                for line in cuts:
                    i = 0
                    while i * mb_spacing < line.length:
                        p = line.interpolate(i*mb_spacing)
                        x, y = self.toCanvas(p.x, p.y)
                        canvas.drawEllipse(x, y, mb_diameter/2*scale, mb_diameter/2*scale, stroke=0xFFFF00)
                        i += 1
            if cut_method == "vc":
                for line in cuts:
                    p1 = line.coords[0]
                    p2 = line.coords[-1]
                    x1, y1 = self.toCanvas(p1[0], p1[1])
                    x2, y2 = self.toCanvas(p2[0], p2[1])
                    canvas.drawLine(x1, y1, x2, y2, color=0xFFFF00)

    def content(self):
        with Window():
            with VBox():
                with HBox():
                    Button("Add PCB").click(self.addPCB)
                    if self.state.focus:
                        Button("CCW").click(self.rotateCCW)
                        Button("CW").click(self.rotateCW)
                    Spacer()
                    if self.state.pcb:
                        RadioButton("Mousebites", "mb", self.state("cut_method")).click(self.build)
                        RadioButton("V-Cut", "vc", self.state("cut_method")).click(self.build)
                        Button("Save").click(self.build, True)

                for i,pcb in enumerate(self.state.pcb):
                    Label(f"{i+1}. {pcb.file}").grid(row=i, column=0)

                self.state.pcb
                self.state.cuts
                self.state.cut_method
                self.state.mb_diameter
                self.state.mb_spacing
                (Canvas(self.painter)
                    .mousedown(self.mousedown)
                    .mouseup(self.mouseup)
                    .mousemove(self.mousemove)
                    .layout(width=self.state.canvas_width, height=self.state.canvas_height)
                    .style(bgColor=0x000000))

                Spacer()

ui = UI()
ui.run()
