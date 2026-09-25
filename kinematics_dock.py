# Kinematics results shown as four stacked plots with pairwise linked X axes
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt

import batch_metrics
import plot_widgets
from plot_widgets import CoypuPlotWidget


class KinematicsPlotWidget(CoypuPlotWidget):
    def __init__(self, lan, parent=None):
        super().__init__(lan, parent)

        self.stopMarkers = []
        self.useKmh = False

        self.plotTachoTrack = self.addPlotRow("tachoTrack", 0, withCrosshair=False)
        self.plotTachoTime = self.addPlotRow("tachoTime", 1, withCrosshair=False)
        self.plotDistTime = self.addPlotRow("distTime", 2, withCrosshair=False,
                                            legendCorner="bottomLeft")
        self.plotForces = self.addPlotRow("forces", 3, withCrosshair=False)

        # Plots sharing the same X quantity are linked, distance and time stay apart
        self.plotForces.setXLink(self.plotTachoTrack)
        self.plotDistTime.setXLink(self.plotTachoTime)

        self.updateLabels(lan)
        self.applyTheme(False)

    # Refresh axis labels and plot captions after a language or unit change
    def updateLabels(self, lan):
        self.lan = lan

        speedLabel = self.speedLabel()
        speedLimitLabel = self.speedLimitLabel()
        distanceLabel = self.distanceLabel()
        timeLabel = self.timeLabel()

        self.plotTitles["tachoTrack"] = lan.get("kinematicsSpeedLimitTrack", "Speed - Distance")
        self.plotTitles["tachoTime"] = lan.get("kinematicsSpeedLimitTime", "Speed - Time")
        self.plotTitles["distTime"] = lan.get("kinematicsDistanceTime", "Distance - Time")
        self.plotTitles["forces"] = lan.get("kinematicsForces", "Forces")

        self.plotTachoTrack.setLabel("bottom", distanceLabel)
        self.plotTachoTrack.setLabel("left", speedLimitLabel)
        self.plotTachoTime.setLabel("bottom", timeLabel)
        self.plotTachoTime.setLabel("left", speedLimitLabel)
        self.plotDistTime.setLabel("bottom", timeLabel)
        self.plotDistTime.setLabel("left", distanceLabel)
        self.plotForces.setLabel("bottom", distanceLabel)
        self.plotForces.setLabel("left", lan.get("forceKN", "Force [kN]"))

        self.retranslateMenus(lan)

    # Axis caption for the simulated running speed
    def speedLabel(self):
        if self.useKmh:
            return self.lan.get("speedKmh", "Speed [km/h]")
        return self.lan.get("speedM", "Speed [m/s]")

    # Axis caption for the permissible speed
    def speedLimitLabel(self):
        if self.useKmh:
            return self.lan.get("speedLimKmh", "Speed Limit [km/h]")
        return self.lan.get("speedLimM", "Speed Limit [m/s]")

    # Axis caption for the travelled distance
    def distanceLabel(self):
        if self.useKmh:
            return self.lan.get("distanceKm", "Distance [km]")
        return self.lan.get("distance", "Distance [m]")

    # Axis caption for the elapsed time
    def timeLabel(self):
        if self.useKmh:
            return self.lan.get("timeMin", "Time [min]")
        return self.lan.get("time", "Time [s]")

    # Rebuild every kinematics curve from the main data storage dictionary
    def updateKinematicsData(self, dataStorage, useKmh, vehicleNameResolver=None, visibility=None):
        self.useKmh = bool(useKmh)
        self.clearAll()
        self.updateLabels(self.lan)

        if not dataStorage:
            return

        visibility = visibility or {}
        speedFactor = 3.6 if self.useKmh else 1.0
        distanceFactor = 1000.0 if self.useKmh else 1.0
        timeFactor = 60.0 if self.useKmh else 1.0

        vehicleCount = dataStorage.get("num_vehicles", 1)
        vehiclesSettings = dataStorage.get("settingsData", {}).get("vehicles", [])

        for vehicleIndex in range(vehicleCount):
            self.drawVehicle(dataStorage, vehicleIndex, vehicleCount, vehiclesSettings,
                             speedFactor, distanceFactor, timeFactor,
                             vehicleNameResolver, visibility)

        self.drawStopMarkers(dataStorage, vehicleCount, vehiclesSettings,
                             distanceFactor, timeFactor)

    # Draw every curve belonging to a single simulated vehicle
    def drawVehicle(self, dataStorage, vehicleIndex, vehicleCount, vehiclesSettings,
                    speedFactor, distanceFactor, timeFactor, vehicleNameResolver, visibility):
        colorIndex = vehicleIndex % len(plot_widgets.VEHICLE_SPEED_COLORS)
        limitColor = plot_widgets.VEHICLE_LIMIT_COLORS[colorIndex]
        speedColor = plot_widgets.VEHICLE_SPEED_COLORS[colorIndex]

        suffix = self.vehicleSuffix(vehicleIndex, vehicleCount, vehicleNameResolver)
        speedLimitLabel = self.speedLimitLabel() + suffix
        speedLabel = self.speedLabel() + suffix
        distanceLabel = self.distanceLabel() + suffix

        trackVisible = visibility.get("kinematicsSpeedLimitTrack", True)
        timeVisible = visibility.get("kinematicsSpeedLimitTime", True)
        distanceVisible = visibility.get("kinematicsDistanceTime", True)
        forcesVisible = visibility.get("kinematicsForces", True)

        stationSpeedLimits = dataStorage.get(f"stationSpeedLimitM_{vehicleIndex}")
        speedLimits = dataStorage.get(f"speedLimitsM_{vehicleIndex}")
        speedLimitsTime = dataStorage.get(f"speedLimitsT_{vehicleIndex}")

        if self.hasData(stationSpeedLimits) and self.hasData(speedLimits):
            # Reversed vehicles store descending chainages, sort them for the step curve only
            isReversed = self.isReversed(vehiclesSettings, vehicleIndex)
            if isReversed and len(stationSpeedLimits) > 1:
                sortIndex = np.argsort(stationSpeedLimits)
                plotStations = np.asarray(stationSpeedLimits)[sortIndex]
                plotSpeeds = np.asarray(speedLimits)[sortIndex]
            else:
                plotStations, plotSpeeds = stationSpeedLimits, speedLimits

            self.setSeriesData("tachoTrack", f"tachoTrack{vehicleIndex}",
                               np.asarray(plotStations, dtype=float) / distanceFactor,
                               np.asarray(plotSpeeds, dtype=float) * speedFactor,
                               name=speedLimitLabel, color=limitColor, dash=True,
                               step=True, symbol="s", alpha=0.7, isVisible=trackVisible)

        if self.hasData(speedLimitsTime) and self.hasData(speedLimits):
            self.setSeriesData("tachoTime", f"tachoTime{vehicleIndex}",
                               np.asarray(speedLimitsTime, dtype=float) / timeFactor,
                               np.asarray(speedLimits, dtype=float) * speedFactor,
                               name=speedLimitLabel, color=limitColor, dash=True,
                               step=True, symbol="s", alpha=0.7, isVisible=timeVisible)

        if self.hasData(speedLimitsTime) and self.hasData(stationSpeedLimits):
            self.setSeriesData("distTime", f"distTime{vehicleIndex}",
                               np.asarray(speedLimitsTime, dtype=float) / timeFactor,
                               np.asarray(stationSpeedLimits, dtype=float) / distanceFactor,
                               name=speedLimitLabel, color=limitColor, dash=True,
                               symbol="s", alpha=0.7, isVisible=distanceVisible)

        kinematicsStation = dataStorage.get(f"kinematicsStationM_{vehicleIndex}")
        kinematicsSpeed = dataStorage.get(f"kinematicsSpeedM_{vehicleIndex}")
        kinematicsTime = dataStorage.get(f"kinematicsTimeS_{vehicleIndex}")
        kinematicsDwells = dataStorage.get(f"kinematicsDwellTimesS_{vehicleIndex}")

        if not self.hasData(kinematicsStation):
            return

        plotTimes, plotSpeeds, plotStations = self.expandStops(
            kinematicsTime, kinematicsSpeed, kinematicsStation, kinematicsDwells)

        if self.hasData(kinematicsSpeed):
            self.setSeriesData("tachoTrack", f"simTrack{vehicleIndex}",
                               np.asarray(kinematicsStation, dtype=float) / distanceFactor,
                               np.asarray(kinematicsSpeed, dtype=float) * speedFactor,
                               name=speedLabel, color=speedColor, isVisible=trackVisible)

        if plotTimes.size and plotSpeeds.size:
            self.setSeriesData("tachoTime", f"simTime{vehicleIndex}",
                               plotTimes / timeFactor, plotSpeeds * speedFactor,
                               name=speedLabel, color=speedColor, isVisible=timeVisible)

        if plotTimes.size and plotStations.size:
            self.setSeriesData("distTime", f"simDistTime{vehicleIndex}",
                               plotTimes / timeFactor, plotStations / distanceFactor,
                               name=distanceLabel, color=speedColor, isVisible=distanceVisible)

        forceDefinitions = [
            ("forceTraction", f"kinematicsForceTractionKN_{vehicleIndex}",
             plot_widgets.VEHICLE_TRACTION_COLORS[colorIndex], "forceTraction"),
            ("forceBraking", f"kinematicsForceBrakingKN_{vehicleIndex}",
             plot_widgets.VEHICLE_BRAKING_COLORS[colorIndex], "forceBraking"),
            ("forceResistance", f"kinematicsForceResistanceKN_{vehicleIndex}",
             plot_widgets.VEHICLE_RESISTANCE_COLORS[colorIndex], "forceResistance"),
        ]
        for seriesPrefix, storageKey, forceColor, labelKey in forceDefinitions:
            forceValues = dataStorage.get(storageKey)
            if not self.hasData(forceValues):
                continue
            self.setSeriesData("forces", f"{seriesPrefix}{vehicleIndex}",
                               np.asarray(kinematicsStation, dtype=float) / distanceFactor,
                               np.asarray(forceValues, dtype=float),
                               name=self.lan.get(labelKey, labelKey) + suffix,
                               color=forceColor, isVisible=forcesVisible)

    # Insert an arrival point with zero speed in front of every dwell stop
    def expandStops(self, kinematicsTime, kinematicsSpeed, kinematicsStation, kinematicsDwells):
        timeList = list(kinematicsTime if kinematicsTime is not None else [])
        speedList = list(kinematicsSpeed if kinematicsSpeed is not None else [])
        stationList = list(kinematicsStation if kinematicsStation is not None else [])

        if kinematicsDwells is not None:
            stopIndices = np.where(np.asarray(kinematicsDwells) > 0)[0]
            offset = 0
            for stopIndex in stopIndices:
                actualIndex = stopIndex + offset
                if actualIndex >= len(timeList):
                    continue
                arrivalTime = timeList[actualIndex] - kinematicsDwells[stopIndex]
                timeList.insert(actualIndex, arrivalTime)
                speedList.insert(actualIndex, 0.0)
                stationList.insert(actualIndex, stationList[actualIndex])
                offset += 1

        return (np.asarray(timeList, dtype=float), np.asarray(speedList, dtype=float),
                np.asarray(stationList, dtype=float))

    # Draw the scheduled stop indicators on the three plots that can show them
    def drawStopMarkers(self, dataStorage, vehicleCount, vehiclesSettings,
                        distanceFactor, timeFactor):
        # After an optimization the engine runs against projected chainages, so the markers
        # read the same list the travel times do rather than the raw timetable entries
        trainStops = batch_metrics.stopsList(dataStorage)
        if not trainStops or not self.showStationMarkers:
            return

        foreground = self.tokens["plotForeground"] if self.tokens else "#1c1c1c"

        for stationKm, dwellSeconds, stopName in trainStops:
            stationMetres = stationKm * 1000.0

            self.addStopMarker(self.plotTachoTrack, stationMetres / distanceFactor,
                               angle=90, color="#8a8a8a", label=stopName,
                               labelColor=foreground)
            self.addStopMarker(self.plotDistTime, stationMetres / distanceFactor,
                               angle=0, color="#8a8a8a", label=stopName,
                               labelColor=foreground)

            for vehicleIndex in range(vehicleCount):
                stopTime = self.interpolateStopTime(dataStorage, vehiclesSettings,
                                                    vehicleIndex, stationMetres)
                if stopTime is None:
                    continue
                colorIndex = vehicleIndex % len(plot_widgets.VEHICLE_LIMIT_COLORS)
                markerLabel = f"{stopName} (V{vehicleIndex + 1})" if stopName else ""
                self.addStopMarker(self.plotTachoTime, stopTime / timeFactor, angle=90,
                                   color=plot_widgets.VEHICLE_LIMIT_COLORS[colorIndex],
                                   label=markerLabel,
                                   labelColor=plot_widgets.VEHICLE_LIMIT_COLORS[colorIndex],
                                   dotted=True)

        self.updateMarkerAnchors()

    # Add a single labelled marker line and remember it for the next redraw
    def addStopMarker(self, plotItem, position, angle, color, label, labelColor,
                      dotted=False):
        penStyle = Qt.PenStyle.DotLine if dotted else Qt.PenStyle.DashLine
        markerLine = self.buildMarker(plotItem, position, angle, color, label,
                                      labelColor, penStyle)
        self.stopMarkers.append((plotItem, markerLine))

    # Time at which one vehicle reaches a given chainage, honouring reversed runs
    def interpolateStopTime(self, dataStorage, vehiclesSettings, vehicleIndex, stationMetres):
        kinematicsStation = dataStorage.get(f"kinematicsStationM_{vehicleIndex}")
        kinematicsTime = dataStorage.get(f"kinematicsTimeS_{vehicleIndex}")
        if not (self.hasData(kinematicsStation) and self.hasData(kinematicsTime)):
            return None

        stations = np.asarray(kinematicsStation, dtype=float)
        times = np.asarray(kinematicsTime, dtype=float)
        if self.isReversed(vehiclesSettings, vehicleIndex):
            stations = stations[::-1]
            times = times[::-1]

        return float(np.interp(stationMetres, stations, times))

    # Read the reversed run flag of one vehicle from the settings list
    def isReversed(self, vehiclesSettings, vehicleIndex):
        if vehicleIndex >= len(vehiclesSettings):
            return False
        return bool(vehiclesSettings[vehicleIndex].get("runReversed", False))

    # Build the per vehicle label suffix used on every legend entry
    def vehicleSuffix(self, vehicleIndex, vehicleCount, vehicleNameResolver):
        if vehicleCount <= 1:
            return ""
        vehicleName = vehicleNameResolver(vehicleIndex) if vehicleNameResolver else ""
        return f" {vehicleName}" if vehicleName else f" V{vehicleIndex + 1}"

    # Toggle every curve of one plot at once from the ribbon series actions
    def setPlotVisible(self, plotKey, isVisible):
        for seriesKey in self.plotSeries.get(plotKey, {}):
            self.setSeriesVisible(plotKey, seriesKey, isVisible)

    # Guard used before touching any optional array
    def hasData(self, values):
        return values is not None and len(values) > 0

    # Remove every curve and marker, used by the clean actions
    def clearAll(self):
        for plotItem, markerLine in self.stopMarkers:
            plotItem.removeItem(markerLine)
            self.forgetMarker(markerLine)
        self.stopMarkers = []

        for plotKey in ("tachoTrack", "tachoTime", "distTime", "forces"):
            self.clearPlot(plotKey)
