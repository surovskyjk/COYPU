# Lateral slew analysis table, shared by the report window, the CSV/TXT export and the geometry report
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QHeaderView, QPushButton, QFileDialog,
                               QMessageBox, QPlainTextEdit)

import report_formats

# Translation keys of the slew table columns, in display order
SLEW_COLUMN_KEYS = (
    ("slewColId", "Curve"),
    ("slewColStartKm", "Start [km]"),
    ("slewColEndKm", "End [km]"),
    ("slewColPattern", "Pattern"),
    ("slewColRadiusOld", "R_orig [m]"),
    ("slewColRadiusNew", "R_new [m]"),
    ("slewColRadiusDelta", "dR [m]"),
    ("slewColSpiral1", "L_k1 orig -> new [m]"),
    ("slewColSpiral2", "L_k2 orig -> new [m]"),
    ("slewColSlewMax", "d_max,local [mm]"),
    ("slewColSlewAt", "at [km]"),
    ("slewColSlewEntry", "dy entry [mm]"),
    ("slewColSlewArc", "dy arc [mm]"),
    ("slewColSlewExit", "dy exit [mm]"),
    ("slewColSpeedOld", "v_orig [km/h]"),
    ("slewColSpeedNew", "v_new [km/h]"),
    ("slewColSpeedDelta", "dv [km/h]"),
    ("slewColStatus", "Status"),
)

# Placeholder written wherever a group carries no value, for instance every skipped group
NO_VALUE_TEXT = "-"

# Fallback wording of the note explaining that the tabulated slew values are local peaks
NON_PARALLEL_NOTE = ("Note: with the intersection points held fixed, an enlarged curve is not shifted "
                     "in parallel. Displacement peaks on the apex bisector and tapers to zero at the "
                     "transition tangent points, so every value below is a local peak, not a constant offset.")

# Row height of the slew table, matching the other result tables of the application
TABLE_ROW_HEIGHT_PX = 20


# The optimizer summary of the current project, or None when no optimization has been applied
def readSummary(dataStorage):
    return (dataStorage or {}).get("LandXML", {}).get("optimizationSummary")


def formatNumber(value, decimals=2):
    if value is None:
        return NO_VALUE_TEXT
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return NO_VALUE_TEXT


def formatSigned(value, decimals=2):
    if value is None:
        return NO_VALUE_TEXT
    try:
        return f"{float(value):+.{decimals}f}"
    except (TypeError, ValueError):
        return NO_VALUE_TEXT


def formatTransition(oldValue, newValue, decimals=1):
    if oldValue is None or newValue is None:
        return NO_VALUE_TEXT
    return f"{formatNumber(oldValue, decimals)} -> {formatNumber(newValue, decimals)}"


# Railway style chainage caption, 12.345 km becomes km 12+345
def formatChainage(stationKm):
    if stationKm is None:
        return NO_VALUE_TEXT
    try:
        stationKm = float(stationKm)
    except (TypeError, ValueError):
        return NO_VALUE_TEXT
    return f"km {int(stationKm)}+{abs(stationKm - int(stationKm)) * 1000.0:06.2f}"


# Seconds rendered as a signed minutes and seconds caption for the travel time delta
def formatDuration(seconds):
    if seconds is None:
        return NO_VALUE_TEXT
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return NO_VALUE_TEXT
    sign = "-" if seconds < 0 else "+"
    total = abs(seconds)
    return f"{sign}{int(total // 60)}:{total % 60:04.1f}"


def columnHeaders(lan):
    lan = lan or {}
    return [lan.get(key, fallback) for key, fallback in SLEW_COLUMN_KEYS]


# One table row per evaluated curve group, optimized and skipped alike
def buildSlewReportRows(dataStorage, lan):
    lan = lan or {}
    headerRow = columnHeaders(lan)
    summary = readSummary(dataStorage)
    if not summary:
        return headerRow, []

    dataRows = []
    for group in summary.get("groups", []):
        radiusOld = group.get("radiusOldM")
        radiusNew = group.get("radiusNewM")
        radiusDelta = (radiusNew - radiusOld) if (radiusOld is not None and radiusNew is not None) else None
        spiralsOld = group.get("spiralLengthsOldM") or [None, None]
        spiralsNew = group.get("spiralLengthsNewM") or [None, None]
        slewMaxM = group.get("slewMaxM")
        elementPeaksMm = group.get("elementSlewMaxMm") or [None, None, None]

        dataRows.append([
            str(group.get("groupIndex", 0) + 1),
            formatNumber(group.get("startKm"), 3),
            formatNumber(group.get("endKm"), 3),
            group.get("elementPattern", NO_VALUE_TEXT),
            formatNumber(radiusOld, 1),
            formatNumber(radiusNew, 1),
            formatSigned(radiusDelta, 1),
            formatTransition(spiralsOld[0], spiralsNew[0]),
            formatTransition(spiralsOld[1], spiralsNew[1]),
            formatNumber(slewMaxM * 1000.0 if slewMaxM is not None else None, 1),
            formatNumber(group.get("slewMaxStationKm"), 3),
            formatNumber(elementPeaksMm[0], 1),
            formatNumber(elementPeaksMm[1], 1),
            formatNumber(elementPeaksMm[2], 1),
            formatNumber(group.get("speedOldKmh"), 0),
            formatNumber(group.get("speedNewKmh"), 0),
            formatSigned(group.get("speedDeltaKmh"), 0),
            lan.get(group.get("status", ""), group.get("status", "")),
        ])
    return headerRow, dataRows


# Corridor wide figures shown above the table and repeated at the top of every export
def buildSlewSummaryLines(dataStorage, lan):
    lan = lan or {}
    summary = readSummary(dataStorage)
    if not summary:
        return [lan.get("slewNoOptimization", "No alignment optimization has been applied.")]

    maxSlewMm = (summary.get("maxSlewM") or 0.0) * 1000.0
    meanSlewMm = (summary.get("meanSlewCurvedM") or 0.0) * 1000.0
    travelTimeDeltaS = summary.get("travelTimeDeltaS")

    lines = [
        f"{lan.get('slewSummaryEvaluated', 'Total line length evaluated')}: "
        f"{formatNumber(summary.get('evaluatedLengthKm'), 3)} km",
        f"{lan.get('slewSummaryShifted', 'Total shifted length')}: "
        f"{formatNumber(summary.get('shiftedLengthKm'), 3)} km "
        f"({formatNumber(summary.get('shiftedLengthPercent'), 1)} %)",
        f"{lan.get('slewSummaryMaxSlew', 'Global maximum lateral slew')}: "
        f"{formatNumber(maxSlewMm, 1)} mm @ {formatNumber(summary.get('maxSlewStationKm'), 3)} km",
        f"{lan.get('slewSummaryMeanSlew', 'Average slew in curved sections')}: "
        f"{formatNumber(meanSlewMm, 1)} mm",
        f"{lan.get('slewSummaryGroups', 'Curve groups optimized / skipped')}: "
        f"{summary.get('optimizedGroupCount', 0)} / {summary.get('skippedGroupCount', 0)}",
        f"{lan.get('slewSummaryEnvelope', 'Envelope d_max / L_min')}: "
        f"{formatNumber(summary.get('dMaxM'), 2)} m / {formatNumber(summary.get('lMinM'), 1)} m",
    ]
    if travelTimeDeltaS is not None:
        lines.append(
            f"{lan.get('slewSummaryTravelTime', 'Theoretical travel time change')}: "
            f"{formatSigned(travelTimeDeltaS, 1)} s ({formatDuration(travelTimeDeltaS)})")

    if summary.get("hasClampedChainage"):
        lines.append(lan.get("slewClampedChainage",
                             "Warning: at least one straight was consumed past its own start and "
                             "its length was clamped to zero. Check the affected curve groups."))

    # Enlarging a curve between fixed vertices is not a parallel shift, the table shows peaks
    lines.append(lan.get("slewNonParallelNote", NON_PARALLEL_NOTE))
    return lines


# Whole section as flat text lines, the shape report_formats renders into txt, md, tex and pdf
def buildSlewReportLines(dataStorage, lan):
    lan = lan or {}
    title = lan.get("slewReportTitle", "Lateral Alignment Slew Summary")
    lines = [f"=== {title} ===", ""]
    lines.extend(buildSlewSummaryLines(dataStorage, lan))
    lines.append("")

    headerRow, dataRows = buildSlewReportRows(dataStorage, lan)
    if not dataRows:
        return lines

    columnWidths = [len(headerRow[index]) for index in range(len(headerRow))]
    for row in dataRows:
        for index, cell in enumerate(row):
            columnWidths[index] = max(columnWidths[index], len(cell))

    def formatRow(cells):
        return "  ".join(cell.ljust(columnWidths[index]) for index, cell in enumerate(cells)).rstrip()

    lines.append(formatRow(headerRow))
    lines.append("-" * len(formatRow(headerRow)))
    lines.extend(formatRow(row) for row in dataRows)
    return lines


class SlewReportWindow(QDialog):
    def __init__(self, dataStorage, lan, parent=None):
        super().__init__(parent)
        self.lan = lan or {}
        self.dataStorage = dataStorage

        self.setWindowTitle(self.lan.get("slewReportTitle", "Lateral Alignment Slew Summary"))
        self.resize(1100, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.summaryView = QPlainTextEdit()
        self.summaryView.setReadOnly(True)
        self.summaryView.setMaximumHeight(140)
        layout.addWidget(self.summaryView)

        self.groupTable = self.buildGroupTable(len(SLEW_COLUMN_KEYS))
        layout.addWidget(self.groupTable, 1)

        buttonRow = QHBoxLayout()
        self.exportCsvButton = QPushButton(self.lan.get("slewExportCsv", "Export CSV"))
        self.exportCsvButton.clicked.connect(self.exportCsv)
        self.exportTxtButton = QPushButton(self.lan.get("slewExportTxt", "Export TXT"))
        self.exportTxtButton.clicked.connect(self.exportTxt)
        self.closeButton = QPushButton(self.lan.get("close", "Close"))
        self.closeButton.clicked.connect(self.close)
        buttonRow.addWidget(self.exportCsvButton)
        buttonRow.addWidget(self.exportTxtButton)
        buttonRow.addStretch(1)
        buttonRow.addWidget(self.closeButton)
        layout.addLayout(buttonRow)

        self.updateTexts(self.lan)
        self.updateData(dataStorage)

    # Same read only grid the track statistics dock uses for its segment tables
    def buildGroupTable(self, columnCount):
        table = QTableWidget(0, columnCount)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT_PX)
        return table

    # Explain on the slew columns that their values are local peaks rather than a parallel offset
    def applySlewColumnTooltips(self):
        tooltip = self.lan.get("slewNonParallelNote", NON_PARALLEL_NOTE)
        columnKeys = [key for key, _ in SLEW_COLUMN_KEYS]
        for columnKey in ("slewColSlewMax", "slewColSlewEntry", "slewColSlewArc", "slewColSlewExit"):
            headerItem = self.groupTable.horizontalHeaderItem(columnKeys.index(columnKey))
            if headerItem is not None:
                headerItem.setToolTip(tooltip)

    # Refill both the summary block and the group table from the current data storage
    def updateData(self, dataStorage):
        self.dataStorage = dataStorage
        self.summaryView.setPlainText("\n".join(buildSlewSummaryLines(dataStorage, self.lan)))

        _, dataRows = buildSlewReportRows(dataStorage, self.lan)
        self.groupTable.setRowCount(len(dataRows))
        for rowIndex, row in enumerate(dataRows):
            for columnIndex, cell in enumerate(row):
                self.groupTable.setItem(rowIndex, columnIndex, QTableWidgetItem(cell))

    # Re-apply every caption after a language change, headers included
    def updateTexts(self, lan):
        self.lan = lan or {}
        self.setWindowTitle(self.lan.get("slewReportTitle", "Lateral Alignment Slew Summary"))
        self.groupTable.setHorizontalHeaderLabels(columnHeaders(self.lan))
        self.applySlewColumnTooltips()
        self.exportCsvButton.setText(self.lan.get("slewExportCsv", "Export CSV"))
        self.exportTxtButton.setText(self.lan.get("slewExportTxt", "Export TXT"))
        self.closeButton.setText(self.lan.get("close", "Close"))
        self.updateData(self.dataStorage)

    def exportCsv(self):
        filePath, _ = QFileDialog.getSaveFileName(
            self, self.lan.get("slewExportCsv", "Export CSV"), "", "CSV (*.csv)")
        if not filePath:
            return
        try:
            headerRow, dataRows = buildSlewReportRows(self.dataStorage, self.lan)
            report_formats.rowsToCsv(filePath, headerRow, dataRows)
        except Exception as exc:
            QMessageBox.critical(self, self.lan.get("error", "Error"), f"{exc}")

    def exportTxt(self):
        filePath, _ = QFileDialog.getSaveFileName(
            self, self.lan.get("slewExportTxt", "Export TXT"), "", "Text (*.txt)")
        if not filePath:
            return
        try:
            reportLines = buildSlewReportLines(self.dataStorage, self.lan)
            titleText = self.lan.get("slewReportTitle", "Lateral Alignment Slew Summary")
            report_formats.writeReportFile(reportLines, filePath, titleText)
        except Exception as exc:
            QMessageBox.critical(self, self.lan.get("error", "Error"), f"{exc}")
