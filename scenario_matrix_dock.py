# Scenario matrix results panel and the dialog that chooses what a matrix run covers
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

import batch_metrics
import karto_export
import profile_state
import scenario_matrix
import schedule_rules
import simulation_runner
import stops_model
from ui_kit import DARK_CARD_TOKENS, LIGHT_CARD_TOKENS, patternCaptionFor, stopsCountText

# Value modes of the matrix table
VALUE_MODE_RAW = "raw"
VALUE_MODE_SCHEDULED = "scheduled"

# Row height of the compact tables, matching the statistics dock
TABLE_ROW_HEIGHT_PX = 22

# Stands in for the dwell at the destination, which is not part of the journey
NO_VALUE_TEXT = "–"

# Translation key and English fallback of every cell status
STATUS_TEXTS = {
    scenario_matrix.STATUS_NOT_CERTIFIED: ("matrixStatusNotCertified", "not certified"),
    scenario_matrix.STATUS_ZERO_SPEED_SECTION: ("matrixStatusZeroSpeed", "no permitted speed"),
    scenario_matrix.STATUS_NO_TRACK_DATA: ("matrixStatusNoTrackData", "no track data"),
    scenario_matrix.STATUS_TOO_FEW_STOPS: ("matrixStatusTooFewStops", "fewer than 2 stops"),
    scenario_matrix.STATUS_TRAIN_TOO_LONG: ("matrixStatusTrainTooLong", "train longer than the line"),
}

# Results of the last scenario matrix run: tiers across, vehicle and pattern down
class ScenarioMatrixWidget(QWidget):
    # Asked by the empty state, the margins button and the stale badge, handled by the main window
    runRequested = Signal()
    marginsRequested = Signal()
    rerunRequested = Signal()

    def __init__(self, lan, parent=None):
        super().__init__(parent)

        self.lan = lan or {}
        self.dataStorage = {}
        self.cellIndex = {}
        self.rowKeys = []

        outerLayout = QVBoxLayout(self)
        outerLayout.setContentsMargins(4, 4, 4, 4)
        outerLayout.setSpacing(4)

        # Everything that only makes sense next to results hides together in the empty state
        self.controlsHost = QWidget()
        controlsLayout = QHBoxLayout(self.controlsHost)
        controlsLayout.setContentsMargins(0, 0, 0, 0)
        controlsLayout.setSpacing(4)
        self.valueModeLabel = QLabel()
        self.valueModeCombo = QComboBox()
        self.valueModeCombo.currentIndexChanged.connect(self.rebuildView)
        self.marginsButton = QPushButton()
        self.marginsButton.clicked.connect(self.marginsRequested)
        self.directionLabel = QLabel()
        self.directionCombo = QComboBox()
        self.directionCombo.currentIndexChanged.connect(self.rebuildView)
        self.exportButton = QPushButton()
        self.exportButton.clicked.connect(self.exportCsv)
        controlsLayout.addWidget(self.valueModeLabel)
        controlsLayout.addWidget(self.valueModeCombo)
        controlsLayout.addWidget(self.marginsButton)
        controlsLayout.addWidget(self.directionLabel)
        controlsLayout.addWidget(self.directionCombo, 1)
        controlsLayout.addWidget(self.exportButton)
        outerLayout.addWidget(self.controlsHost)

        self.staleHost = QWidget()
        staleLayout = QHBoxLayout(self.staleHost)
        staleLayout.setContentsMargins(0, 0, 0, 0)
        self.staleLabel = QLabel()
        self.staleLabel.setWordWrap(True)
        self.rerunButton = QPushButton()
        self.rerunButton.clicked.connect(self.rerunRequested)
        staleLayout.addWidget(self.staleLabel, 1)
        staleLayout.addWidget(self.rerunButton)
        self.staleHost.setVisible(False)
        outerLayout.addWidget(self.staleHost)

        # Empty state: a centred message and the button that starts a first run
        self.emptyHost = QWidget()
        emptyLayout = QVBoxLayout(self.emptyHost)
        emptyLayout.addStretch(1)
        self.emptyLabel = QLabel()
        self.emptyLabel.setWordWrap(True)
        self.emptyLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.runButton = QPushButton()
        self.runButton.clicked.connect(self.runRequested)
        emptyLayout.addWidget(self.emptyLabel)
        emptyLayout.addWidget(self.runButton, 0, Qt.AlignmentFlag.AlignHCenter)
        emptyLayout.addStretch(1)
        outerLayout.addWidget(self.emptyHost, 1)

        self.matrixTable = QTableWidget(0, 0)
        self.matrixTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.matrixTable.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.matrixTable.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT_PX)
        self.matrixTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.matrixTable.currentCellChanged.connect(self.onCurrentCellChanged)

        detailHost = QWidget()
        detailLayout = QVBoxLayout(detailHost)
        detailLayout.setContentsMargins(0, 0, 0, 0)
        detailLayout.setSpacing(4)
        self.cellInfoLabel = QLabel()
        self.cellInfoLabel.setWordWrap(True)
        self.legTable = QTableWidget(0, 5)
        self.legTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.legTable.verticalHeader().setVisible(False)
        self.legTable.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT_PX)
        self.legTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.relaxedLabel = QLabel()
        self.relaxedLabel.setWordWrap(True)
        self.relaxedLabel.setVisible(False)
        detailLayout.addWidget(self.cellInfoLabel)
        detailLayout.addWidget(self.legTable, 1)
        detailLayout.addWidget(self.relaxedLabel)

        self.tableSplitter = QSplitter(Qt.Orientation.Vertical)
        self.tableSplitter.addWidget(self.matrixTable)
        self.tableSplitter.addWidget(detailHost)
        self.tableSplitter.setStretchFactor(0, 1)
        self.tableSplitter.setStretchFactor(1, 1)
        outerLayout.addWidget(self.tableSplitter, 1)

        self.updateTexts(self.lan)

    # Text shown wherever a value is missing
    def noDataText(self):
        return self.lan.get("statsNoData", "No data")

    # Stored matrix of the current data storage, None when no run exists
    def currentMatrix(self):
        matrix = self.dataStorage.get(scenario_matrix.MATRIX_STORAGE_KEY)
        return matrix if matrix and matrix.get("cells") else None

    # Stop records of the current project by their identifier
    def recordsById(self):
        settingsData = self.dataStorage.get("settingsData", {}) or {}
        records = stops_model.normalizeStopRecords(settingsData.get("stopRecords"))
        return {record["stopId"]: record for record in records}

    # Vehicle caption of a matrix row
    def vehicleCaption(self, vehicleIndex, vehicleName):
        return vehicleName or f'{self.lan.get("vehicle", "Vehicle")} {vehicleIndex + 1}'

    # Caption of one pattern, with its short code in front of the translated name
    def patternCaption(self, patternKey):
        return patternCaptionFor(self.lan, patternKey)

    # Entry point called whenever the stored matrix, the stops or the schedule settings may have changed
    def setData(self, dataStorage):
        self.dataStorage = dataStorage or {}
        self.rebuildDirectionCombo()
        self.rebuildView()

    # Direction entries labelled by the stops of the line, a vehicle's own label shows in the cell line
    def rebuildDirectionCombo(self):
        previousDirection = self.directionCombo.currentData()
        settingsData = self.dataStorage.get("settingsData", {}) or {}
        records = stops_model.normalizeStopRecords(settingsData.get("stopRecords"))
        lowCaption, highCaption = stops_model.lineEndpointCaptions(records)

        self.directionCombo.blockSignals(True)
        self.directionCombo.clear()
        for directionKey in simulation_runner.DIRECTION_KEYS:
            isForward = directionKey == "forward"
            wordKey, wordFallback = ("directionForwardShort", "Forward") if isForward else \
                ("directionReverseShort", "Reverse")
            word = self.lan.get(wordKey, wordFallback)
            route = f"{lowCaption} → {highCaption}" if isForward else f"{highCaption} → {lowCaption}"
            self.directionCombo.addItem(f"{word}: {route}" if lowCaption or highCaption else word, directionKey)
        restored = self.directionCombo.findData(previousDirection)
        self.directionCombo.setCurrentIndex(restored if restored >= 0 else 0)
        self.directionCombo.blockSignals(False)

    # Text of one cell in the active value mode
    def cellText(self, cell, valueMode, scheduleSettings):
        if cell is None:
            return "-"
        if cell["status"] != scenario_matrix.STATUS_OK:
            textKey, fallback = STATUS_TEXTS.get(cell["status"], (cell["status"], cell["status"]))
            return self.lan.get(textKey, fallback)
        if valueMode == VALUE_MODE_SCHEDULED:
            scheduled = schedule_rules.scheduleCell(cell, scheduleSettings)
            seconds = scheduled["scheduledOriginDestS"] if scheduled else None
        else:
            seconds = cell.get("rawOriginDestS")
        return batch_metrics.formatDuration(seconds, self.noDataText())

    # Rebuild the matrix table and the leg table of the selected cell
    def rebuildView(self, index=None):
        matrix = self.currentMatrix()
        selectedRow = self.matrixTable.currentRow()
        selectedColumn = self.matrixTable.currentColumn()
        self.matrixTable.blockSignals(True)
        self.matrixTable.clear()
        self.matrixTable.setRowCount(0)
        self.matrixTable.setColumnCount(0)
        self.legTable.setRowCount(0)
        self.cellInfoLabel.setText("")
        self.relaxedLabel.setVisible(False)
        self.cellIndex = {}
        self.rowKeys = []

        hasMatrix = matrix is not None
        self.emptyHost.setVisible(not hasMatrix)
        self.controlsHost.setVisible(hasMatrix)
        self.tableSplitter.setVisible(hasMatrix)
        self.staleHost.setVisible(hasMatrix and scenario_matrix.isMatrixStale(self.dataStorage))
        if not hasMatrix:
            self.matrixTable.blockSignals(False)
            return

        for cell in matrix["cells"]:
            self.cellIndex[(cell["vehicleIndex"], cell["patternKey"], cell["profileKey"],
                            cell["direction"])] = cell
        vehicleNames = {cell["vehicleIndex"]: cell["vehicleName"] for cell in matrix["cells"]}

        for vehicleIndex in matrix["vehicleIndices"]:
            for patternKey in matrix["patternKeys"]:
                self.rowKeys.append((vehicleIndex, patternKey))

        profileKeys = list(matrix["profileKeys"])
        self.matrixTable.setColumnCount(len(profileKeys))
        self.matrixTable.setRowCount(len(self.rowKeys))
        self.matrixTable.setHorizontalHeaderLabels(
            [profile_state.profileShortName(profileKey) for profileKey in profileKeys])
        self.matrixTable.setVerticalHeaderLabels([
            f"{self.vehicleCaption(vehicleIndex, vehicleNames.get(vehicleIndex, ''))} · "
            f"{self.patternCaption(patternKey)}" for vehicleIndex, patternKey in self.rowKeys])

        directionKey = self.directionCombo.currentData() or "forward"
        valueMode = self.valueModeCombo.currentData() or VALUE_MODE_RAW
        scheduleSettings = (self.dataStorage.get("settingsData", {}) or {}).get("scheduleSettings")
        for row, (vehicleIndex, patternKey) in enumerate(self.rowKeys):
            for column, profileKey in enumerate(profileKeys):
                cell = self.cellIndex.get((vehicleIndex, patternKey, profileKey, directionKey))
                self.matrixTable.setItem(
                    row, column, QTableWidgetItem(self.cellText(cell, valueMode, scheduleSettings)))
        self.matrixTable.blockSignals(False)

        # The selection survives a mode or direction switch, so its legs follow the new values
        if 0 <= selectedRow < self.matrixTable.rowCount() and 0 <= selectedColumn < self.matrixTable.columnCount():
            self.matrixTable.setCurrentCell(selectedRow, selectedColumn)

    # Table item with the text right-aligned, used by every time column of the leg table
    def numberItem(self, text, isBold=False):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if isBold:
            boldFont = item.font()
            boldFont.setBold(True)
            item.setFont(boldFont)
        return item

    # Show the legs of the cell the user selected
    def onCurrentCellChanged(self, row, column, previousRow, previousColumn):
        matrix = self.currentMatrix()
        self.legTable.setRowCount(0)
        self.cellInfoLabel.setText("")
        self.relaxedLabel.setVisible(False)
        if matrix is None or not (0 <= row < len(self.rowKeys)) or column < 0:
            return

        vehicleIndex, patternKey = self.rowKeys[row]
        profileKey = matrix["profileKeys"][column]
        directionKey = self.directionCombo.currentData() or "forward"
        cell = self.cellIndex.get((vehicleIndex, patternKey, profileKey, directionKey))
        if cell is None:
            return

        records = self.recordsById()
        scheduleSettings = (self.dataStorage.get("settingsData", {}) or {}).get("scheduleSettings")
        scheduled = schedule_rules.scheduleCell(cell, scheduleSettings)
        scheduledLegs = scheduled["scheduledLegsS"] if scheduled else [None] * len(cell["sections"])

        originRecord = records.get(cell.get("originStopId"))
        destinationRecord = records.get(cell.get("destinationStopId"))
        vehicles = scenario_matrix.matrixVehicles(self.dataStorage.get("settingsData", {}) or {})
        vehicleSettings = vehicles[vehicleIndex] if 0 <= vehicleIndex < len(vehicles) else {}
        label = stops_model.resolveDirectionLabel(
            vehicleSettings, directionKey,
            stops_model.stopCaption(originRecord) if originRecord else "",
            stops_model.stopCaption(destinationRecord) if destinationRecord else "")
        infoParts = [self.vehicleCaption(vehicleIndex, cell["vehicleName"]), self.patternCaption(patternKey),
                     profile_state.profileShortName(profileKey), label]
        self.cellInfoLabel.setText(" · ".join(part for part in infoParts if part))
        self.relaxedLabel.setVisible(bool(scheduled and scheduled.get("isLegRoundingRelaxed")))

        sections = cell["sections"]
        for legIndex, (section, scheduledRunS) in enumerate(zip(sections, scheduledLegs)):
            fromRecord = records.get(section["fromStopId"])
            toRecord = records.get(section["toStopId"])
            legLabel = (f"{stops_model.stopCaption(fromRecord) if fromRecord else section['fromStopId']}"
                        f" → "
                        f"{stops_model.stopCaption(toRecord) if toRecord else section['toStopId']}")
            isLastLeg = legIndex == len(sections) - 1
            legRow = self.legTable.rowCount()
            self.legTable.insertRow(legRow)
            self.legTable.setItem(legRow, 0, QTableWidgetItem(legLabel))
            self.legTable.setItem(legRow, 1, self.numberItem(f"{section['lengthKm']:.3f}"))
            self.legTable.setItem(legRow, 2, self.numberItem(
                batch_metrics.formatDuration(section["rawRunS"], self.noDataText())))
            self.legTable.setItem(legRow, 3, self.numberItem(
                batch_metrics.formatDuration(scheduledRunS, self.noDataText())))
            # The dwell at the destination is not part of the journey, so it shows no value
            self.legTable.setItem(legRow, 4, self.numberItem(
                NO_VALUE_TEXT if isLastLeg else f"{section['dwellAtToS']:.0f}"))

        if sections:
            totalRow = self.legTable.rowCount()
            self.legTable.insertRow(totalRow)
            totalItem = QTableWidgetItem(self.lan.get("matrixRowTotal", "Total"))
            totalFont = totalItem.font()
            totalFont.setBold(True)
            totalItem.setFont(totalFont)
            self.legTable.setItem(totalRow, 0, totalItem)
            rawTotalS = sum(section["rawRunS"] for section in sections if section["rawRunS"] is not None)
            scheduledTotalS = sum(value for value in scheduledLegs if value is not None) if scheduled else None
            self.legTable.setItem(totalRow, 1, self.numberItem(
                f"{sum(section['lengthKm'] for section in sections):.3f}", True))
            self.legTable.setItem(totalRow, 2, self.numberItem(
                batch_metrics.formatDuration(rawTotalS, self.noDataText()), True))
            self.legTable.setItem(totalRow, 3, self.numberItem(
                batch_metrics.formatDuration(scheduledTotalS, self.noDataText()), True))
            self.legTable.setItem(totalRow, 4, self.numberItem(
                f"{sum(section['dwellAtToS'] for section in sections[:-1]):.0f}", True))

    # Write every scenario of the stored matrix, with scheduled values, into one CSV file
    def exportCsv(self):
        matrix = self.currentMatrix()
        if matrix is None:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, self.lan.get("matrixExportCsv", "Export scenario matrix to CSV"),
            "scenario_matrix.csv", self.lan.get("csvFileFilter", "CSV Files (*.csv)"))
        if not filepath:
            return
        settingsData = self.dataStorage.get("settingsData", {}) or {}
        records = stops_model.normalizeStopRecords(settingsData.get("stopRecords"))
        scenarios = karto_export.buildTravelTimes(self.dataStorage, settingsData, records)["scenarios"]
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as fileHandle:
                fileHandle.write(scenario_matrix.scenariosToCsv(scenarios))
        except OSError as exportError:
            QMessageBox.critical(self, self.lan.get("error", "Error"), str(exportError))

    # Refresh every caption after a language change, then redraw the cached values
    def updateTexts(self, lan):
        self.lan = lan or {}
        self.valueModeLabel.setText(self.lan.get("matrixValueMode", "Values:"))
        previousMode = self.valueModeCombo.currentData()
        self.valueModeCombo.blockSignals(True)
        self.valueModeCombo.clear()
        self.valueModeCombo.addItem(self.lan.get("matrixModeRaw", "Raw (theoretical)"), VALUE_MODE_RAW)
        self.valueModeCombo.addItem(self.lan.get("matrixModeScheduled", "Scheduled"), VALUE_MODE_SCHEDULED)
        restored = self.valueModeCombo.findData(previousMode)
        self.valueModeCombo.setCurrentIndex(restored if restored >= 0 else 0)
        self.valueModeCombo.blockSignals(False)
        self.valueModeCombo.setToolTip(self.lan.get(
            "matrixModeTip", "Raw is the theoretical running time, scheduled adds the timetable margins and rounding"))
        self.marginsButton.setText(self.lan.get("matrixMargins", "Margins..."))
        self.marginsButton.setToolTip(self.lan.get("scheduleSettingsTitle", "Timetable margins"))

        self.directionLabel.setText(self.lan.get("matrixDirection", "Direction:"))
        self.directionCombo.setToolTip(self.lan.get(
            "matrixDirectionTip", "Forward runs along rising chainage, reverse against it"))
        self.exportButton.setText(self.lan.get("matrixExportCsv", "Export scenario matrix to CSV"))
        self.exportButton.setToolTip(self.lan.get(
            "matrixExportTip", "Write every scenario with its legs and scheduled values to one CSV file"))
        self.staleLabel.setText(self.lan.get(
            "matrixStale", "These results are out of date: stops, vehicles, speed profiles or the alignment changed since the run."))
        self.rerunButton.setText(self.lan.get("matrixRerun", "Re-run"))
        self.rerunButton.setToolTip(self.lan.get(
            "matrixRerunTip", "Open the matrix dialog with the last selection"))
        self.emptyLabel.setText(self.lan.get(
            "matrixEmpty", "No scenario matrix yet. Run Simulation > Scenario matrix to fill this panel."))
        self.runButton.setText(self.lan.get("matrixRunButton", "Run scenario matrix..."))
        self.relaxedLabel.setText(self.lan.get(
            "matrixLegRoundingRelaxed",
            "The legs are not whole steps: rounding could not keep every leg at or above its raw running time."))
        self.legTable.setHorizontalHeaderLabels([
            self.lan.get("statsSegmentColumn", "Segment"),
            self.lan.get("matrixColLength", "Length [km]"),
            self.lan.get("matrixColRaw", "Raw [mm:ss]"),
            self.lan.get("matrixColScheduled", "Scheduled [mm:ss]"),
            self.lan.get("matrixColDwell", "Dwell [s]"),
        ])
        self.setData(self.dataStorage)

    # Restyle the tables and the badges with the active theme's tokens
    def applyTheme(self, isDark, tokens=None):
        tokens = tokens or (DARK_CARD_TOKENS if isDark else LIGHT_CARD_TOKENS)
        backgroundColor = tokens.get("base", "#1e1e1e" if isDark else "#ffffff")
        textColor = tokens.get("text", "#1c1c1c")
        borderColor = tokens.get("border", "#c4c4c4")
        mutedColor = tokens.get("mutedText", "#5a5a5a")
        errorColor = tokens.get("error", "#e57373" if isDark else "#c0392b")

        for table in (self.matrixTable, self.legTable):
            table.setAlternatingRowColors(True)
            table.setStyleSheet(
                f"QTableWidget {{ background: {backgroundColor}; color: {textColor};"
                f" gridline-color: {borderColor}; }}"
                f"QTableWidget::item {{ color: {textColor}; }}")
        self.staleLabel.setStyleSheet(f"font-weight: 600; color: {errorColor};")
        self.emptyLabel.setStyleSheet(f"color: {mutedColor};")
        self.cellInfoLabel.setStyleSheet(f"color: {mutedColor};")
        self.relaxedLabel.setStyleSheet(f"color: {mutedColor};")


# Dialog choosing the tiers, vehicles and stopping patterns a matrix run covers
class ScenarioMatrixDialog(QDialog):
    def __init__(self, dataStorage, lan, parent=None, initialRequest=None):
        super().__init__(parent)
        self.lan = lan or {}
        self.dataStorage = dataStorage or {}
        settingsData = self.dataStorage.get("settingsData", {}) or {}
        self.vehicles = scenario_matrix.matrixVehicles(settingsData)
        records = stops_model.normalizeStopRecords(settingsData.get("stopRecords"))
        self.evaluableKeys = simulation_runner.evaluableProfileKeys(self.dataStorage, self.vehicles)
        initialRequest = initialRequest or {}

        self.setWindowTitle(self.lan.get("matrixDialogTitle", "Scenario matrix"))
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        hintLabel = QLabel(self.lan.get(
            "matrixDialogHint",
            "Raw theoretical travel times for every combination below, in both directions."))
        hintLabel.setWordWrap(True)
        layout.addWidget(hintLabel)

        self.tierChecks = {}
        tierGroup = QGroupBox(self.lan.get("matrixTiers", "Speed profiles (GPK tiers)"))
        tierLayout = QVBoxLayout(tierGroup)
        for profileKey in profile_state.PROFILE_KEYS:
            captionKey = profile_state.PROFILE_LABEL_KEYS.get(profileKey, profileKey)
            check = QCheckBox(self.lan.get(captionKey, profileKey))
            isEvaluable = profileKey in self.evaluableKeys
            check.setEnabled(isEvaluable)
            if not isEvaluable:
                check.setToolTip(self.lan.get(
                    "matrixTierDisabledTip",
                    "This speed profile has no data yet, or no vehicle is certified for it"))
            check.setChecked(isEvaluable and (profileKey in initialRequest.get("profileKeys", [profileKey])))
            check.toggled.connect(self.updateSummary)
            tierLayout.addWidget(check)
            self.tierChecks[profileKey] = check
        layout.addWidget(tierGroup)

        self.vehicleChecks = []
        vehicleGroup = QGroupBox(self.lan.get("matrixVehicles", "Vehicles"))
        vehicleLayout = QVBoxLayout(vehicleGroup)
        for vehicleIndex, vehicleSettings in enumerate(self.vehicles):
            caption = (scenario_matrix.vehicleDisplayName(vehicleSettings)
                       or f'{self.lan.get("vehicle", "Vehicle")} {vehicleIndex + 1}')
            check = QCheckBox(caption)
            check.setChecked(vehicleIndex in initialRequest.get("vehicleIndices", [vehicleIndex]))
            check.toggled.connect(self.updateSummary)
            vehicleLayout.addWidget(check)
            self.vehicleChecks.append(check)
        layout.addWidget(vehicleGroup)

        self.patternChecks = {}
        counts = stops_model.patternStopCounts(records)
        patternGroup = QGroupBox(self.lan.get("matrixPatterns", "Stopping patterns"))
        patternLayout = QVBoxLayout(patternGroup)
        for patternKey in stops_model.PATTERN_KEYS:
            caption = patternCaptionFor(self.lan, patternKey)
            check = QCheckBox(f"{caption} ({stopsCountText(self.lan, counts[patternKey])})")
            defaultChecked = counts[patternKey] >= 2
            if not defaultChecked:
                check.setToolTip(self.lan.get("matrixStatusTooFewStops", "fewer than 2 stops"))
            check.setChecked(patternKey in initialRequest["patternKeys"] if "patternKeys" in initialRequest
                             else defaultChecked)
            check.toggled.connect(self.updateSummary)
            patternLayout.addWidget(check)
            self.patternChecks[patternKey] = check
        layout.addWidget(patternGroup)

        self.summaryLabel = QLabel()
        layout.addWidget(self.summaryLabel)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                          | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

        self.updateSummary()

    # Profile keys ticked in the dialog
    def selectedProfileKeys(self):
        return [profileKey for profileKey, check in self.tierChecks.items()
                if check.isEnabled() and check.isChecked()]

    # Vehicle indices ticked in the dialog
    def selectedVehicleIndices(self):
        return [index for index, check in enumerate(self.vehicleChecks) if check.isChecked()]

    # Pattern keys ticked in the dialog
    def selectedPatternKeys(self):
        return [patternKey for patternKey, check in self.patternChecks.items() if check.isChecked()]

    # Show the number of engine passes and only allow a run that covers something
    def updateSummary(self, checked=None):
        passCount = scenario_matrix.countEnginePasses(len(self.selectedPatternKeys()),
                                                      len(self.selectedProfileKeys()))
        template = self.lan.get("matrixPassCount", "{count} engine passes, both directions included")
        self.summaryLabel.setText(template.format(count=passCount))
        isRunnable = bool(passCount and self.selectedVehicleIndices())
        self.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(isRunnable)

    # The request the main window starts the worker with
    def getRequest(self):
        return {
            "profileKeys": self.selectedProfileKeys(),
            "vehicleIndices": self.selectedVehicleIndices(),
            "patternKeys": self.selectedPatternKeys(),
        }
