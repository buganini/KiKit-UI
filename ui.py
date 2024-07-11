#!/usr/bin/env /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
from kikit import panelize
from kikit.units import mm
import pcbnew
from shapely import MultiPoint, affinity

import sys
sys.path.append("/Users/buganini/repo/buganini/PUI")
from PUI.PySide6 import *

class PCB():
    def __init__(self, boardfile):
        self.file = boardfile
        board = pcbnew.LoadBoard(boardfile)
        bbox = panelize.findBoardBoundingBox(board)
        self.width = bbox.GetWidth()
        self.height = bbox.GetHeight()
        self.x = 0
        self.y = 0
        self.rotate = 0

class UI(Application):
    def __init__(self):
        super().__init__()
        self.state = State()
        self.state.pcb = []
        self.state.scale = 1
        self.state.output = ""
        self.state.canvas_width = 800
        self.state.canvas_height = 600
        self.state.focus = None

        inputs = sys.argv[1:]
        for f in inputs:
            self.state.pcb.append(PCB(f))

        self.autoScale()

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
        self.state.scale = min(sw, sh) / 2

    def addPCB(self):
        boardfile = OpenFileDialog("Open PCB", "KiCad PCB (*.kicad_pcb)")
        self.state.pcb.append(PCB(boardfile))
        self.autoScale()

    def save(self):
        self.state.output = SaveFile(self.state.output, "KiCad PCB (*.kicad_pcb)")
        if not self.state.output.endswith(".kicad_pcb"):
            self.state.output += ".kicad_pcb"
        panel = panelize.Panel(self.state.output)
        x = 0
        y = 0
        for pcb in self.state.pcb:
            panel.appendBoard(pcb.file, pcbnew.VECTOR2I(pcb.x, pcb.y), origin=panelize.Origin.TopLeft, tolerance=panelize.fromMm(1), inheritDrc=False)

        cuts = panel.buildTabsFromAnnotations(fillet=1*mm)
        panel.makeMouseBites(cuts, diameter=0.5 * mm, spacing=0.75 * mm, offset=0 * mm, prolongation=0 * mm)

        panel.save()

    def setFocus(self, pcb):
        self.state.focus = pcb

    def rotateCCW(self, pcb):
        pcb.rotate -= 90
        self.state()

    def rotateCW(self, pcb):
        pcb.rotate += 90
        self.state()

    def drawPCB(self, canvas, pcb, highlight):
        stroke = 0x00FFFF if highlight else 0x0000FF
        rect = MultiPoint([(pcb.x, pcb.y), (pcb.x + pcb.width, pcb.y + pcb.height)])
        rect = affinity.rotate(rect, pcb.rotate, origin='center', use_radians=False)
        canvas.drawRect(rect.geoms[0].x * self.state.scale, rect.geoms[0].y * self.state.scale, rect.geoms[1].x * self.state.scale, rect.geoms[1].y * self.state.scale, stroke=stroke)

    def painter(self, canvas, pcbs):
        for pcb in pcbs:
            if pcb is self.state.focus:
                continue
            self.drawPCB(canvas, pcb, False)

        for pcb in pcbs:
            if pcb is not self.state.focus:
                continue
            self.drawPCB(canvas, pcb, True)

    def content(self):
        with VBox():
            with HBox():
                Button("Add PCB").click(self.addPCB)
                Spacer()
                Button("Save").click(self.save)

            with Grid():
                for i,pcb in enumerate(self.state.pcb):
                    Label(f"{i+1}. {pcb.file}").click(self.setFocus, pcb).grid(row=i, column=0)
                    Button("CCW").click(self.rotateCCW, pcb).grid(row=i, column=1)
                    Button("CW").click(self.rotateCW, pcb).grid(row=i, column=2)

            Canvas(self.painter, self.state.pcb).layout(width=self.state.canvas_width, height=self.state.canvas_height)

ui = UI()
ui.run()
