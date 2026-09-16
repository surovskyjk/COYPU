# Vehicle catalog browser and the dynamic 1..N vehicle settings dialog
import csv
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

import default_values
import readfile
from plot_widgets import CoypuPlotWidget
from ui_kit import CollapsibleSection, MetricCard
from vehicle_catalog import (CatalogVehicle, DEFAULT_MAX_CANT_DEFICIENCY_MM,
                             DEFAULT_ROT_MASS_FACTOR, MAX_VEHICLES, VehicleCatalog, toFloat)


# Small pyqtgraph canvas rendering the tractive effort against speed curve
class TractiveCurveWidget(CoypuPlotWidget):
    def __init__(self, lan, parent=None):
        super().__init__(lan, parent)

        self.plotTraction = self.addPlotRow("traction", 0)

        self.updateLabels(lan)
        self.applyTheme(False)

    # Refresh axis labels after a language change
    def updateLabels(self, lan):
        self.lan = lan
        self.plotTitles["traction"] = lan.get("tractiveEffortPlot", "Tractive effort curve")
        self.plotTraction.setLabel("bottom", lan.get("speedAxisKmh", "Speed [km/h]"))
        self.plotTraction.setLabel("left", lan.get("tractiveEffortAxis", "Tractive effort [kN]"))
        self.retranslateMenus(lan)

    # Sample the given traction bands and redraw the curve
    def showBands(self, tracBands, vehicleName=""):
        self.clearPlot("traction")

        sampler = CatalogVehicle()
        sampler.tracBands = tracBands or []
        speeds, forces = sampler.sampleTractiveCurve()

        if not speeds:
            self.plotTraction.vb.setYRange(0, 1, padding=0)
            return

        self.setSeriesData("traction", "tractiveEffort", speeds, forces,
                           name=vehicleName or self.lan.get("tractiveEffortPlot", "Tractive effort"),
                           styleKey="simulated")

        peak = max(forces)
        self.plotTraction.vb.setYRange(0, max(peak * 1.05, 1.0), padding=0)


# Read-only browser over the vehicles/ folder with KPI cards and the F(v) diagram
class VehicleCatalogDialog(QDialog):
    def __init__(self, catalog, lan, isDarkActive=False, tokens=None, parent=None):
        super().__init__(parent)
        self.lan = lan
        self.catalog = catalog
        self.selectedVehicleName = None

        self.setWindowTitle(lan.get("vehicleCatalog", "Vehicle Catalog"))
        self.setMinimumSize(760, 480)

        outerLayout = QVBoxLayout(self)
        outerLayout.setContentsMargins(8, 8, 8, 8)
        outerLayout.setSpacing(6)

        bodyLayout = QHBoxLayout()
        outerLayout.addLayout(bodyLayout, 1)

        self.vehicleList = QListWidget()
        self.vehicleList.setMaximumWidth(220)
        self.vehicleList.currentRowChanged.connect(self.onVehicleSelected)
        bodyLayout.addWidget(self.vehicleList)

        rightLayout = QVBoxLayout()
        bodyLayout.addLayout(rightLayout, 1)

        cardsLayout = QGridLayout()
        cardsLayout.setSpacing(6)
        self.maxSpeedCard = MetricCard(lan.get("max_train_speed", "Max Train Speed [km/h]:"))
        self.massCard = MetricCard(lan.get("vehicleMass", "Mass [t]"))
        self.lengthCard = MetricCard(lan.get("vehicleLengthM", "Length [m]"))
        self.brakeCard = MetricCard(lan.get("vehicleBrakeDecel", "Braking Deceleration [m/s2]:"))
        self.peakForceCard = MetricCard(lan.get("maxTractiveForce", "Peak tractive force [kN]"))
        for column, card in enumerate((self.maxSpeedCard, self.massCard, self.lengthCard,
                                       self.brakeCard, self.peakForceCard)):
            cardsLayout.addWidget(card, 0, column)
        rightLayout.addLayout(cardsLayout)

        self.curveWidget = TractiveCurveWidget(lan)
        self.curveWidget.setMinimumHeight(260)
        rightLayout.addWidget(self.curveWidget, 1)

        toolbarLayout = QHBoxLayout()
        self.btnRescan = QPushButton(lan.get("catalogRescan", "Rescan"))
        self.btnRescan.clicked.connect(self.rescanCatalog)
        self.btnAssign = QPushButton(lan.get("catalogAssign", "Assign to active vehicle"))
        self.btnAssign.clicked.connect(self.accept)
        toolbarLayout.addWidget(self.btnRescan)
        toolbarLayout.addStretch(1)
        toolbarLayout.addWidget(self.btnAssign)
        outerLayout.addLayout(toolbarLayout)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                          | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        outerLayout.addWidget(self.buttonBox)

        self.populateList()
        self.applyTheme(isDarkActive, tokens)

    # Rebuild the vehicle list widget from the catalog's current contents
    def populateList(self):
        self.vehicleList.blockSignals(True)
        self.vehicleList.clear()
        for catalogVehicle in self.catalog.vehicles:
            item = QListWidgetItem(catalogVehicle.vehicleName)
            item.setToolTip(catalogVehicle.fileName)
            self.vehicleList.addItem(item)
        self.vehicleList.blockSignals(False)

        if self.catalog.vehicles:
            self.vehicleList.setCurrentRow(0)
        else:
            self.showEmptyState()

    # Blank every KPI card and the curve when the catalog is empty
    def showEmptyState(self):
        for card in (self.maxSpeedCard, self.massCard, self.lengthCard,
                    self.brakeCard, self.peakForceCard):
            card.setValue(self.lan.get("catalogEmpty", "No vehicles found"))
        self.curveWidget.clearPlot("traction")
        self.selectedVehicleName = None

    # Refresh the KPI cards and the F(v) diagram for the highlighted vehicle
    def onVehicleSelected(self, row):
        if row < 0 or row >= len(self.catalog.vehicles):
            self.showEmptyState()
            return

        catalogVehicle = self.catalog.vehicles[row]
        self.selectedVehicleName = catalogVehicle.vehicleName

        self.maxSpeedCard.setValue(f"{catalogVehicle.maxSpeedKmh:.0f} km/h")
        self.massCard.setValue(f"{catalogVehicle.massTonnes:.1f} t")
        self.lengthCard.setValue(f"{catalogVehicle.lengthM:.1f} m")
        self.brakeCard.setValue(f"{catalogVehicle.brakeDecelMs2:.2f} m/s²")
        self.peakForceCard.setValue(f"{catalogVehicle.peakTractiveForceKN():.1f} kN")
        self.curveWidget.showBands(catalogVehicle.tracBands, catalogVehicle.vehicleName)

    # Reread the vehicles/ folders and rebuild the list
    def rescanCatalog(self):
        self.catalog.scanCatalog()
        self.populateList()

    # The catalog entry currently highlighted, or None when the catalog is empty
    def selectedVehicle(self):
        if self.selectedVehicleName is None:
            return None
        return self.catalog.vehicleByName(self.selectedVehicleName)

    # Restyle the KPI cards and the plot with the active theme's tokens
    def applyTheme(self, isDark, tokens=None):
        self.curveWidget.applyTheme(isDark, tokens)
        for card in (self.maxSpeedCard, self.massCard, self.lengthCard,
                    self.brakeCard, self.peakForceCard):
            card.applyTheme(isDark, tokens)


# Editor for a single vehicle's kinematic and physical parameters
class VehicleTab(QWidget):
    def __init__(self, vData, lan, catalog=None, isDarkActive=False, tokens=None, parent=None):
        super().__init__(parent)
        self.lan = lan
        self.vehicleData = vData
        self.catalog = catalog
        self.isDarkActive = isDarkActive
        self.tokens = tokens
        self.curveWidget = None

        outerLayout = QVBoxLayout(self)
        outerLayout.setContentsMargins(6, 6, 6, 6)
        outerLayout.setSpacing(6)

        paramRows = self.vehicleData.get("trainParam") or default_values.defVal.get("trainParam", [])
        initialName = str(paramRows[0][0]) if paramRows else ""
        initialMass = paramRows[0][2] if paramRows and len(paramRows[0]) > 2 else 0.0
        initialLength = paramRows[0][3] if paramRows and len(paramRows[0]) > 3 else 0.0

        # Dense 3 column grid keeps the common fields visible without scrolling
        gridLayout = QGridLayout()
        gridLayout.setSpacing(4)

        self.comboCatalog = QComboBox()
        self.comboCatalog.addItem(lan.get("manualVehicle", "-- Manual --"), None)
        for vehicleName in (self.catalog.vehicleNames() if self.catalog else []):
            self.comboCatalog.addItem(vehicleName, vehicleName)
        self.comboCatalog.blockSignals(True)
        matchIndex = self.comboCatalog.findData(initialName)
        self.comboCatalog.setCurrentIndex(matchIndex if matchIndex >= 0 else 0)
        self.comboCatalog.blockSignals(False)
        self.comboCatalog.currentIndexChanged.connect(self.onCatalogSelected)

        self.inputVehicleName = QLineEdit(initialName)

        self.inputMaxSpeed = QLineEdit(str(self.vehicleData.get("trainMaxSpeed", 120.0)))
        self.inputMass = QLineEdit(str(initialMass))
        self.inputLength = QLineEdit(str(initialLength))
        self.inputBrakeDecel = QLineEdit(str(self.vehicleData.get(
            "trainBrakeDecel", default_values.defVal.get("trainBrakeDecel", 0.45))))
        self.inputInitialSpeed = QLineEdit(str(self.vehicleData.get("trainInitialSpeed", 0.0)))
        self.inputFinalSpeed = QLineEdit(str(self.vehicleData.get("trainFinalSpeed", 0.0)))

        # The shared profile switcher owns the tier now, only the two per vehicle overrides remain here
        self.comboProfile = QComboBox()
        self.profiles = [
            (lan.get("speedProfileShared", "Follow active speed profile"), None),
            (lan.get("speed_lim_manual", "Manual Speed Limits"), ["manualSpeedLimits", "manualSpeedLimits"]),
            (lan.get("unlimited", "Unlimited"), ["unlimited", "unlimited"])
        ]
        for text, data in self.profiles:
            self.comboProfile.addItem(text, data)
        currentProfile = self.vehicleData.get("speedLimitPlot")
        for index, (text, data) in enumerate(self.profiles):
            if data is not None and data == currentProfile:
                self.comboProfile.setCurrentIndex(index)
                break

        self.inputMaxCantDeficiency = QLineEdit(
            str(self.vehicleData.get("maxCantDeficiencyMm", DEFAULT_MAX_CANT_DEFICIENCY_MM)))
        self.inputMaxCantDeficiency.setToolTip(lan.get(
            "vehicleMaxCantDeficiencyTip",
            "Highest cant deficiency this vehicle is certified for, gating the design speed profiles"))

        gridLayout.addWidget(QLabel(lan.get("catalogVehicleLabel", "Catalog:")), 0, 0)
        gridLayout.addWidget(self.comboCatalog, 0, 1)
        gridLayout.addWidget(QLabel(lan.get("vehicleNameField", "Vehicle name:")), 0, 2)
        gridLayout.addWidget(self.inputVehicleName, 0, 3)

        gridLayout.addWidget(QLabel(lan.get("max_train_speed", "Max Train Speed [km/h]:")), 1, 0)
        gridLayout.addWidget(self.inputMaxSpeed, 1, 1)
        gridLayout.addWidget(QLabel(lan.get("vehicleMass", "Mass [t]:")), 1, 2)
        gridLayout.addWidget(self.inputMass, 1, 3)

        gridLayout.addWidget(QLabel(lan.get("vehicleLengthM", "Length [m]:")), 2, 0)
        gridLayout.addWidget(self.inputLength, 2, 1)
        gridLayout.addWidget(QLabel(lan.get("vehicleBrakeDecel", "Braking Deceleration [m/s2]:")), 2, 2)
        gridLayout.addWidget(self.inputBrakeDecel, 2, 3)

        gridLayout.addWidget(QLabel(lan.get("trainInitialSpeed", "Initial Speed [km/h]:")), 3, 0)
        gridLayout.addWidget(self.inputInitialSpeed, 3, 1)
        gridLayout.addWidget(QLabel(lan.get("trainFinalSpeed", "Final Speed [km/h]:")), 3, 2)
        gridLayout.addWidget(self.inputFinalSpeed, 3, 3)

        gridLayout.addWidget(QLabel(lan.get("vehicleMaxCantDeficiency", "Max cant deficiency I [mm]:")), 4, 0)
        gridLayout.addWidget(self.inputMaxCantDeficiency, 4, 1)

        gridLayout.addWidget(QLabel(lan.get("speed_profile", "Speed Profile:")), 5, 0)
        gridLayout.addWidget(self.comboProfile, 5, 1)

        outerLayout.addLayout(gridLayout)

        toolbarLayoutVehicle = QHBoxLayout()
        self.btnImportVehicle = QPushButton(lan.get("importVehicleCSV", "Import vehicle from CSV"))
        self.btnImportVehicle.clicked.connect(self.importVehicleCSV)
        self.btnExportVehicle = QPushButton(lan.get("exportVehicleCSV", "Export vehicle to CSV"))
        self.btnExportVehicle.clicked.connect(self.exportVehicleCSV)
        toolbarLayoutVehicle.addWidget(self.btnImportVehicle)
        toolbarLayoutVehicle.addWidget(self.btnExportVehicle)
        toolbarLayoutVehicle.addStretch(1)
        outerLayout.addLayout(toolbarLayoutVehicle)

        self.curveSection = CollapsibleSection(
            lan.get("tractiveEffortPlot", "Tractive effort curve F(v)"),
            contentFactory=self.buildCurveWidget)
        outerLayout.addWidget(self.curveSection)

        self.buildAdvancedTables(lan)
        self.advancedSection = CollapsibleSection(lan.get("advancedCoefficients", "Advanced (coefficients)"))
        self.advancedSection.setContentWidget(self.advancedContainer)
        outerLayout.addWidget(self.advancedSection)

        outerLayout.addStretch(1)

    # Build the collapsed by default Res / Trac / Param tables, always present so getSettings can read them
    def buildAdvancedTables(self, lan):
        self.advancedContainer = QWidget()
        containerLayout = QVBoxLayout(self.advancedContainer)
        containerLayout.setContentsMargins(0, 0, 0, 0)
        containerLayout.setSpacing(4)

        containerLayout.addWidget(QLabel(lan["vehicleResistance"]))
        self.tableRes = QTableWidget(0, 4)
        self.tableRes.setHorizontalHeaderLabels([lan["vehicle"], lan["coefA"], lan["coefB"], lan["coefC"]])
        self.tableRes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        containerLayout.addWidget(self.tableRes)
        defaultRes = self.vehicleData.get("trainRes", default_values.defVal.get("trainRes", []))
        self.populateTable(self.tableRes, defaultRes)

        containerLayout.addWidget(QLabel(lan["vehicleTraction"]))
        self.tableTrac = QTableWidget(0, 6)
        self.tableTrac.setHorizontalHeaderLabels([lan["vehicle"], lan["Vbottom"], lan["Vtop"],
                                                  lan["coef_b0"], lan["coef_b1"], lan["coef_b2"]])
        self.tableTrac.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tableTrac.itemChanged.connect(self.onTracTableChanged)
        containerLayout.addWidget(self.tableTrac)
        defaultTrac = self.vehicleData.get("trainTrac", default_values.defVal.get("trainTrac", []))
        self.populateTable(self.tableTrac, defaultTrac)

        containerLayout.addWidget(QLabel(lan["vehicleParam"]))
        self.tableParam = QTableWidget(0, 4)
        self.tableParam.setHorizontalHeaderLabels([lan["vehicle"], lan["rotMass"], lan["weight"],
                                                   lan.get("trainLength", "Train Length [m]")])
        self.tableParam.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        containerLayout.addWidget(self.tableParam)
        defaultParam = self.vehicleData.get("trainParam", default_values.defVal.get("trainParam", []))
        # Ensure older saves have the 4th column, train length, initialized
        for rowData in defaultParam:
            if isinstance(rowData, list) and len(rowData) == 3:
                rowData.append(0.0)
        self.populateTable(self.tableParam, defaultParam)

    def populateTable(self, tableWidget, data):
        tableWidget.setRowCount(len(data))
        for row, rowData in enumerate(data):
            for col, value in enumerate(rowData):
                tableWidget.setItem(row, col, QTableWidgetItem(str(value)))

    # Build the F(v) plot the first time its collapsible section is expanded
    def buildCurveWidget(self):
        self.curveWidget = TractiveCurveWidget(self.lan)
        self.curveWidget.setMinimumHeight(220)
        self.curveWidget.applyTheme(self.isDarkActive, self.tokens)
        self.refreshCurve()
        return self.curveWidget

    # Redraw the F(v) curve from the current traction table contents
    def refreshCurve(self):
        if self.curveWidget is None:
            return
        self.curveWidget.showBands(self.collectTracBands(), self.inputVehicleName.text().strip())

    # Read the traction bands currently held in the Advanced table
    def collectTracBands(self):
        bands = []
        for row in range(self.tableTrac.rowCount()):
            try:
                bands.append([
                    float(self.tableTrac.item(row, 1).text()),
                    float(self.tableTrac.item(row, 2).text()),
                    float(self.tableTrac.item(row, 3).text()),
                    float(self.tableTrac.item(row, 4).text()),
                    float(self.tableTrac.item(row, 5).text()),
                ])
            except (ValueError, AttributeError):
                continue
        return bands

    # Coalesce rapid successive table edits into a single curve redraw
    def onTracTableChanged(self, item=None):
        QTimer.singleShot(0, self.refreshCurve)

    # Apply the catalog vehicle picked from the combo box
    def onCatalogSelected(self, index):
        vehicleName = self.comboCatalog.itemData(index)
        if not vehicleName or self.catalog is None:
            return
        catalogVehicle = self.catalog.vehicleByName(vehicleName)
        if catalogVehicle is not None:
            self.applyCatalogVehicle(catalogVehicle)

    # Populate every field and table from a catalog vehicle
    def applyCatalogVehicle(self, catalogVehicle):
        settings = catalogVehicle.toVehicleSettings()

        self.inputVehicleName.setText(catalogVehicle.vehicleName)
        self.inputMaxSpeed.setText(f"{catalogVehicle.maxSpeedKmh:g}")
        self.inputBrakeDecel.setText(f"{catalogVehicle.brakeDecelMs2:g}")
        self.inputMass.setText(f"{catalogVehicle.massTonnes:g}")
        self.inputLength.setText(f"{catalogVehicle.lengthM:g}")
        self.inputMaxCantDeficiency.setText(f"{catalogVehicle.maxCantDeficiencyMm:g}")

        self.populateTable(self.tableRes, settings["trainRes"])
        self.populateTable(self.tableTrac, settings["trainTrac"])
        self.populateTable(self.tableParam, settings["trainParam"])

        self.refreshCurve()

    # Import an extended or legacy vehicle CSV and apply it to this tab
    def importVehicleCSV(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, self.lan.get("importVehicleCSV", "Import vehicle from CSV"), "", "CSV Files (*.csv)")
        if not filepath:
            return

        fileContent = readfile.ReadFile().Read(filepath)
        if not isinstance(fileContent, str) or fileContent.startswith("Error"):
            QMessageBox.critical(self, self.lan.get("error", "Error"), str(fileContent))
            return

        try:
            catalogVehicle = VehicleCatalog().parseCsvText(fileContent, Path(filepath).name)
        except (csv.Error, ValueError) as importError:
            QMessageBox.critical(self, self.lan.get("error", "Error"), str(importError))
            return

        self.applyCatalogVehicle(catalogVehicle)

        # A vehicle imported from a stray file is not one of the catalog entries
        self.comboCatalog.blockSignals(True)
        self.comboCatalog.setCurrentIndex(0)
        self.comboCatalog.blockSignals(False)

    # Export this tab's current settings as an extended vehicle CSV
    def exportVehicleCSV(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, self.lan.get("exportVehicleCSV", "Export vehicle to CSV"), "", "CSV Files (*.csv)")
        if not filepath:
            return

        try:
            csvText = VehicleCatalog().serialiseVehicle(
                self.getSettings(), self.inputVehicleName.text().strip())
            with open(filepath, "w", encoding="utf-8", newline="") as fileHandle:
                fileHandle.write(csvText)
        except OSError as exportError:
            QMessageBox.critical(self, self.lan.get("error", "Error"), str(exportError))

    # Collect every field into the settings dictionary the simulation engine expects
    def getSettings(self):
        vehicleName = self.inputVehicleName.text().strip() or "Vehicle"

        settingsData = {
            "trainRes": [],
            "trainTrac": [],
            "trainParam": [],
            # The travel direction belongs to the run, so the ribbon toggle owns it and this preserves it
            "runReversed": bool(self.vehicleData.get("runReversed", False)),
        }

        # A None entry means this vehicle follows the shared tier, so it carries no pinned profile
        overrideProfile = self.comboProfile.currentData()
        if overrideProfile is not None:
            settingsData["speedLimitPlot"] = list(overrideProfile)

        try:
            settingsData["maxCantDeficiencyMm"] = float(self.inputMaxCantDeficiency.text())
        except ValueError:
            settingsData["maxCantDeficiencyMm"] = DEFAULT_MAX_CANT_DEFICIENCY_MM

        try:
            settingsData["trainMaxSpeed"] = float(self.inputMaxSpeed.text())
        except ValueError:
            pass
        try:
            settingsData["trainInitialSpeed"] = float(self.inputInitialSpeed.text())
        except ValueError:
            pass
        try:
            settingsData["trainFinalSpeed"] = float(self.inputFinalSpeed.text())
        except ValueError:
            pass
        try:
            settingsData["trainBrakeDecel"] = float(self.inputBrakeDecel.text())
        except ValueError:
            pass

        rotMassItem = self.tableParam.item(0, 1) if self.tableParam.rowCount() > 0 else None
        rotMassFactor = toFloat(rotMassItem.text() if rotMassItem else None, DEFAULT_ROT_MASS_FACTOR)
        massTonnes = toFloat(self.inputMass.text(), 0.0)
        lengthM = toFloat(self.inputLength.text(), 0.0)
        settingsData["trainParam"] = [[vehicleName, rotMassFactor, massTonnes, lengthM]]

        for row in range(self.tableRes.rowCount()):
            try:
                settingsData["trainRes"].append([
                    vehicleName,
                    float(self.tableRes.item(row, 1).text()),
                    float(self.tableRes.item(row, 2).text()),
                    float(self.tableRes.item(row, 3).text())
                ])
            except (ValueError, AttributeError):
                continue

        for row in range(self.tableTrac.rowCount()):
            try:
                settingsData["trainTrac"].append([
                    vehicleName,
                    float(self.tableTrac.item(row, 1).text()),
                    float(self.tableTrac.item(row, 2).text()),
                    float(self.tableTrac.item(row, 3).text()),
                    float(self.tableTrac.item(row, 4).text()),
                    float(self.tableTrac.item(row, 5).text())
                ])
            except (ValueError, AttributeError):
                continue

        return settingsData

    # Propagate a theme change to the F(v) plot, when it has been built
    def applyTheme(self, isDark, tokens=None):
        self.isDarkActive = isDark
        self.tokens = tokens
        if self.curveWidget is not None:
            self.curveWidget.applyTheme(isDark, tokens)


# Dialog hosting 1 to MAX_VEHICLES vehicle tabs, adaptive to the active count
class VehicleSettingsDialog(QDialog):
    def __init__(self, settingsData, lan, catalog=None, isDarkActive=False, tokens=None, parent=None):
        super().__init__(parent)
        self.lan = lan
        self.settingsData = settingsData
        self.catalog = catalog
        self.isDarkActive = isDarkActive
        self.tokens = tokens

        self.setWindowTitle(lan.get("vehicleSettings", "Vehicle Settings"))
        self.setMinimumSize(680, 560)

        layout = QVBoxLayout(self)

        headerLayout = QHBoxLayout()
        headerLayout.addWidget(QLabel(lan.get("vehicleCount", "Number of vehicles:")))
        self.countSpin = QSpinBox()
        self.countSpin.setRange(1, MAX_VEHICLES)
        headerLayout.addWidget(self.countSpin)
        headerLayout.addStretch(1)
        self.btnBrowseCatalog = QPushButton(lan.get("browseCatalog", "Browse catalog..."))
        self.btnBrowseCatalog.clicked.connect(self.browseCatalog)
        headerLayout.addWidget(self.btnBrowseCatalog)
        layout.addLayout(headerLayout)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        vehicles = self.settingsData.get("vehicles", [])
        if not vehicles:
            # Migrate a pre vehicle list save into a single vehicle tab
            oldV = {
                "trainInitialSpeed": self.settingsData.get("trainInitialSpeed", 0.0),
                "trainFinalSpeed": self.settingsData.get("trainFinalSpeed", 0.0),
                "trainMaxSpeed": self.settingsData.get("trainMaxSpeed", self.settingsData.get("vInit", [120])[0]),
                "trainBrakeDecel": self.settingsData.get("trainBrakeDecel",
                                                          default_values.defVal.get("trainBrakeDecel", 0.45)),
                "trainRes": self.settingsData.get("trainRes", default_values.defVal.get("trainRes", [])),
                "trainTrac": self.settingsData.get("trainTrac", default_values.defVal.get("trainTrac", [])),
                "trainParam": self.settingsData.get("trainParam", default_values.defVal.get("trainParam", [])),
                "maxCantDeficiencyMm": self.settingsData.get("maxCantDeficiencyMm",
                                                              DEFAULT_MAX_CANT_DEFICIENCY_MM),
                "runReversed": self.settingsData.get("runReversed", False)
            }
            vehicles.append(oldV)

        for vData in vehicles:
            self.addTab(vData)

        self.countSpin.blockSignals(True)
        self.countSpin.setValue(self.tabs.count())
        self.countSpin.blockSignals(False)
        self.countSpin.valueChanged.connect(self.onCountChanged)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                          | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    # Append one vehicle tab built from the given settings dictionary
    def addTab(self, vData):
        tab = VehicleTab(vData, self.lan, catalog=self.catalog,
                         isDarkActive=self.isDarkActive, tokens=self.tokens)
        self.tabs.addTab(tab, f'{self.lan.get("vehicle", "Vehicle")} {self.tabs.count() + 1}')

    # Grow or shrink the tab set to match the spin box, keeping surviving tabs intact
    def onCountChanged(self, newCount):
        currentCount = self.tabs.count()

        if newCount > currentCount:
            for _ in range(newCount - currentCount):
                lastTab = self.tabs.widget(self.tabs.count() - 1) if self.tabs.count() > 0 else None
                self.addTab(lastTab.getSettings() if lastTab is not None else {})
        elif newCount < currentCount:
            for _ in range(currentCount - newCount):
                self.tabs.removeTab(self.tabs.count() - 1)

        self.retitleTabs()

    # Renumber every tab caption after the active count changes
    def retitleTabs(self):
        for index in range(self.tabs.count()):
            self.tabs.setTabText(index, f'{self.lan.get("vehicle", "Vehicle")} {index + 1}')

    # Open the catalog browser and apply the chosen vehicle to the active tab
    def browseCatalog(self):
        if self.catalog is None:
            return

        dialog = VehicleCatalogDialog(self.catalog, self.lan, isDarkActive=self.isDarkActive,
                                      tokens=self.tokens, parent=self)
        if not dialog.exec():
            return

        catalogVehicle = dialog.selectedVehicle()
        currentTab = self.tabs.currentWidget()
        if catalogVehicle is None or currentTab is None:
            return

        currentTab.applyCatalogVehicle(catalogVehicle)
        matchIndex = currentTab.comboCatalog.findData(catalogVehicle.vehicleName)
        if matchIndex >= 0:
            currentTab.comboCatalog.blockSignals(True)
            currentTab.comboCatalog.setCurrentIndex(matchIndex)
            currentTab.comboCatalog.blockSignals(False)

    # Collect the settings of every active tab
    def getSettings(self):
        vehicles = [self.tabs.widget(index).getSettings() for index in range(self.tabs.count())]
        return {"vehicles": vehicles}

    # Propagate a theme change to every built F(v) plot
    def applyTheme(self, isDark, tokens=None):
        self.isDarkActive = isDark
        self.tokens = tokens
        for index in range(self.tabs.count()):
            self.tabs.widget(index).applyTheme(isDark, tokens)
