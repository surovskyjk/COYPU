# Track Statistics panel summarising length, design/actual speed maxima and travel times
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
import numpy as np

from profile_state import DEFAULT_PROFILE_KEY, ProfileSelectorBar
from ui_kit import CollapsibleSection, DARK_CARD_TOKENS, LIGHT_CARD_TOKENS, MetricCard
from vehicle_catalog import MAX_VEHICLES
import batch_metrics

# Row height used to size the segment tables without letting them grow unbounded
TABLE_ROW_HEIGHT_PX = 22

# Most rows a segment table shows before it starts scrolling internally
TABLE_MAX_VISIBLE_ROWS = 6


class TrackStatisticsWidget(QWidget):
    def __init__(self, lan, parent=None):
        super().__init__(parent)

        self.lan = lan or {}
        self.lastDataStorage = {}
        self.vehicleNameResolver = None
        self.useKmh = False
        self.activeProfileKey = DEFAULT_PROFILE_KEY

        scrollArea = QScrollArea(self)
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameShape(QScrollArea.Shape.NoFrame)

        rootLayout = QVBoxLayout(self)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        rootLayout.addWidget(scrollArea)

        contentWidget = QWidget()
        scrollArea.setWidget(contentWidget)

        outerLayout = QVBoxLayout(contentWidget)
        outerLayout.setContentsMargins(4, 4, 4, 4)
        outerLayout.setSpacing(4)

        # Compact selector row, the profile half is the shared switcher mirrored from the ribbon
        selectorLayout = QHBoxLayout()
        selectorLayout.setSpacing(4)
        self.profileSelector = ProfileSelectorBar(self.lan)
        selectorLayout.addWidget(self.profileSelector, 1)

        self.vehicleRowLabel = QLabel()
        self.vehicleCombo = QComboBox()
        self.vehicleCombo.currentIndexChanged.connect(self.onVehicleChanged)
        selectorLayout.addWidget(self.vehicleRowLabel)
        selectorLayout.addWidget(self.vehicleCombo, 1)
        outerLayout.addLayout(selectorLayout)

        # KPI cards, a compact grid replaces the four free growing group boxes
        cardsLayout = QGridLayout()
        cardsLayout.setSpacing(4)
        self.lengthCard = MetricCard()
        self.designMaxCard = MetricCard()
        self.actualMaxCard = MetricCard()
        self.totalTimeCard = MetricCard()
        self.originDestCard = MetricCard()
        cardsLayout.addWidget(self.lengthCard, 0, 0)
        cardsLayout.addWidget(self.designMaxCard, 0, 1)
        cardsLayout.addWidget(self.actualMaxCard, 1, 0)
        cardsLayout.addWidget(self.totalTimeCard, 1, 1)
        cardsLayout.addWidget(self.originDestCard, 2, 0, 1, 2)
        outerLayout.addLayout(cardsLayout)

        # Detail tables live in collapsible sections, built eagerly so refreshes always find them
        self.designSegmentTable = self.buildSegmentTable(3)
        self.designSection = CollapsibleSection()
        self.designSection.setContentWidget(self.designSegmentTable)
        outerLayout.addWidget(self.designSection)

        self.actualSegmentTable = self.buildSegmentTable(3)
        self.actualSection = CollapsibleSection()
        self.actualSection.setContentWidget(self.actualSegmentTable)
        outerLayout.addWidget(self.actualSection)

        self.interstationTable = self.buildSegmentTable(2)
        self.interstationSection = CollapsibleSection(startExpanded=True)
        self.interstationSection.setContentWidget(self.interstationTable)
        outerLayout.addWidget(self.interstationSection)

        outerLayout.addStretch(1)

        self.rebuildVehicleCombo()
        self.updateTexts(self.lan)

    # Build one compact, read only segment table with the given column count
    def buildSegmentTable(self, columnCount):
        table = QTableWidget(0, columnCount)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(20)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT_PX)
        return table

    # Cap a table's height to a handful of rows so it stops stealing vertical space
    def constrainTableHeight(self, table):
        visibleRows = min(max(table.rowCount(), 1), TABLE_MAX_VISIBLE_ROWS)
        table.setMaximumHeight(table.horizontalHeader().height() + visibleRows * TABLE_ROW_HEIGHT_PX + 4)

    # Guard used before touching any optional array
    def hasData(self, values):
        return batch_metrics.hasData(values)

    # Fallback text shown wherever a statistic cannot be computed yet
    def noDataText(self):
        return self.lan.get("statsNoData", "No data")

    # Render a duration in seconds as MM:SS, or the no-data placeholder
    def formatDuration(self, seconds):
        return batch_metrics.formatDuration(seconds, self.noDataText())

    # Scheduled stops in the order they were imported, never sorted by chainage
    def stopsList(self, dataStorage):
        return batch_metrics.stopsList(dataStorage)

    # Track length in kilometres derived from the parsed alignment chainage
    def computeTrackLength(self, dataStorage):
        return batch_metrics.computeTrackLengthKm(dataStorage)

    # Design speed limit and matching chainage arrays for the requested GPK profile
    def resolveDesignSpeedArrays(self, dataStorage, profile):
        if profile == "TTP":
            speeds = dataStorage.get("speedLimits")
            stations = dataStorage.get("stationSpeedLimits")
        else:
            speeds = dataStorage.get(f"speedLimits{profile}")
            stations = dataStorage.get(f"stationSpeed{profile}")

        if not self.hasData(speeds) or not self.hasData(stations):
            return None, None

        speeds = np.asarray(speeds, dtype=float)
        stations = np.asarray(stations, dtype=float)
        valid = np.isfinite(speeds) & np.isfinite(stations) & (speeds > 0)
        speeds, stations = speeds[valid], stations[valid]
        if len(speeds) == 0:
            return None, None
        return speeds, stations

    # Simulated actual speed and chainage arrays for one vehicle, in the currently active unit system
    def resolveActualSpeedArrays(self, dataStorage, vehicleIndex):
        speedsMs = dataStorage.get(f"kinematicsSpeedM_{vehicleIndex}")
        stationsM = dataStorage.get(f"kinematicsStationM_{vehicleIndex}")
        if not self.hasData(speedsMs) or not self.hasData(stationsM):
            return None, None
        speedFactor = 3.6 if self.useKmh else 1.0
        stationFactor = 0.001 if self.useKmh else 1.0
        speeds = np.asarray(speedsMs, dtype=float) * speedFactor
        stations = np.asarray(stationsM, dtype=float) * stationFactor
        return speeds, stations

    # Unit suffix and value formatter for the achieved-speed section, following the active toggle
    def actualSpeedUnitLabel(self):
        return self.lan.get("unitKmh", "km/h") if self.useKmh else self.lan.get("unitMs", "m/s")

    def actualDistanceUnitLabel(self):
        return self.lan.get("unitKm", "km") if self.useKmh else self.lan.get("unitM", "m")

    # Design values are held in km/h and km, these turn them into whatever the toggle selected
    def designSpeedForDisplay(self, speedKmh):
        return float(speedKmh) if self.useKmh else float(speedKmh) / 3.6

    def designDistanceForDisplay(self, stationKm):
        return float(stationKm) if self.useKmh else float(stationKm) * 1000.0

    def formatDesignSpeed(self, speedKmh):
        return f"{self.designSpeedForDisplay(speedKmh):.0f}" if self.useKmh \
            else f"{self.designSpeedForDisplay(speedKmh):.1f}"

    def formatDesignDistance(self, stationKm):
        return f"{self.designDistanceForDisplay(stationKm):.3f}" if self.useKmh \
            else f"{self.designDistanceForDisplay(stationKm):.1f}"

    # Header labels for the design table, tracking whichever unit system is active
    def designSegmentHeaders(self):
        return [
            self.lan.get("statsSegmentColumn", "Segment"),
            f"{self.lan.get('statsMaxSpeedColumnBase', 'Max speed')} [{self.actualSpeedUnitLabel()}]",
            f"{self.lan.get('statsChainageColumnBase', 'Chainage')} [{self.actualDistanceUnitLabel()}]",
        ]

    def formatActualSpeed(self, value):
        return f"{value:.0f}" if self.useKmh else f"{value:.1f}"

    def formatActualDistance(self, value):
        return f"{value:.3f}" if self.useKmh else f"{value:.0f}"

    # Highest value in a speed array and the chainage at which it occurs
    def globalMax(self, speeds, stations):
        if not self.hasData(speeds):
            return None
        index = int(np.argmax(speeds))
        return float(speeds[index]), float(stations[index])

    # Fill a Segment / Max speed / Chainage table from consecutive stop boundaries, in the units the
    # caller already scaled speeds/stations/boundaries to (formatSpeed/formatDistance default to km/h, km)
    def fillSegmentTable(self, table, speeds, stations, boundaries, formatSpeed=None, formatDistance=None):
        formatSpeed = formatSpeed or (lambda value: f"{value:.0f}")
        formatDistance = formatDistance or (lambda value: f"{value:.3f}")

        table.setRowCount(0)
        if not self.hasData(speeds) or len(boundaries) < 2:
            return

        for segmentIndex in range(len(boundaries) - 1):
            startValue, startName = boundaries[segmentIndex]
            endValue, endName = boundaries[segmentIndex + 1]
            loValue, hiValue = sorted((startValue, endValue))
            mask = (stations >= loValue) & (stations <= hiValue)

            row = table.rowCount()
            table.insertRow(row)
            label = f"{startName or formatDistance(startValue)} → {endName or formatDistance(endValue)}"
            table.setItem(row, 0, QTableWidgetItem(label))
            if np.any(mask):
                bestIndex = int(np.argmax(speeds[mask]))
                table.setItem(row, 1, QTableWidgetItem(formatSpeed(speeds[mask][bestIndex])))
                table.setItem(row, 2, QTableWidgetItem(formatDistance(stations[mask][bestIndex])))
            else:
                table.setItem(row, 1, QTableWidgetItem("-"))
                table.setItem(row, 2, QTableWidgetItem("-"))

        self.constrainTableHeight(table)

    # Cumulative time at the chainage nearest to a stop, mirrors generateVehicleReport's lookup
    def lookupTimeAtStation(self, stationsM, timesS, stationKm):
        return batch_metrics.lookupTimeAtStation(stationsM, timesS, stationKm)

    # Arrival (before dwelling) and departure (after dwelling) time at one stop
    def stopTiming(self, stationsM, timesS, stationKm, dwellSeconds):
        return batch_metrics.stopTiming(stationsM, timesS, stationKm, dwellSeconds)

    # Total, origin-to-destination and inter-station travel times for one vehicle
    def computeTravelTimeSections(self, dataStorage, vehicleIndex):
        return batch_metrics.computeTravelTimeSections(dataStorage, vehicleIndex)

    # Rebuild the vehicle selector from the currently simulated vehicle count
    def rebuildVehicleCombo(self):
        dataStorage = self.lastDataStorage or {}
        vehicleCount = int(dataStorage.get("num_vehicles", 1) or 1)
        vehicleCount = max(1, min(vehicleCount, MAX_VEHICLES))

        previousData = self.vehicleCombo.currentData()
        self.vehicleCombo.blockSignals(True)
        self.vehicleCombo.clear()
        for vehicleIndex in range(vehicleCount):
            caption = f'{self.lan.get("vehicle", "Vehicle")} {vehicleIndex + 1}'
            vehicleName = self.vehicleNameResolver(vehicleIndex) if self.vehicleNameResolver else ""
            if vehicleName:
                caption = f"{caption} — {vehicleName}"
            self.vehicleCombo.addItem(caption, vehicleIndex)
        restoredIndex = self.vehicleCombo.findData(previousData) if previousData is not None else -1
        self.vehicleCombo.setCurrentIndex(restoredIndex if restoredIndex >= 0 else 0)
        self.vehicleCombo.blockSignals(False)

    # Re-render every section from the currently cached data storage and active profile
    def updateStatisticsView(self):
        self.refreshTrackLength()
        self.refreshDesignSpeedSection()
        self.refreshActualSpeedSection()
        self.refreshTravelTimeSection()

    # Previous spelling of updateStatisticsView, kept so older call sites keep working
    def refreshAll(self):
        self.updateStatisticsView()

    def refreshTrackLength(self):
        length = self.computeTrackLength(self.lastDataStorage or {})
        if length is None:
            self.lengthCard.setValue(self.noDataText())
            return
        self.lengthCard.setValue(
            f"{self.formatDesignDistance(length)} {self.actualDistanceUnitLabel()}")

    def refreshDesignSpeedSection(self):
        self.designSegmentTable.setHorizontalHeaderLabels(self.designSegmentHeaders())

        dataStorage = self.lastDataStorage or {}
        speeds, stations = self.resolveDesignSpeedArrays(dataStorage, self.activeProfileKey)

        peak = self.globalMax(speeds, stations)
        if peak is None:
            self.designMaxCard.setValue(self.noDataText())
        else:
            maxSpeed, location = peak
            self.designMaxCard.setValue(
                f"{self.formatDesignSpeed(maxSpeed)} {self.actualSpeedUnitLabel()}",
                f"@ {self.formatDesignDistance(location)} {self.actualDistanceUnitLabel()}")

        boundaries = [(km, name) for km, dwell, name in self.stopsList(dataStorage)]
        self.fillSegmentTable(self.designSegmentTable, speeds, stations, boundaries,
                              formatSpeed=self.formatDesignSpeed,
                              formatDistance=self.formatDesignDistance)

    # Header labels for the achieved-speed table, tracking whichever unit system is active
    def actualSegmentHeaders(self):
        return [
            self.lan.get("statsSegmentColumn", "Segment"),
            f"{self.lan.get('statsMaxSpeedColumnBase', 'Max speed')} [{self.actualSpeedUnitLabel()}]",
            f"{self.lan.get('statsChainageColumnBase', 'Chainage')} [{self.actualDistanceUnitLabel()}]",
        ]

    def refreshActualSpeedSection(self):
        self.actualSegmentTable.setHorizontalHeaderLabels(self.actualSegmentHeaders())

        dataStorage = self.lastDataStorage or {}
        vehicleIndex = self.vehicleCombo.currentData()
        if vehicleIndex is None:
            self.actualMaxCard.setValue(self.noDataText())
            self.actualSegmentTable.setRowCount(0)
            return

        speeds, stations = self.resolveActualSpeedArrays(dataStorage, vehicleIndex)
        peak = self.globalMax(speeds, stations)
        if peak is None:
            self.actualMaxCard.setValue(self.noDataText())
        else:
            maxSpeed, location = peak
            self.actualMaxCard.setValue(
                f"{self.formatActualSpeed(maxSpeed)} {self.actualSpeedUnitLabel()}",
                f"@ {self.formatActualDistance(location)} {self.actualDistanceUnitLabel()}")

        # Stop boundaries are recorded in km; scale to metres to match stations when not using km/h
        distanceScale = 1.0 if self.useKmh else 1000.0
        boundaries = [(km * distanceScale, name) for km, dwell, name in self.stopsList(dataStorage)]
        self.fillSegmentTable(self.actualSegmentTable, speeds, stations, boundaries,
                              self.formatActualSpeed, self.formatActualDistance)

    # Origin to destination and per leg running times of the active profile and vehicle
    def calculateSectionalTravelTimes(self):
        vehicleIndex = self.vehicleCombo.currentData()
        if vehicleIndex is None:
            return None, None, []
        # The stop chainages come from batch_metrics, which prefers the ones the engine actually ran
        return self.computeTravelTimeSections(self.lastDataStorage or {}, vehicleIndex)

    def refreshTravelTimeSection(self):
        totalTime, originDestTime, legs = self.calculateSectionalTravelTimes()
        self.totalTimeCard.setValue(self.formatDuration(totalTime))
        self.originDestCard.setValue(self.formatDuration(originDestTime))

        self.interstationTable.setRowCount(0)
        for label, legTime in legs:
            row = self.interstationTable.rowCount()
            self.interstationTable.insertRow(row)
            self.interstationTable.setItem(row, 0, QTableWidgetItem(label))
            self.interstationTable.setItem(row, 1, QTableWidgetItem(self.formatDuration(legTime)))
        self.constrainTableHeight(self.interstationTable)

    # Re-render the vehicle dependent sections only, used by the vehicle selector
    def onVehicleChanged(self, index):
        self.refreshActualSpeedSection()
        self.refreshTravelTimeSection()

    # Main entry point called whenever alignment, TTP, simulation data or the active profile changes
    def updateStatistics(self, dataStorage, vehicleNameResolver=None, useKmh=False,
                         activeProfileKey=None):
        self.lastDataStorage = dataStorage or {}
        self.vehicleNameResolver = vehicleNameResolver
        self.useKmh = bool(useKmh)
        if activeProfileKey is not None:
            self.activeProfileKey = activeProfileKey
            self.profileSelector.applyActiveProfile(activeProfileKey)
        self.rebuildVehicleCombo()
        self.updateStatisticsView()

    # Refresh every caption, header and cached value after a language change
    def updateTexts(self, lan):
        self.lan = lan or {}

        self.profileSelector.updateTexts(self.lan)
        self.vehicleRowLabel.setText(self.lan.get("statsVehicleRow", "Vehicle"))

        self.lengthCard.setCaption(self.lan.get("statsCardLength", "Total length"))
        self.designMaxCard.setCaption(self.lan.get("statsCardDesignSpeed", "Max design speed"))
        self.actualMaxCard.setCaption(self.lan.get("statsCardActualSpeed", "Max achieved speed"))
        self.totalTimeCard.setCaption(self.lan.get("statsCardTotalTime", "Total travel time"))
        self.originDestCard.setCaption(self.lan.get("statsCardOriginDest", "Origin → Destination"))

        self.designSection.setTitle(self.lan.get("statsSectionDesign", "Design segments"))
        self.actualSection.setTitle(self.lan.get("statsSectionActual", "Achieved segments"))
        self.interstationSection.setTitle(self.lan.get("statsSectionInterstation", "Inter-station times"))

        # Both segment tables follow the active units toggle, refreshed by their own sections
        self.interstationTable.setHorizontalHeaderLabels([
            self.lan.get("statsSegmentColumn", "Segment"),
            self.lan.get("statsTravelTimeColumn", "Travel time [mm:ss]"),
        ])

        self.rebuildVehicleCombo()
        self.updateStatisticsView()

    # Restyle the KPI cards and the tables with the active theme's tokens
    def applyTheme(self, isDark, tokens=None):
        tokens = tokens or (DARK_CARD_TOKENS if isDark else LIGHT_CARD_TOKENS)
        backgroundColor = tokens.get("base", "#1e1e1e" if isDark else "#ffffff")
        textColor = tokens.get("text", "#1c1c1c")
        borderColor = tokens.get("border", "#c4c4c4")

        for card in (self.lengthCard, self.designMaxCard, self.actualMaxCard,
                    self.totalTimeCard, self.originDestCard):
            card.applyTheme(isDark, tokens)

        # Setting only the background would leave the cell text on whatever the style last used
        for table in (self.designSegmentTable, self.actualSegmentTable, self.interstationTable):
            table.setAlternatingRowColors(True)
            table.setStyleSheet(
                f"QTableWidget {{ background: {backgroundColor}; color: {textColor};"
                f" gridline-color: {borderColor}; }}"
                f"QTableWidget::item {{ color: {textColor}; }}")
