#!/usr/bin/env /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
from kikit import panelize
from kikit.units import mm
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
        boardfile = OpenFileDialog("Open PCB", "KiCad PCB (*.kicad_pcb)")
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

        if save:
            self.state.output = SaveFile(self.state.output, "KiCad PCB (*.kicad_pcb)")
            if not self.state.output.endswith(".kicad_pcb"):
                self.state.output += ".kicad_pcb"

        panel = panelize.Panel(self.state.output)
        for pcb in pcbs:
            x1, y1, x2, y2 = pcb.bbox
            panel.appendBoard(
                pcb.file,
                pcbnew.VECTOR2I(pcbs[0].pos_x + x1, pcbs[0].pos_y + y1),
                origin=panelize.Origin.TopLeft,
                tolerance=panelize.fromMm(1),
                rotationAngle=pcbnew.EDA_ANGLE(pcb.rotate * 90, pcbnew.DEGREES_T),
                inheritDrc=False
            )

        panel.buildPartitionLineFromBB()
        cuts = panel.buildFullTabs(cutoutDepth=3*mm)
        self.state.cuts = cuts

        cut_method = self.state.cut_method
        if cut_method == "mb":
            panel.makeMouseBites(cuts, diameter=self.state.mb_diameter, spacing=self.state.mb_spacing, offset=0 * mm, prolongation=0 * mm)
        if cut_method == "vc":
            panel.makeVCuts(cuts)

        if save:
            panel.save()

    def setFocus(self, pcb):
        self.state.focus = pcb

    def moveUp(self, pcb):
        pcb.moveUp()
        self.build()

    def moveLeft(self, pcb):
        pcb.moveLeft()
        self.build()

    def moveRight(self, pcb):
        pcb.moveRight()
        self.build()

    def moveDown(self, pcb):
        pcb.moveDown()
        self.build()

    def rotateCCW(self, pcb):
        pcb.rotate += 1
        self.build()

    def rotateCW(self, pcb):
        pcb.rotate -= 1
        self.build()

    def drawPCB(self, canvas, pcb, highlight):
        stroke = 0x00FFFF if highlight else 0x0000FF
        x1, y1, x2, y2 = pcb.bbox
        scale, offx, offy = self.state.scale
        canvas.drawRect((offx + x1) * scale, (offy + y1) * scale, (offx + x2) * scale, (offy + y2) * scale, stroke=stroke)

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

        cut_method = self.state.cut_method
        mb_diameter = self.state.mb_diameter
        mb_spacing = self.state.mb_spacing
        scale, offx, offy = self.state.scale
        if cut_method == "mb":
            for line in cuts:
                i = 0
                while i * mb_spacing < line.length:
                    p = line.interpolate(i*mb_spacing)
                    canvas.drawEllipse((offx + p.x - pcbs[0].pos_x) * scale, (offy + p.y - pcbs[0].pos_y) * scale, mb_diameter/2*scale, mb_diameter/2*scale, stroke=0xFFFF00)
                    i += 1
        if cut_method == "vc":
            for line in cuts:
                p1 = line.coords[0]
                p2 = line.coords[-1]
                canvas.drawLine((offx + p1[0] - pcbs[0].pos_x) * scale, (offy + p1[1] - pcbs[0].pos_y) * scale, (offx + p2[0] - pcbs[0].pos_x) * scale, (offy + p2[1] - pcbs[0].pos_y) * scale, color=0xFFFF00)

    def content(self):
        with Window():
            with VBox():
                with HBox():
                    Button("Add PCB").click(self.addPCB)
                    Spacer()
                    RadioButton("Mousebites", "mb", self.state("cut_method"))
                    RadioButton("V-Cut", "vc", self.state("cut_method"))
                    Button("Save").click(self.build, True)

                with Grid():
                    for i,pcb in enumerate(self.state.pcb):
                        Label(f"{i+1}. {pcb.file}").click(self.setFocus, pcb).grid(row=i, column=0)
                        Button("Left").click(self.moveLeft, pcb).grid(row=i, column=1)
                        Button("Up").click(self.moveUp, pcb).grid(row=i, column=2)
                        Button("Down").click(self.moveDown, pcb).grid(row=i, column=3)
                        Button("Right").click(self.moveRight, pcb).grid(row=i, column=4)
                        Button("CCW").click(self.rotateCCW, pcb).grid(row=i, column=5)
                        Button("CW").click(self.rotateCW, pcb).grid(row=i, column=6)

                self.state.pcb
                self.state.cuts
                self.state.cut_method
                self.state.mb_diameter
                self.state.mb_spacing
                Canvas(self.painter).layout(width=self.state.canvas_width, height=self.state.canvas_height).style(bgColor=0x000000)

                Spacer()

ui = UI()
ui.run()
