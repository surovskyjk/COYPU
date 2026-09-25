# Track geometry, speed and lateral slew profiles with a linked X axis and a shared crosshair
import numpy as np
from PySide6.QtCore import Qt

from plot_widgets import CoypuPlotWidget
import profile_state

# Cant and cant deficiency curves drawn on the left axis of the geometry plot
GEOMETRY_SERIES = [
    ("cant", "stationCant", "cant", "cant"),
    ("cantPossible", "stationCantPossible", "cantPossible", "cant_possible"),
    ("cDef100", "stationCantPossible", "cDef100", "cdef_100"),
    ("cDef130", "stationCantPossible", "cDef130", "cdef_130"),
    ("cDef150", "stationCantPossible", "cDef150", "cdef_150"),
    ("cDefK", "stationCantPossible", "cDefK", "cdef_K"),
    ("cantDef100", "stationCantPossible", "cantDef100", "cant_def_100"),
    ("cantDef130", "stationCantPossible", "cantDef130", "cant_def_130"),
    ("cantDef150", "stationCantPossible", "cantDef150", "cant_def_150"),
    ("cantDefK", "stationCantPossible", "cantDefK", "cant_def_K"),
]

# Curvature curves drawn on the secondary right axis, the muted baseline first then the active one
CURVATURE_SERIES = [
    ("curvatureBaseline", "stationHorizontalBaseline", "curvatureBaseline", "curvature_baseline"),
    ("curvature", "stationHorizontal", "curvature", "curvature"),
]

# Speed limit step curves drawn on the middle plot, always the active alignment only
SPEED_SERIES = [
    ("speedLimits", "stationSpeedLimits", "speedLimits", "speed_lim"),
    ("speedLimits100", "stationSpeed100", "speedLimits100", "speed_lim_100"),
    ("speedLimits130", "stationSpeed130", "speedLimits130", "speed_lim_130"),
    ("speedLimits150", "stationSpeed150", "speedLimits150", "speed_lim_150"),
    ("speedLimitsK", "stationSpeedK", "speedLimitsK", "speed_lim_K"),
]

# Chainage and offset arrays feeding the lateral slew profile plot
SLEW_STATION_KEY = "slewProfileStationKm"
SLEW_OFFSET_KEY = "slewProfileOffsetMm"

# Extra headroom around the slew peak so the d_max threshold lines stay inside the view
SLEW_RANGE_HEADROOM = 1.25

# Grid row the slew plot occupies while it is part of the layout
SLEW_PLOT_ROW = 2

# Smallest half range of the slew axis in millimetres, keeps a near zero profile readable
SLEW_MIN_RANGE_MM = 10.0

# Fixed vertical range of the cant axis, matching the previous alignment plot
CANT_RANGE = 500.0

# Extra headroom above the fastest speed curve so the top line stays readable
SPEED_RANGE_HEADROOM = 1.05

# Opacity every speed ceiling except the active tier is drawn with
INACTIVE_PROFILE_ALPHA = 0.3

# Extra headroom around the curvature peak, replaces the old setYRange padding argument
CURVATURE_RANGE_HEADROOM = 1.05


class PerformanceGraphsWidget(CoypuPlotWidget):
    def __init__(self, lan, parent=None):
        super().__init__(lan, parent)

        self.plotGeometry = self.addPlotRow("geometry", 0, rightAxis="fraction")
        self.plotSpeed = self.addPlotRow("speed", 1)
        self.plotSlew = self.addPlotRow("slew", 2)

        self.addRightAxis("geometry")

        # Linking the lower axes to the top one keeps every plot in step during pan and zoom
        self.plotSpeed.setXLink(self.plotGeometry)
        self.plotSlew.setXLink(self.plotGeometry)

        # Tier the shared profile switcher points at, drawn heavier than the other ceilings
        self.activeProfileKey = profile_state.DEFAULT_PROFILE_KEY

        # Threshold and zero guides of the slew plot, rebuilt whenever new profile data arrives
        self.slewGuides = []
        self.slewThresholdM = None
        self.slewStationKm = np.array([], dtype=float)
        self.slewOffsetMm = np.array([], dtype=float)

        # The slew row stays hidden until an optimization has actually produced a profile
        self.isSlewPlotVisible = False
        self.applySlewPlotVisibility()

        self.plotGeometry.vb.setYRange(-CANT_RANGE, CANT_RANGE, padding=0)

        # Keep the curvature zero line locked onto the cant zero line during zoom and pan
        self.enableZeroLock("geometry")

        # Each row restores its own vertical policy on a reset, instead of auto ranging to the data
        self.setYRangeHandler("geometry", self.restoreGeometryRange)
        self.setYRangeHandler("speed", self.applyFullSpeedRange)
        self.setYRangeHandler("slew", self.applySlewRange)

        self.updateLabels(lan)
        self.enableCursorTracking("geometry")
        self.applyTheme(False)

    # Refresh axis labels and plot captions after a language change
    def updateLabels(self, lan):
        self.lan = lan

        self.plotTitles["geometry"] = lan.get("dockGeometryPlot", "Track geometry")
        self.plotTitles["speed"] = lan.get("dockSpeedPlot", "Speed profile")
        self.plotTitles["slew"] = lan.get("slewPlotTitle", "Lateral slew profile")

        self.plotGeometry.setLabel("left", lan.get("cant", "Cant"))
        self.plotGeometry.setLabel("right", lan.get("curvature", "Curvature"))
        self.plotGeometry.setLabel("bottom", lan.get("station", "Chainage"))
        self.plotSpeed.setLabel("left", self.speedAxisLabel())
        self.plotSpeed.setLabel("bottom", lan.get("station", "Chainage"))
        self.plotSlew.setLabel("left", lan.get("slewAxisLabel", "Lateral slew [mm]"))
        self.plotSlew.setLabel("bottom", lan.get("station", "Chainage"))

        self.retranslateMenus(lan)

    # Speed axis caption in whichever unit system is active
    def speedAxisLabel(self):
        base = self.lan.get("speedLimBase", "Speed limit")
        return f"{base} [{self.speedUnitLabel()}]"

    # Re-label the axes and redraw the speed curves after the unit toggle flipped
    def applyUnitSystem(self, useKmh, dataStorage, visibility=None):
        self.setUnitSystem(useKmh)
        self.plotSpeed.setLabel("left", self.speedAxisLabel())
        self.updateSpeedData(dataStorage, visibility)

    # Replace the geometry curves from the LandXML dictionary
    def updateGeometryData(self, lxml, visibility=None):
        self.clearPlot("geometry")
        if not lxml:
            return

        visibility = visibility or {}

        # Geometry chainage arrays are already stored in kilometres by the parser
        for seriesKey, stationKey, valueKey, labelKey in GEOMETRY_SERIES:
            stations = lxml.get(stationKey)
            values = lxml.get(valueKey)
            if not (self.hasData(stations) and self.hasData(values)):
                continue
            self.setSeriesData("geometry", seriesKey, stations, values,
                               name=self.lan.get(labelKey, labelKey), symbol="o",
                               isVisible=visibility.get(seriesKey, True))

        for seriesKey, stationKey, valueKey, labelKey in CURVATURE_SERIES:
            stations = lxml.get(stationKey)
            values = lxml.get(valueKey)
            if not (self.hasData(stations) and self.hasData(values)):
                continue
            self.setSeriesData("geometry", seriesKey, stations, values,
                               name=self.lan.get(labelKey, labelKey), onRight=True,
                               isVisible=visibility.get(seriesKey, True))

        self.plotGeometry.vb.setYRange(-CANT_RANGE, CANT_RANGE, padding=0)
        self.applySymmetricCurvature()

    # Put the cant axis back on its fixed range and re-centre curvature against it
    def restoreGeometryRange(self):
        self.plotGeometry.vb.setYRange(-CANT_RANGE, CANT_RANGE, padding=0)
        self.applySymmetricCurvature()

    # Centre the curvature axis on zero so it lines up with the cant axis
    def applySymmetricCurvature(self):
        peak = 1e-9
        for entry in self.plotSeries.get("geometry", {}).values():
            if not entry["onRight"] or entry["y"].size == 0:
                continue
            finiteValues = entry["y"][np.isfinite(entry["y"])]
            if finiteValues.size:
                peak = max(peak, float(np.max(np.abs(finiteValues))))

        peak *= CURVATURE_RANGE_HEADROOM
        rightView = self.plotRightViews.get("geometry")
        if rightView is not None:
            rightView.setYRange(-peak, peak, padding=0)
            # The new peak defines the proportion the two axes keep from here on
            self.captureZeroLockRatio("geometry")
            self.syncZeroAlignment("geometry")

    # Replace the speed curves from the main data storage dictionary
    def updateSpeedData(self, dataStorage, visibility=None):
        self.clearPlot("speed")
        if not dataStorage:
            return

        visibility = visibility or {}

        # Speed profile chainage arrays are already stored in kilometres, the limits in km/h
        limitFactor = 1.0 if self.useKmh else 1.0 / 3.6
        activeSeriesKey = profile_state.storageKeysFor(self.activeProfileKey)[1]
        for seriesKey, stationKey, valueKey, labelKey in SPEED_SERIES:
            stations = dataStorage.get(stationKey)
            speeds = dataStorage.get(valueKey)
            if not (self.hasData(stations) and self.hasData(speeds)):
                continue
            isActiveProfile = seriesKey == activeSeriesKey
            self.setSeriesData("speed", seriesKey, stations,
                               np.asarray(speeds, dtype=float) * limitFactor,
                               name=self.lan.get(labelKey, labelKey), step=True, symbol="s",
                               width=2 if isActiveProfile else None,
                               alpha=None if isActiveProfile else INACTIVE_PROFILE_ALPHA,
                               isVisible=visibility.get(seriesKey, True))

        # Overlay the simulated running speed of every calculated vehicle
        vehicleCount = dataStorage.get("num_vehicles", 1)
        for vehicleIndex in range(vehicleCount):
            simulatedStations = dataStorage.get(f"kinematicsStationM_{vehicleIndex}")
            simulatedSpeeds = dataStorage.get(f"kinematicsSpeedM_{vehicleIndex}")
            if not (self.hasData(simulatedStations) and self.hasData(simulatedSpeeds)):
                continue

            # Kinematics arrays are stored in metres and metres per second
            self.setSeriesData(
                "speed", f"simulated{vehicleIndex}",
                np.asarray(simulatedStations, dtype=float) / 1000.0,
                np.asarray(simulatedSpeeds, dtype=float) * self.displaySpeedFactor(),
                styleKey="simulated",
                name=f"{self.lan.get('speedBase', 'Speed')} V{vehicleIndex + 1}")

        self.applyFullSpeedRange()

    # Show the speed axis from standstill up to the fastest curve on the plot
    def applyFullSpeedRange(self):
        peak = 0.0
        for entry in self.plotSeries.get("speed", {}).values():
            if entry["y"].size == 0:
                continue
            finiteValues = entry["y"][np.isfinite(entry["y"])]
            if finiteValues.size:
                peak = max(peak, float(np.max(finiteValues)))

        if peak <= 0.0:
            # A one shot fit, leaving auto range armed would undo the fixed policy on the next redraw
            self.plotSpeed.vb.enableAutoRange(axis="y")
            self.plotSpeed.vb.disableAutoRange(axis="y")
            return

        self.plotSpeed.vb.setYRange(0.0, peak * SPEED_RANGE_HEADROOM, padding=0)

    # Replace the lateral slew profile from the LandXML dictionary
    def updateSlewData(self, lxml, dMaxM=None):
        self.clearSlewGuides()
        self.clearPlot("slew")
        self.slewStationKm = np.array([], dtype=float)
        self.slewOffsetMm = np.array([], dtype=float)
        if not lxml:
            return

        stations = lxml.get(SLEW_STATION_KEY)
        offsets = lxml.get(SLEW_OFFSET_KEY)
        if not (self.hasData(stations) and self.hasData(offsets)):
            return

        self.slewStationKm = np.asarray(stations, dtype=float)
        self.slewOffsetMm = np.asarray(offsets, dtype=float)
        self.slewThresholdM = dMaxM

        # Splitting on sign keeps the inward and outward halves individually coloured
        inwardValues = self.slewSideValues(isInward=True)
        outwardValues = self.slewSideValues(isInward=False)

        self.setSeriesData("slew", "slewPositive", self.slewStationKm, inwardValues,
                           name=self.lan.get("slewInward", "Inward slew"))
        self.setSeriesData("slew", "slewNegative", self.slewStationKm, outwardValues,
                           name=self.lan.get("slewOutward", "Outward slew"))

        self.buildSlewGuides(dMaxM)
        self.applySlewRange(dMaxM)

    # Offsets of one side of the slew profile. Each side is masked to its own sign, so a
    # profile crossing zero between two samples used to leave a gap in both halves. Extending
    # each side by a single sample across the crossing closes the line without moving a value.
    def slewSideValues(self, isInward):
        onSide = self.slewOffsetMm >= 0.0 if isInward else self.slewOffsetMm <= 0.0
        keep = onSide.copy()
        if keep.size > 1:
            keep[:-1] |= onSide[1:]
            keep[1:] |= onSide[:-1]
        return np.where(keep, self.slewOffsetMm, np.nan)

    # Zero line plus the two configured d_max envelope lines
    def buildSlewGuides(self, dMaxM):
        foreground = self.tokens["plotForeground"] if self.tokens else "#666666"
        self.slewGuides.append(self.buildMarker(self.plotSlew, 0.0, 0, "#8a8a8a", "", foreground,
                                                penStyle=Qt.PenStyle.SolidLine))
        if not dMaxM:
            return

        thresholdMm = float(dMaxM) * 1000.0
        label = self.lan.get("slewThresholdLabel", "d_max")
        for position in (thresholdMm, -thresholdMm):
            self.slewGuides.append(
                self.buildMarker(self.plotSlew, position, 0, "#d64545", label, foreground))

    # Drop the guide lines so a redraw never stacks them
    def clearSlewGuides(self):
        for guide in self.slewGuides:
            self.plotSlew.removeItem(guide)
            self.forgetMarker(guide)
        self.slewGuides = []

    # Symmetric range around zero so the sign of the slew stays readable at a glance
    def applySlewRange(self, dMaxM=None):
        # A view reset calls this with no argument, the stored envelope keeps the guides in frame
        dMaxM = self.slewThresholdM if dMaxM is None else dMaxM
        peak = SLEW_MIN_RANGE_MM
        if self.slewOffsetMm.size:
            finiteValues = self.slewOffsetMm[np.isfinite(self.slewOffsetMm)]
            if finiteValues.size:
                peak = max(peak, float(np.max(np.abs(finiteValues))))
        if dMaxM:
            peak = max(peak, float(dMaxM) * 1000.0)

        peak *= SLEW_RANGE_HEADROOM
        self.plotSlew.vb.setYRange(-peak, peak, padding=0)

    # Show or hide the slew row without disturbing the two plots above it
    def setSlewPlotVisible(self, isVisible):
        self.isSlewPlotVisible = bool(isVisible)
        self.applySlewPlotVisibility()

    # Hiding a plot item would leave an empty grid row, so the row is added and removed instead
    def applySlewPlotVisibility(self):
        isInLayout = self.plotSlew in self.ci.items
        if self.isSlewPlotVisible and not isInLayout:
            self.ci.addItem(self.plotSlew, row=SLEW_PLOT_ROW, col=0)
            self.plotSlew.setXLink(self.plotGeometry)
        elif not self.isSlewPlotVisible and isInLayout:
            self.ci.removeItem(self.plotSlew)

    # Drop the slew curve entirely, used when an optimization is reverted
    def clearSlewPlot(self):
        self.clearSlewGuides()
        self.clearPlot("slew")
        self.slewStationKm = np.array([], dtype=float)
        self.slewOffsetMm = np.array([], dtype=float)

    # Remember which permissible speed curve the shared profile switcher points at
    def setActiveProfileKey(self, profileKey):
        self.activeProfileKey = profileKey

    # The shared readout names the active tier's ceiling, the simulated speed and the slew
    def updateReadout(self, value):
        super().updateReadout(value)
        if self.readoutLabel is None:
            return

        readoutParts = [self.formatChainage(value)]

        activeSeriesKey = profile_state.storageKeysFor(self.activeProfileKey)[1]
        limitValue = self.seriesValueAt("speed", activeSeriesKey, value)
        if not np.isnan(limitValue):
            readoutParts.append(f"{self.lan.get('readoutProfileShort', 'Vlim')} {limitValue:.0f}")

        simulatedValue = self.seriesValueAt("speed", "simulated0", value)
        if not np.isnan(simulatedValue):
            readoutParts.append(f"{self.lan.get('readoutSpeedShort', 'V')} {simulatedValue:.0f}")

        if self.slewStationKm.size >= 2:
            slewMm = float(np.interp(value, self.slewStationKm, self.slewOffsetMm,
                                     left=np.nan, right=np.nan))
            if not np.isnan(slewMm):
                readoutParts.append(
                    f"{self.lan.get('slewShort', 'dy')} {slewMm:+.1f} mm")

        self.readoutLabel.setText(" | ".join(readoutParts))

    # Guard used before touching any optional array
    def hasData(self, values):
        return values is not None and len(values) > 0

    # Remove every curve, used by the clean actions
    def clearAll(self):
        self.clearPlot("geometry")
        self.clearPlot("speed")
        self.clearSlewPlot()
