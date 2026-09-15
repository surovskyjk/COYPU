# Shared pyqtgraph plotting infrastructure used by every plot dock and popup
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor
from PySide6.QtWidgets import QFileDialog, QMenu, QToolBar

import icons

# Single source of truth for every series colour used across the application
SERIES_STYLES = {
    "cant": {"color": "#111111", "width": 2},
    "cantPossible": {"color": "#2e9e4f", "width": 2},
    "cDef100": {"color": "#d64545", "width": 2},
    "cDef130": {"color": "#0f8b8d", "width": 2},
    "cDef150": {"color": "#8a4fd3", "width": 2},
    "cDefK": {"color": "#4a7fd4", "width": 2},
    "cantDef100": {"color": "#e8734a", "width": 2, "dash": True},
    "cantDef130": {"color": "#35b6c4", "width": 2, "dash": True},
    "cantDef150": {"color": "#b06fe0", "width": 2, "dash": True},
    "cantDefK": {"color": "#5b8ede", "width": 2, "dash": True},
    "curvature": {"color": "#00b4d8", "width": 3},
    "curvatureBaseline": {"color": "#888888", "width": 2, "dash": True},
    "speedLimits": {"color": "#111111", "width": 2},
    "speedLimits100": {"color": "#d64545", "width": 2},
    "speedLimits130": {"color": "#0f8b8d", "width": 2},
    "speedLimits150": {"color": "#8a4fd3", "width": 2},
    "speedLimitsK": {"color": "#4a7fd4", "width": 2},
    "slewPositive": {"color": "#e0703d", "width": 2},
    "slewNegative": {"color": "#3d8fe0", "width": 2},
    "slewThreshold": {"color": "#d64545", "width": 1, "dash": True},
    "profile": {"color": "#8a8a8a", "width": 2},
    "simulated": {"color": "#d19a66", "width": 2},
}

# Per vehicle colour banks mirroring the previous matplotlib palettes, one entry per MAX_VEHICLES slot
VEHICLE_SPEED_COLORS = ["#d64545", "#2e9e4f", "#4a7fd4", "#a04fd6", "#d68f2e"]
VEHICLE_LIMIT_COLORS = ["#f0a0a0", "#a8dcae", "#a8c8ef", "#d4a8ef", "#f0d0a0"]
VEHICLE_TRACTION_COLORS = ["#2e9e4f", "#63d17c", "#1c6b34", "#7fd68a", "#0f7a2e"]
VEHICLE_BRAKING_COLORS = ["#d64545", "#8f2020", "#f08e8e", "#b03030", "#f0aaaa"]
VEHICLE_RESISTANCE_COLORS = ["#e08a2e", "#f0a95c", "#c9a227", "#f0c67a", "#b8801a"]

# Qualitative colour bank for overlaying an arbitrary number of batch variants on one plot
VARIANT_COLORS = ["#d64545", "#2e9e4f", "#4a7fd4", "#a04fd6", "#d68f2e",
                   "#0f8b8d", "#e377c2", "#8c564b", "#bcbd22", "#17becf"]

# Series that keep the theme foreground colour so they stay readable on both themes
FOREGROUND_SERIES = ("cant", "speedLimits")

# Interaction mode identifiers exposed through the plot context menu
MODE_BOX_ZOOM = "boxZoom"
MODE_PAN = "pan"
MODE_AXIS_LOCK = "axisLock"

# Matplotlib tableau colour names still used by the popup series descriptors
TAB_COLORS = {
    "tab:blue": "#1f77b4",
    "tab:orange": "#ff7f0e",
    "tab:green": "#2ca02c",
    "tab:red": "#d62728",
    "tab:purple": "#9467bd",
    "tab:brown": "#8c564b",
    "tab:pink": "#e377c2",
    "tab:gray": "#7f7f7f",
    "tab:grey": "#7f7f7f",
    "tab:olive": "#bcbd22",
    "tab:cyan": "#17becf",
}

# Colour used when a descriptor names something Qt cannot resolve
FALLBACK_COLOR = "#888888"

# Captions of vertical markers hug the bottom axis, clear of a top corner legend
MARKER_LABEL_POSITION_VERTICAL = 0.02

# Captions of horizontal markers sit at the right end, clear of a left corner legend
MARKER_LABEL_POSITION_HORIZONTAL = 0.98

# Fraction of the visible range past which a caption flips to the other side
MARKER_FLIP_FRACTION = 0.75

# Above this many visible curves the legend wraps into a second column, and then a third
LEGEND_SINGLE_COLUMN_MAX = 6
LEGEND_TWO_COLUMN_MAX = 12

# Hard ceiling on legend columns, past this the labels themselves become unreadable
LEGEND_MAX_COLUMNS = 3

# Legend placement offsets, negative values anchor to the opposite plot edge
LEGEND_OFFSETS = {
    "topLeft": (10, 10),
    "topRight": (-10, 10),
    "bottomLeft": (10, -10),
    "bottomRight": (-10, -10),
}


# Translate a colour name into something QColor accepts
def resolveColor(color):
    if not isinstance(color, str):
        return color if color is not None else FALLBACK_COLOR

    mapped = TAB_COLORS.get(color.lower())
    if mapped is not None:
        return mapped
    if QColor.isValidColorName(color):
        return color
    return FALLBACK_COLOR


# Build a pen from the shared style table with optional overrides
def penFor(seriesKey, color=None, width=None, dash=None):
    style = SERIES_STYLES.get(seriesKey, {})
    penColor = resolveColor(color or style.get("color", FALLBACK_COLOR))
    penWidth = width if width is not None else style.get("width", 2)
    useDash = style.get("dash", False) if dash is None else dash

    if useDash:
        return pg.mkPen(penColor, width=penWidth, style=Qt.PenStyle.DashLine)
    return pg.mkPen(penColor, width=penWidth)


# Translate a matplotlib style line style string into a Qt pen style
def penStyleFromLineStyle(lineStyle):
    if lineStyle == "--":
        return Qt.PenStyle.DashLine
    if lineStyle == ":":
        return Qt.PenStyle.DotLine
    if lineStyle == "-.":
        return Qt.PenStyle.DashDotLine
    return Qt.PenStyle.SolidLine


# Translate a matplotlib marker character into a pyqtgraph symbol
def symbolFromMarker(marker):
    markerMap = {"o": "o", "s": "s", "^": "t", "v": "t1", "d": "d", "+": "+", "x": "x"}
    return markerMap.get(marker)


class FractionAxisItem(pg.AxisItem):
    # Render curvature tick values as a one over radius fraction
    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            if abs(value) < 1e-9:
                labels.append("0")
                continue
            sign = "-" if value < 0 else ""
            labels.append(f"{sign}1/{abs(int(round(1.0 / value)))}")
        return labels


class CoypuPlotWidget(pg.GraphicsLayoutWidget):
    # Emitted with the chainage in kilometres whenever a tracked plot is hovered
    cursorMoved = Signal(float)

    def __init__(self, lan, parent=None):
        super().__init__(parent)

        self.lan = lan
        self.isDark = False
        self.tokens = None

        self.plotItems = {}
        self.plotLegends = {}
        self.plotSeries = {}
        self.plotCrosshairs = {}
        self.plotStationMarkers = {}
        self.plotRightViews = {}
        self.plotMenus = {}
        self.plotTitles = {}

        self.stationList = []
        self.showStationMarkers = True
        self.managedMarkers = []
        self.anchoredPlots = set()
        self.highlightedSeries = {}
        self.cursorAxis = "x"
        self.mouseProxy = None
        self.readoutLabel = None

        # Active unit system, km/h and km when true, m/s and m when false
        self.useKmh = False
        self.readoutPlotKey = None
        self.detachedWindows = []

        # Plot keys currently re-entering syncZeroAlignment, guards against feedback loops
        self.zeroLockBusy = set()
        # Plot keys whose secondary axis keeps its zero line locked to the primary axis
        self.zeroLockedPlots = set()
        # Span the secondary axis keeps relative to the primary, so proportion survives a vertical zoom
        self.zeroLockRatios = {}
        # Plot keys the user explicitly released for vertical zoom, every plot is chainage only by default
        self.verticalZoomPlots = set()
        # Callbacks restoring the vertical range a plot wants, registered by the owning dock
        self.yRangeHandlers = {}
        # Interaction mode in force per plot, so releasing the vertical axis can re-apply it
        self.plotModes = {}

    # Register a plot row and wire its legend, crosshair and context menu
    def addPlotRow(self, plotKey, row, leftLabel="", bottomLabel="", rightAxis=None,
                   withLegend=True, withCrosshair=True, legendCorner="topLeft"):
        axisItems = {}
        if rightAxis == "fraction":
            axisItems["right"] = FractionAxisItem("right")

        plotItem = self.addPlot(row=row, col=0, axisItems=axisItems or None)
        plotItem.showGrid(x=True, y=True, alpha=0.3)
        plotItem.setLabel("left", leftLabel)
        plotItem.setLabel("bottom", bottomLabel)
        # No implicit auto range padding, every explicit setYRange call stays exact
        plotItem.vb.setDefaultPadding(0.0)
        # Navigation runs along the chainage axis, so the vertical scale never moves by accident
        plotItem.vb.setMouseEnabled(x=True, y=False)

        self.plotItems[plotKey] = plotItem
        self.plotSeries[plotKey] = {}
        self.plotStationMarkers[plotKey] = []
        self.highlightedSeries[plotKey] = None
        self.plotModes[plotKey] = MODE_PAN

        if withLegend:
            # Tight vertical spacing keeps the legend compact over the data
            legend = plotItem.addLegend(offset=LEGEND_OFFSETS.get(legendCorner, (10, 10)),
                                        verSpacing=-6, horSpacing=6, labelTextSize="7pt")
            legend.layout.setContentsMargins(2, 1, 2, 1)
            self.plotLegends[plotKey] = legend

        if withCrosshair:
            crosshair = pg.InfiniteLine(angle=90 if self.cursorAxis == "x" else 0, movable=False)
            plotItem.addItem(crosshair, ignoreBounds=True)
            self.plotCrosshairs[plotKey] = crosshair

        self.installPlotContextMenu(plotKey)
        return plotItem

    # Attach a second view box so a plot can carry an independent right hand axis
    def addRightAxis(self, plotKey, label=""):
        plotItem = self.plotItems[plotKey]
        rightView = pg.ViewBox()

        plotItem.showAxis("right")
        plotItem.scene().addItem(rightView)
        plotItem.getAxis("right").linkToView(rightView)
        rightView.setXLink(plotItem)
        plotItem.setLabel("right", label)

        # The secondary view sits over the primary one, taking the wheel here would detach its zero line
        rightView.setMouseEnabled(x=False, y=False)
        rightView.disableAutoRange()

        self.plotRightViews[plotKey] = rightView
        plotItem.vb.sigResized.connect(lambda vb, key=plotKey: self.syncRightView(key))
        self.syncRightView(plotKey)
        return rightView

    # Drop the secondary view box so a redraw without one starts clean
    def removeRightAxis(self, plotKey):
        self.zeroLockRatios.pop(plotKey, None)
        rightView = self.plotRightViews.pop(plotKey, None)
        if rightView is None:
            return

        plotItem = self.plotItems.get(plotKey)
        if plotItem is not None:
            plotItem.scene().removeItem(rightView)
            plotItem.hideAxis("right")

    # Keep the secondary view box aligned with the primary one after a resize
    def syncRightView(self, plotKey):
        plotItem = self.plotItems.get(plotKey)
        rightView = self.plotRightViews.get(plotKey)
        if plotItem is None or rightView is None:
            return
        rightView.setGeometry(plotItem.vb.sceneBoundingRect())
        rightView.linkedViewChanged(plotItem.vb, rightView.XAxis)

    # Keep the zero line of a secondary axis locked onto the zero line of its primary axis
    def enableZeroLock(self, plotKey):
        plotItem = self.plotItems.get(plotKey)
        rightView = self.plotRightViews.get(plotKey)
        if plotItem is None or rightView is None:
            return

        # Connect only once per plot, a rebuilt right view is picked up by lookup at sync time
        if plotKey not in self.zeroLockedPlots:
            plotItem.vb.sigYRangeChanged.connect(
                lambda viewBox, viewRange, key=plotKey: self.syncZeroAlignment(key))
            self.zeroLockedPlots.add(plotKey)

        self.captureZeroLockRatio(plotKey)
        self.syncZeroAlignment(plotKey)

    # Freeze the span ratio the two axes currently show, so a later zoom scales them together
    def captureZeroLockRatio(self, plotKey):
        plotItem = self.plotItems.get(plotKey)
        rightView = self.plotRightViews.get(plotKey)
        if plotItem is None or rightView is None:
            return

        primaryLow, primaryHigh = plotItem.vb.viewRange()[1]
        secondaryLow, secondaryHigh = rightView.viewRange()[1]
        primarySpan = primaryHigh - primaryLow
        secondarySpan = secondaryHigh - secondaryLow
        if primarySpan <= 0 or secondarySpan <= 0:
            return

        self.zeroLockRatios[plotKey] = secondarySpan / primarySpan

    # Re-anchor the secondary Y range so zero sits at the same fraction of both views
    def syncZeroAlignment(self, plotKey):
        if plotKey in self.zeroLockBusy:
            return

        plotItem = self.plotItems.get(plotKey)
        rightView = self.plotRightViews.get(plotKey)
        if plotItem is None or rightView is None:
            return

        primaryLow, primaryHigh = plotItem.vb.viewRange()[1]
        primarySpan = primaryHigh - primaryLow
        secondaryLow, secondaryHigh = rightView.viewRange()[1]
        secondarySpan = secondaryHigh - secondaryLow
        if primarySpan <= 0 or secondarySpan <= 0:
            return

        # Scaling the secondary by the captured ratio keeps curvature in proportion with cant at any zoom
        ratio = self.zeroLockRatios.get(plotKey)
        if ratio is not None and ratio > 0:
            secondarySpan = primarySpan * ratio

        # Zero of the secondary axis lands on the same view fraction as zero of the primary axis
        zeroFraction = (0.0 - primaryLow) / primarySpan
        newLow = -zeroFraction * secondarySpan

        self.zeroLockBusy.add(plotKey)
        try:
            rightView.setYRange(newLow, newLow + secondarySpan, padding=0)
        finally:
            self.zeroLockBusy.discard(plotKey)

    # Add or replace one curve, the registry keeps everything needed to redraw it
    def setSeriesData(self, plotKey, seriesKey, x, y, name="", styleKey=None, color=None,
                      width=None, dash=None, step=False, symbol=None, onRight=False,
                      isVisible=True, alpha=None):
        plotItem = self.plotItems.get(plotKey)
        if plotItem is None:
            return None

        xValues = np.asarray(x, dtype=float)
        yValues = np.asarray(y, dtype=float)
        if xValues.size == 0 or yValues.size == 0:
            return None

        pen = penFor(styleKey or seriesKey, color=color, width=width, dash=dash)
        if alpha is not None:
            penColor = pen.color()
            penColor.setAlphaF(float(alpha))
            pen.setColor(penColor)

        plotArgs = {"pen": pen, "connect": "finite", "name": name or None}
        if step:
            plotArgs["stepMode"] = "right"
        if symbol:
            plotArgs["symbol"] = symbol
            plotArgs["symbolSize"] = 5
            plotArgs["symbolBrush"] = pen.color()
            plotArgs["symbolPen"] = pen.color()

        item = pg.PlotDataItem(xValues, yValues, **plotArgs)

        targetView = self.plotRightViews.get(plotKey) if onRight else None
        if targetView is not None:
            targetView.addItem(item)
        else:
            plotItem.addItem(item)

        item.setVisible(bool(isVisible))
        self.plotSeries[plotKey][seriesKey] = {
            "item": item,
            "name": name,
            "pen": pen,
            "step": step,
            "symbol": symbol,
            "onRight": onRight,
            "x": xValues,
            "y": yValues,
            "visible": bool(isVisible),
        }

        self.rebuildLegend(plotKey)
        return item

    # Drop every curve and annotation from one plot
    def clearPlot(self, plotKey):
        plotItem = self.plotItems.get(plotKey)
        if plotItem is None:
            return

        rightView = self.plotRightViews.get(plotKey)
        for entry in self.plotSeries.get(plotKey, {}).values():
            if entry["onRight"] and rightView is not None:
                rightView.removeItem(entry["item"])
            else:
                plotItem.removeItem(entry["item"])

        self.plotSeries[plotKey] = {}
        self.highlightedSeries[plotKey] = None
        self.rebuildLegend(plotKey)

    # Toggle one curve and refresh the legend so hidden series disappear from it
    def setSeriesVisible(self, plotKey, seriesKey, isVisible):
        entry = self.plotSeries.get(plotKey, {}).get(seriesKey)
        if entry is None:
            return
        entry["visible"] = bool(isVisible)
        entry["item"].setVisible(bool(isVisible))
        self.rebuildLegend(plotKey)

    # Rebuild the legend from the currently visible curves of one plot
    def rebuildLegend(self, plotKey):
        legend = self.plotLegends.get(plotKey)
        if legend is None:
            return

        legend.clear()
        visibleEntries = [entry for entry in self.plotSeries.get(plotKey, {}).values()
                          if entry["visible"] and entry["name"]]

        # A single tall column overflows the short dock rows, so long legends wrap instead of clipping
        legend.setColumnCount(self.legendColumnCount(len(visibleEntries)))
        for entry in visibleEntries:
            legend.addItem(entry["item"], entry["name"])

    # How many columns a legend needs to stay inside its plot row
    def legendColumnCount(self, entryCount):
        if entryCount <= LEGEND_SINGLE_COLUMN_MAX:
            return 1
        if entryCount <= LEGEND_TWO_COLUMN_MAX:
            return 2
        return LEGEND_MAX_COLUMNS

    # Store the stop list and redraw the vertical station indicators
    def setStations(self, stations):
        self.stationList = list(stations or [])
        self.refreshStationMarkers()

    # Draw one labelled vertical line per station on every registered plot
    def refreshStationMarkers(self):
        foreground = self.tokens["plotForeground"] if self.tokens else "#666666"

        for plotKey, plotItem in self.plotItems.items():
            for marker in self.plotStationMarkers.get(plotKey, []):
                plotItem.removeItem(marker)
                self.forgetMarker(marker)
            self.plotStationMarkers[plotKey] = []

            if not self.showStationMarkers:
                continue

            for stationKm, stationName in self.stationList:
                marker = self.buildMarker(plotItem, float(stationKm), 90, "#8a8a8a",
                                          stationName, foreground)
                self.plotStationMarkers[plotKey].append(marker)

        self.updateMarkerAnchors()

    # Create one marker line whose caption is kept inside the plot at all times
    def buildMarker(self, plotItem, position, angle, color, label, labelColor,
                    penStyle=Qt.PenStyle.DashLine):
        isVertical = angle == 90

        labelOpts = None
        if label:
            # Captions stay horizontal, a rotated caption is taller than a stacked plot
            labelPosition = (MARKER_LABEL_POSITION_VERTICAL if isVertical
                             else MARKER_LABEL_POSITION_HORIZONTAL)
            labelOpts = {"position": labelPosition, "color": labelColor,
                         "fill": None, "anchor": (0.0, 1.0)}

        marker = pg.InfiniteLine(pos=float(position), angle=angle, movable=False,
                                 pen=pg.mkPen(color, width=1, style=penStyle),
                                 label=label or None, labelOpts=labelOpts)
        plotItem.addItem(marker, ignoreBounds=True)

        if label:
            self.managedMarkers.append((plotItem, marker, isVertical))
            self.trackPlotRange(plotItem)

        return marker

    # Drop a marker from the anchor bookkeeping when its plot is cleared
    def forgetMarker(self, marker):
        self.managedMarkers = [entry for entry in self.managedMarkers if entry[1] is not marker]

    # Recompute the caption anchors whenever the visible range of a plot changes
    def trackPlotRange(self, plotItem):
        if plotItem in self.anchoredPlots:
            return
        self.anchoredPlots.add(plotItem)
        plotItem.vb.sigRangeChanged.connect(lambda *args: self.updateMarkerAnchors())

    # Flip each caption away from the view edge it would otherwise overflow
    def updateMarkerAnchors(self):
        for plotItem, marker, isVertical in self.managedMarkers:
            label = getattr(marker, "label", None)
            if label is None:
                continue

            xRange, yRange = plotItem.vb.viewRange()
            low, high = xRange if isVertical else yRange
            span = high - low
            fraction = 0.5 if span <= 0 else (float(marker.value()) - low) / span

            if isVertical:
                # Near the right edge the caption is drawn to the left of the line
                anchorX = 1.0 if fraction > MARKER_FLIP_FRACTION else 0.0
                anchor = (anchorX, 1.0)
            else:
                # Near the top edge the caption drops below its horizontal line
                anchorY = 0.0 if fraction > MARKER_FLIP_FRACTION else 1.0
                anchor = (1.0, anchorY)

            # Both slots are set because pyqtgraph picks one of them on every update
            label.anchors = [anchor, anchor]
            label.setAnchor(anchor)

    # Show or hide the station indicators across every plot
    def setStationMarkersVisible(self, isVisible):
        self.showStationMarkers = bool(isVisible)
        self.refreshStationMarkers()

    # Apply the active theme to the canvas, the axes and the crosshairs
    def applyTheme(self, isDark, tokens=None):
        self.isDark = isDark
        self.tokens = tokens

        background = tokens["plotBackground"] if tokens else ("#1e1e1e" if isDark else "#ffffff")
        foreground = tokens["plotForeground"] if tokens else ("#e6e6e6" if isDark else "#1c1c1c")

        self.setBackground(background)

        for plotItem in self.plotItems.values():
            for axisName in ("left", "bottom", "right", "top"):
                axis = plotItem.getAxis(axisName)
                if axis is None:
                    continue
                axis.setPen(foreground)
                axis.setTextPen(foreground)

        crosshairPen = pg.mkPen(color="#4a90d9" if isDark else "#2f6fb5", width=1,
                                style=Qt.PenStyle.DashLine)
        for crosshair in self.plotCrosshairs.values():
            crosshair.setPen(crosshairPen)

        if self.readoutLabel is not None:
            self.readoutLabel.setColor(foreground)

        # Series drawn in the foreground colour need a new pen on every theme switch
        for plotKey, seriesMap in self.plotSeries.items():
            for seriesKey, entry in seriesMap.items():
                if seriesKey in FOREGROUND_SERIES:
                    entry["pen"] = pg.mkPen(foreground, width=2)
                    entry["item"].setPen(entry["pen"])

        for legend in self.plotLegends.values():
            legend.setLabelTextColor(foreground)

        self.refreshStationMarkers()

    # Save the whole canvas as a high resolution raster image, callable without a toolbar
    def exportSceneImage(self, filePath, widthMultiplier=3):
        exporter = pg.exporters.ImageExporter(self.scene())
        exporter.parameters()["width"] = int(self.width() * widthMultiplier)
        exporter.export(filePath)

    # Save the whole canvas as a vector SVG image, callable without a toolbar
    def exportSceneVector(self, filePath):
        exporter = pg.exporters.SVGExporter(self.scene())
        exporter.export(filePath)

    # Save a single plot row as a high resolution raster image, e.g. one variant-overlay panel of several
    def exportPlotItemImage(self, plotKey, filePath, widthMultiplier=3):
        plotItem = self.plotItems.get(plotKey)
        if plotItem is None:
            return
        exporter = pg.exporters.ImageExporter(plotItem)
        exporter.parameters()["width"] = int(self.width() * widthMultiplier)
        exporter.export(filePath)

    # Save a single plot row as a vector SVG image
    def exportPlotItemVector(self, plotKey, filePath):
        plotItem = self.plotItems.get(plotKey)
        if plotItem is None:
            return
        exporter = pg.exporters.SVGExporter(plotItem)
        exporter.export(filePath)

    # Start reporting the chainage under the mouse from every tracked plot
    def enableCursorTracking(self, readoutPlotKey=None):
        self.readoutPlotKey = readoutPlotKey or next(iter(self.plotItems), None)
        if self.readoutPlotKey is not None:
            self.readoutLabel = pg.TextItem(anchor=(0, 1))
            self.plotItems[self.readoutPlotKey].addItem(self.readoutLabel, ignoreBounds=True)

        # A signal proxy keeps the crosshair responsive without flooding the event loop
        self.mouseProxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60,
                                         slot=self.onMouseMoved)

    # Hit test every plot so hovering any of them drives the shared crosshair
    def onMouseMoved(self, event):
        position = event[0]

        for plotKey, plotItem in self.plotItems.items():
            # A row currently taken out of the layout has no scene and must be skipped
            if plotItem.scene() is None:
                continue
            if not plotItem.sceneBoundingRect().contains(position):
                continue

            mousePoint = plotItem.vb.mapSceneToView(position)
            value = float(mousePoint.x()) if self.cursorAxis == "x" else float(mousePoint.y())

            self.setCursorStation(value)
            self.updateReadout(value)
            self.cursorMoved.emit(value)
            return

    # Switch the widget between km/h, km and m/s, m without touching the plotted data
    def setUnitSystem(self, useKmh):
        self.useKmh = bool(useKmh)

    # Multiplier turning an internal m/s speed into the displayed unit
    def displaySpeedFactor(self):
        return 3.6 if self.useKmh else 1.0

    # Multiplier turning an internal kilometre chainage into the displayed unit
    def displayDistanceFactor(self):
        return 1.0 if self.useKmh else 1000.0

    def speedUnitLabel(self):
        return self.lan.get("unitKmh", "km/h") if self.useKmh else self.lan.get("unitMs", "m/s")

    def distanceUnitLabel(self):
        return self.lan.get("unitKm", "km") if self.useKmh else self.lan.get("unitM", "m")

    # Chainage formatted in the active distance unit, used by every readout
    def formatChainage(self, stationKm):
        if self.useKmh:
            return f"{stationKm:.3f} {self.distanceUnitLabel()}"
        return f"{stationKm * 1000.0:.1f} {self.distanceUnitLabel()}"

    # Value of one registered curve at a chainage, NaN outside the range it actually covers
    def seriesValueAt(self, plotKey, seriesKey, stationKm):
        entry = self.plotSeries.get(plotKey, {}).get(seriesKey)
        if entry is None or entry["x"].size < 2:
            return float("nan")
        return float(np.interp(stationKm, entry["x"], entry["y"],
                               left=float("nan"), right=float("nan")))

    # Move the readout label to the top of its plot at the current chainage
    def updateReadout(self, value):
        if self.readoutLabel is None or self.readoutPlotKey is None:
            return
        viewRange = self.plotItems[self.readoutPlotKey].vb.viewRange()
        self.readoutLabel.setPos(value, viewRange[1][1])
        self.readoutLabel.setText(self.formatChainage(value))

    # Drive every crosshair from an external source such as the map
    def setCursorStation(self, stationKm):
        for crosshair in self.plotCrosshairs.values():
            crosshair.setPos(float(stationKm))

    # Extend the native view box menu instead of replacing it
    def installPlotContextMenu(self, plotKey):
        plotItem = self.plotItems[plotKey]
        viewBox = plotItem.vb
        menu = viewBox.menu
        lan = self.lan

        menu.addSeparator()

        expandAction = QAction(lan.get("plotExpand", "Expand / Detach to large window"), menu)
        expandAction.setIcon(icons.makeIcon("expand"))
        expandAction.triggered.connect(lambda checked=False, key=plotKey: self.openDetachedWindow(key))
        menu.addAction(expandAction)

        modeMenu = QMenu(lan.get("plotInteraction", "Interaction mode"), menu)
        modeGroup = QActionGroup(modeMenu)
        modeGroup.setExclusive(True)
        modeDefinitions = [
            (MODE_BOX_ZOOM, lan.get("plotModeBoxZoom", "Rectangular box zoom")),
            (MODE_PAN, lan.get("plotModePan", "Mouse drag pan")),
            (MODE_AXIS_LOCK, lan.get("plotModeAxisLock", "Axis lock")),
        ]
        for modeKey, modeLabel in modeDefinitions:
            modeAction = QAction(modeLabel, modeMenu)
            modeAction.setCheckable(True)
            modeAction.setChecked(modeKey == MODE_PAN)
            modeAction.triggered.connect(
                lambda checked=False, key=plotKey, mode=modeKey: self.setInteractionMode(key, mode))
            modeGroup.addAction(modeAction)
            modeMenu.addAction(modeAction)
        menu.addMenu(modeMenu)

        verticalZoomAction = QAction(lan.get("plotVerticalZoom", "Vertical zoom"), menu)
        verticalZoomAction.setCheckable(True)
        verticalZoomAction.setChecked(False)
        verticalZoomAction.setToolTip(lan.get(
            "plotVerticalZoomTip",
            "Navigation follows the chainage axis, enable this to rescale the vertical axis as well"))
        verticalZoomAction.triggered.connect(
            lambda checked, key=plotKey: self.setVerticalZoomEnabled(key, checked))
        menu.addAction(verticalZoomAction)

        resetViewAction = QAction(lan.get("plotResetFitY", "Reset view / Fit Y"), menu)
        resetViewAction.setIcon(icons.makeIcon("resetView"))
        resetViewAction.triggered.connect(lambda checked=False, key=plotKey: self.resetPlotView(key))
        menu.addAction(resetViewAction)

        gridAction = QAction(lan.get("plotToggleGrid", "Toggle grid lines"), menu)
        gridAction.setCheckable(True)
        gridAction.setChecked(True)
        gridAction.setIcon(icons.makeIcon("grid"))
        gridAction.triggered.connect(
            lambda checked, key=plotKey: self.setGridVisible(key, checked))
        menu.addAction(gridAction)

        stationAction = QAction(lan.get("plotToggleStations", "Toggle station markers"), menu)
        stationAction.setCheckable(True)
        stationAction.setChecked(True)
        stationAction.setIcon(icons.makeIcon("station"))
        stationAction.triggered.connect(
            lambda checked: self.setStationMarkersVisible(checked))
        menu.addAction(stationAction)

        highlightMenu = QMenu(lan.get("plotHighlight", "Highlight series"), menu)
        highlightMenu.aboutToShow.connect(
            lambda key=plotKey, target=highlightMenu: self.buildHighlightMenu(key, target))
        menu.addMenu(highlightMenu)

        self.plotMenus[plotKey] = {
            "menu": menu,
            "modeMenu": modeMenu,
            "highlightMenu": highlightMenu,
            "expandAction": expandAction,
            "gridAction": gridAction,
            "stationAction": stationAction,
            "verticalZoomAction": verticalZoomAction,
            "resetViewAction": resetViewAction,
            "modeActions": modeGroup.actions(),
        }

    # Populate the highlight submenu from the curves the plot currently holds
    def buildHighlightMenu(self, plotKey, highlightMenu):
        highlightMenu.clear()
        lan = self.lan

        noneAction = QAction(lan.get("plotHighlightNone", "No highlight"), highlightMenu)
        noneAction.triggered.connect(lambda checked=False, key=plotKey: self.highlightSeries(key, None))
        highlightMenu.addAction(noneAction)
        highlightMenu.addSeparator()

        for seriesKey, entry in self.plotSeries.get(plotKey, {}).items():
            if not entry["visible"]:
                continue
            label = entry["name"] or seriesKey
            seriesAction = QAction(label, highlightMenu)
            seriesAction.setCheckable(True)
            seriesAction.setChecked(self.highlightedSeries.get(plotKey) == seriesKey)
            seriesAction.triggered.connect(
                lambda checked=False, key=plotKey, target=seriesKey: self.highlightSeries(key, target))
            highlightMenu.addAction(seriesAction)

    # Emphasise one curve by fading every other curve of the same plot
    def highlightSeries(self, plotKey, seriesKey):
        self.highlightedSeries[plotKey] = seriesKey

        for currentKey, entry in self.plotSeries.get(plotKey, {}).items():
            pen = pg.mkPen(entry["pen"])
            penColor = pen.color()

            if seriesKey is None:
                penColor.setAlphaF(1.0)
                pen.setWidth(entry["pen"].width())
            elif currentKey == seriesKey:
                penColor.setAlphaF(1.0)
                pen.setWidth(max(entry["pen"].width() + 1, 3))
            else:
                penColor.setAlphaF(0.25)

            pen.setColor(penColor)
            entry["item"].setPen(pen)

    # Switch a plot between box zoom, drag pan and a fully locked view
    def setInteractionMode(self, plotKey, mode):
        plotItem = self.plotItems.get(plotKey)
        if plotItem is None:
            return
        viewBox = plotItem.vb
        self.plotModes[plotKey] = mode

        # Vertical navigation stays off unless the user released it for this plot
        isVerticalEnabled = plotKey in self.verticalZoomPlots

        if mode == MODE_BOX_ZOOM:
            viewBox.setMouseMode(pg.ViewBox.RectMode)
            viewBox.setMouseEnabled(x=True, y=isVerticalEnabled)
        elif mode == MODE_AXIS_LOCK:
            viewBox.setMouseEnabled(x=False, y=False)
        else:
            viewBox.setMouseMode(pg.ViewBox.PanMode)
            viewBox.setMouseEnabled(x=True, y=isVerticalEnabled)

    # Release or re-lock the vertical axis of one plot, re-applying its current interaction mode
    def setVerticalZoomEnabled(self, plotKey, isEnabled):
        if isEnabled:
            self.verticalZoomPlots.add(plotKey)
        else:
            self.verticalZoomPlots.discard(plotKey)
        self.setInteractionMode(plotKey, self.plotModes.get(plotKey, MODE_PAN))

    # Register the routine that restores the vertical range a plot wants after a reset
    def setYRangeHandler(self, plotKey, handler):
        self.yRangeHandlers[plotKey] = handler

        # Owning the vertical policy rules out auto ranging, which would fight it on every redraw
        plotItem = self.plotItems.get(plotKey)
        if plotItem is not None:
            plotItem.vb.disableAutoRange(axis="y")

    # Re-fit one plot, the chainage axis to the data and the vertical axis to its own policy
    def resetPlotView(self, plotKey):
        plotItem = self.plotItems.get(plotKey)
        if plotItem is None:
            return

        plotItem.vb.enableAutoRange(axis="x")
        handler = self.yRangeHandlers.get(plotKey)
        if handler is not None:
            handler()
        else:
            # Without a dock supplied policy the data extent is the best available vertical fit
            plotItem.vb.enableAutoRange(axis="y")
            plotItem.vb.disableAutoRange(axis="y")

        if plotKey in self.zeroLockedPlots:
            self.captureZeroLockRatio(plotKey)
            self.syncZeroAlignment(plotKey)

    # Shift is the explicit opt in for a vertical zoom while the axis is otherwise locked
    def wheelEvent(self, event):
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            super().wheelEvent(event)
            return

        released = [key for key, plotItem in self.plotItems.items()
                    if key not in self.verticalZoomPlots and self.plotModes.get(key, MODE_PAN) != MODE_AXIS_LOCK]
        for plotKey in released:
            self.plotItems[plotKey].vb.setMouseEnabled(x=True, y=True)
        try:
            super().wheelEvent(event)
        finally:
            for plotKey in released:
                self.plotItems[plotKey].vb.setMouseEnabled(x=True, y=False)

    # Show or hide the grid of a single plot
    def setGridVisible(self, plotKey, isVisible):
        plotItem = self.plotItems.get(plotKey)
        if plotItem is not None:
            plotItem.showGrid(x=bool(isVisible), y=bool(isVisible), alpha=0.3)

    # Collect the drawable descriptors of one plot for the detached window
    def buildSeriesDescriptors(self, plotKey):
        primary = []
        secondary = []

        for entry in self.plotSeries.get(plotKey, {}).values():
            if not entry["visible"]:
                continue
            descriptor = {
                "x": entry["x"],
                "y": entry["y"],
                "label": entry["name"],
                "color": entry["pen"].color().name(),
                "step": entry["step"],
                "marker": entry["symbol"],
            }
            if entry["onRight"]:
                secondary.append(descriptor)
            else:
                primary.append(descriptor)

        return primary, secondary

    # Open the current plot in a standalone high resolution window
    def openDetachedWindow(self, plotKey):
        import gui_overlay

        plotItem = self.plotItems.get(plotKey)
        if plotItem is None:
            return None

        primary, secondary = self.buildSeriesDescriptors(plotKey)
        title = self.plotTitles.get(plotKey, plotKey)

        window = gui_overlay.PopupPlotWindow(title, self.window(), self.lan)
        window.drawData(
            primary,
            xlabel=plotItem.getAxis("bottom").labelText,
            ylabel=plotItem.getAxis("left").labelText,
            title=title,
            secondarySeries=secondary or None,
            secondaryYlabel=plotItem.getAxis("right").labelText if secondary else "",
            # A secondary axis must keep its zero on the primary zero here too, not only in the dock
            symmetricYlim=bool(secondary),
        )
        window.applyTheme(self.isDark, self.tokens)
        window.show()

        # Keeping a reference prevents the window from being garbage collected
        self.detachedWindows.append(window)
        return window

    # Refresh the context menu captions after a language change
    def retranslateMenus(self, lan):
        self.lan = lan
        for plotKey, parts in self.plotMenus.items():
            parts["expandAction"].setText(lan.get("plotExpand", "Expand / Detach to large window"))
            parts["modeMenu"].setTitle(lan.get("plotInteraction", "Interaction mode"))
            parts["gridAction"].setText(lan.get("plotToggleGrid", "Toggle grid lines"))
            parts["stationAction"].setText(lan.get("plotToggleStations", "Toggle station markers"))
            parts["highlightMenu"].setTitle(lan.get("plotHighlight", "Highlight series"))
            parts["verticalZoomAction"].setText(lan.get("plotVerticalZoom", "Vertical zoom"))
            parts["verticalZoomAction"].setToolTip(lan.get(
                "plotVerticalZoomTip",
                "Navigation follows the chainage axis, enable this to rescale the vertical axis as well"))
            parts["resetViewAction"].setText(lan.get("plotResetFitY", "Reset view / Fit Y"))

            modeLabels = [lan.get("plotModeBoxZoom", "Rectangular box zoom"),
                          lan.get("plotModePan", "Mouse drag pan"),
                          lan.get("plotModeAxisLock", "Axis lock")]
            for modeAction, modeLabel in zip(parts["modeActions"], modeLabels):
                modeAction.setText(modeLabel)


class PlotNavigationToolbar(QToolBar):
    def __init__(self, plotWidget, lan, parent=None):
        super().__init__(parent)

        self.plotWidget = plotWidget
        self.lan = lan
        self.setIconSize(icons.ribbonIconSize())
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        self.zoomInAction = self.addAction(icons.makeIcon("zoomIn"),
                                           lan.get("plotZoomIn", "Zoom in"))
        self.zoomInAction.triggered.connect(lambda: self.scaleView(0.75))

        self.zoomOutAction = self.addAction(icons.makeIcon("zoomOut"),
                                            lan.get("plotZoomOut", "Zoom out"))
        self.zoomOutAction.triggered.connect(lambda: self.scaleView(1.33))

        self.panAction = self.addAction(icons.makeIcon("pan"), lan.get("plotModePan", "Pan"))
        self.panAction.setCheckable(True)
        self.panAction.setChecked(True)
        self.panAction.triggered.connect(self.togglePanMode)

        self.resetAction = self.addAction(icons.makeIcon("resetView"),
                                          lan.get("plotResetView", "Reset view"))
        self.resetAction.triggered.connect(self.resetView)

        self.addSeparator()

        self.exportAction = self.addAction(icons.makeIcon("exportImage"),
                                           lan.get("plotExportHighRes", "High resolution export"))
        self.exportAction.triggered.connect(self.exportHighRes)

    # Zoom every plot of the attached widget along the chainage axis
    def scaleView(self, factor):
        for plotKey, plotItem in self.plotWidget.plotItems.items():
            # Only a plot the user released for vertical zoom is scaled on both axes
            verticalFactor = factor if plotKey in self.plotWidget.verticalZoomPlots else 1.0
            plotItem.vb.scaleBy((factor, verticalFactor))

    # Switch between drag pan and rectangular box zoom on every plot
    def togglePanMode(self, isChecked):
        mode = MODE_PAN if isChecked else MODE_BOX_ZOOM
        for plotKey in self.plotWidget.plotItems:
            self.plotWidget.setInteractionMode(plotKey, mode)

    # Restore the automatic range of every plot, through the same path as the context menu entry
    def resetView(self):
        for plotKey in self.plotWidget.plotItems:
            self.plotWidget.resetPlotView(plotKey)

    # Save the whole plot canvas as a high resolution raster or vector image
    def exportHighRes(self):
        filePath, _ = QFileDialog.getSaveFileName(
            self, self.lan.get("plotExportHighRes", "High resolution export"),
            "plot.png", "PNG (*.png);;SVG (*.svg);;JPEG (*.jpg)")
        if not filePath:
            return

        if filePath.lower().endswith(".svg"):
            self.plotWidget.exportSceneVector(filePath)
        else:
            self.plotWidget.exportSceneImage(filePath)

    # Refresh the toolbar captions after a language change
    def retranslate(self, lan):
        self.lan = lan
        self.zoomInAction.setText(lan.get("plotZoomIn", "Zoom in"))
        self.zoomOutAction.setText(lan.get("plotZoomOut", "Zoom out"))
        self.panAction.setText(lan.get("plotModePan", "Pan"))
        self.resetAction.setText(lan.get("plotResetView", "Reset view"))
        self.exportAction.setText(lan.get("plotExportHighRes", "High resolution export"))
