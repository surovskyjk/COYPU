from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QDialogButtonBox, QCheckBox, QLabel,
                               QListWidget, QListWidgetItem, QFormLayout,
                               QLineEdit, QTableWidget, QTableWidgetItem,
                               QHeaderView, QFileDialog, QMessageBox,
                               QDialogButtonBox, QPushButton, QComboBox,
                               QDoubleSpinBox, QSlider, QSpinBox, QWidget)
from PySide6.QtCore import Qt

import numpy as np
import pyqtgraph as pg

import basemap_key
import plot_widgets

import csv
import readfile
import io
import default_values
import geometry_engine

# Extra headroom around a symmetric popup axis, replaces the old setYRange padding argument
POPUP_RANGE_HEADROOM = 1.05

# The radius ceiling bounds belong to the engine, the dialog and the batch table share them
R_MAX_MINIMUM_M = geometry_engine.R_MAX_MINIMUM_M
R_MAX_MAXIMUM_M = geometry_engine.R_MAX_MAXIMUM_M

class TTPSelectSectionDialog(QDialog):
    def __init__(self, sections, HasLandXML, lan, parent=None):
        super().__init__(parent)

        # Set up the dialog layout
        self.setWindowTitle(lan["select_sections_for_ttp_title"])
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        layout = QVBoxLayout()

        # Load all checkbox
        self.loadAllCheckBox = QCheckBox(lan["load_all"])
        self.loadAllCheckBox.setChecked(False)
        self.loadAllCheckBox.toggled.connect(self.toggleListWidget)
        layout.addWidget(self.loadAllCheckBox)

        # Sections selector - list widget
        layout.addWidget(QLabel(lan["select_sections_for_ttp_description"]))
        self.listWidget = QListWidget()
        self.listWidget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # Populate the list widget with sections
        for id, section in enumerate(sections):
            item = QListWidgetItem(section)
            item.setData(Qt.ItemDataRole.UserRole, id)
            self.listWidget.addItem(item)
        layout.addWidget(self.listWidget)
        
        # Crop the sections if LandXML data is available and successfully loaded
        self.LandXMLCheckBox = QCheckBox(lan["crop_to_landxml"])
        if not HasLandXML:
            self.LandXMLCheckBox.setEnabled(False)
            self.LandXMLCheckBox.setChecked(False)
        layout.addWidget(self.LandXMLCheckBox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def toggleListWidget(self, checked):
        self.listWidget.setEnabled(not checked)

    def getSelectedSection(self):
        selected = self.listWidget.selectedItems()
        selectedIds = [item.data(Qt.ItemDataRole.UserRole) for item in selected]
        
        return selectedIds, self.LandXMLCheckBox.isChecked(), self.loadAllCheckBox.isChecked()

class AlignmentSelectDialog(QDialog):
    def __init__(self, alignments, lan, parent=None):
        super().__init__(parent)
        self.setWindowTitle(lan.get("select_alignment_title", "Select Alignment"))
        self.setMinimumWidth(300)
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel(lan.get("select_alignment_description", "Select the alignment to load:")))
        
        self.listWidget = QListWidget()
        self.listWidget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        
        for id, aligName in enumerate(alignments):
            item = QListWidgetItem(f"{aligName}")
            item.setData(Qt.ItemDataRole.UserRole, id)
            self.listWidget.addItem(item)
            
        if self.listWidget.count() > 0:
            self.listWidget.setCurrentRow(0)
            
        layout.addWidget(self.listWidget)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        
    def getSelectedIndex(self):
        selected = self.listWidget.selectedItems()
        if selected:
            return selected[0].data(Qt.ItemDataRole.UserRole)
        return 0

class MapSettingsDialog(QDialog):
    def __init__(self, currentEPSG, currentMap, currentDrawMode, currentSpeedProfile, lan,
                 parent=None, basemapApiKey=""):
        super().__init__(parent)
        self.lan = lan
        self.setWindowTitle(lan["mapSettings"])

        layout = QVBoxLayout(self)
        formLayout = QFormLayout()

        displayValue = currentEPSG
        self.inputEPSG = QLineEdit(displayValue)
        formLayout.addRow(QLabel(lan["currentEPSG"]), self.inputEPSG)
        
        self.comboMap = QComboBox()
        self.comboMap.addItem(lan.get("mapPositron", "CartoDB Positron"), "positron")
        self.comboMap.addItem(lan.get("mapOSM", "OpenStreetMap"), "osm")
        self.comboMap.addItem(lan.get("mapORM", "OpenRailwayMap"), "orm")
        self.comboMap.addItem(lan.get("mapCUZK", "ČÚZK Ortofoto"), "cuzk")
        self.comboMap.addItem(lan.get("mapCartoDark", "CartoDB Dark"), "cartodbDark")
        index = self.comboMap.findData(currentMap)
        if index >= 0: self.comboMap.setCurrentIndex(index)
        formLayout.addRow(QLabel(lan.get("mapBase", "Map Base:")), self.comboMap)

        self.comboDrawMode = QComboBox()
        self.comboDrawMode.addItem(lan.get("mapDrawSingleColor", "Single Color"), "single")
        self.comboDrawMode.addItem(lan.get("mapDrawByType", "By Element Type"), "type")
        self.comboDrawMode.addItem(lan.get("mapDrawBySpeed", "By Speed Limit"), "speed")
        index = self.comboDrawMode.findData(currentDrawMode)
        if index >= 0: self.comboDrawMode.setCurrentIndex(index)
        formLayout.addRow(QLabel(lan.get("mapDrawMode", "Draw Mode:")), self.comboDrawMode)

        self.labelSpeedProfile = QLabel(lan.get("mapSpeedProfile", "Speed Profile for Map:"))
        self.comboSpeedProfile = QComboBox()
        self.profiles = [
            ("TTP", "TTP"),
            ("V100", "100"), ("V130", "130"), ("V150", "150"), ("VK", "K"),
        ]
        for text, data in self.profiles:
            self.comboSpeedProfile.addItem(text, data)
        index = self.comboSpeedProfile.findData(currentSpeedProfile)
        if index >= 0: self.comboSpeedProfile.setCurrentIndex(index)
        formLayout.addRow(self.labelSpeedProfile, self.comboSpeedProfile)
        
        # Masked, kept in the credential vault by the caller, never in a project or in the source
        self.apiKeyInput = QLineEdit(str(basemapApiKey or ""))
        self.apiKeyInput.setEchoMode(QLineEdit.EchoMode.Password)
        self.apiKeyInput.setToolTip(lan.get(
            "mapApiKeyTip",
            "Needed for the CARTO basemaps, leave empty to use OpenStreetMap"))
        formLayout.addRow(QLabel(lan.get("mapApiKeyLabel", "CARTO API key:")),
                          self.apiKeyInput)

        # Where a key comes from, either the author on request or a free one of the user's own
        self.apiKeyHelp = QLabel(lan.get(
            "mapApiKeyHelp",
            "CARTO basemaps need an API key. You can ask the author of COYPU for one via GitHub "
            "({authorLink}), or get your own free key at {cartoLink}. The key is stored encrypted "
            "for your Windows account and is never saved in project files. Leave the field empty "
            "to use OpenStreetMap.").format(
                authorLink=self.linkHtml(basemap_key.AUTHOR_CONTACT_URL),
                cartoLink=self.linkHtml(basemap_key.CARTO_KEY_SIGNUP_URL)))
        self.apiKeyHelp.setWordWrap(True)
        self.apiKeyHelp.setTextFormat(Qt.TextFormat.RichText)
        self.apiKeyHelp.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.apiKeyHelp.setOpenExternalLinks(True)
        formLayout.addRow(self.apiKeyHelp)

        self.comboDrawMode.currentTextChanged.connect(self.updateSpeedProfileVisibility)
        self.updateSpeedProfileVisibility()

        layout.addLayout(formLayout)
        label = QLabel(lan["EPSGinfo"])
        layout.addWidget(label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def updateSpeedProfileVisibility(self):
        isSpeedMode = self.comboDrawMode.currentData() == "speed"
        self.labelSpeedProfile.setVisible(isSpeedMode)
        self.comboSpeedProfile.setVisible(isSpeedMode)

    # Clickable link showing the address without its scheme
    def linkHtml(self, url):
        caption = url.split("://", 1)[-1].rstrip("/")
        return f'<a href="{url}">{caption}</a>'

    # Whatever the user typed into the optional key field, stripped
    def getBasemapApiKey(self):
        return self.apiKeyInput.text().strip()

    def getMapSettings(self):
        epsg = self.inputEPSG.text().strip().upper()

        if not epsg.startswith("EPSG:"):
            epsg = f"EPSG:{epsg}"
            
        return epsg, self.comboMap.currentData(), self.comboDrawMode.currentData(), self.comboSpeedProfile.currentData()
        
class GeometrySettingsDialog(QDialog):
    def __init__(self, settingsData, lan, parent=None):
        super().__init__(parent)
        self.settingsData = settingsData

        self.setWindowTitle(lan["geometrySettings"])
        self.setMinimumSize(600,400)

        layout = QVBoxLayout(self)

        formLayout = QFormLayout()
        currentMaxD = self.settingsData.get("maxD", 150.0)
        if isinstance(currentMaxD, list):
            currentMaxD = currentMaxD[0]
            
        self.inputMaxD = QLineEdit(str(currentMaxD))
        formLayout.addRow(QLabel(lan.get("maxCant", "Maximum cant D_max [mm]:")), self.inputMaxD)
        
        currentVInit = self.settingsData.get("vInit", [120.0])
        if isinstance(currentVInit, list): currentVInit = currentVInit[0]
        self.inputVInit = QLineEdit(str(currentVInit))
        formLayout.addRow(QLabel(lan.get("vInitLabel", "Initial Speed v_init [km/h]:")), self.inputVInit)

        currentIterStep = self.settingsData.get("iterationStep", 5.0)
        self.inputIterStep = QLineEdit(str(currentIterStep))
        formLayout.addRow(QLabel(lan.get("iterationStepLabel", "Iteration speed reduction step [km/h]:")), self.inputIterStep)

        currentMaxIter = self.settingsData.get("maxIterations", 50)
        self.inputMaxIter = QLineEdit(str(currentMaxIter))
        formLayout.addRow(QLabel(lan.get("maxIterationsLabel", "Maximum number of iterations [-]:")), self.inputMaxIter)

        layout.addLayout(formLayout)

        labelI = QLabel(lan["cant_def"])
        layout.addWidget(labelI)
        
        # Table for editing settings and thresholds for cant deficiency
        self.tableI = QTableWidget(0, 5)
        self.tableI.setHorizontalHeaderLabels([
            lan["Vbottom"],
            lan["Vtop"],
            lan["I_std"],
            lan["I_lim"],
            lan["I_max"]
        ])

        headerI = self.tableI.horizontalHeader()
        headerI.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tableI)

        # Default values for I according to the Czech standard
        defaultCZI = self.settingsData.get("I", default_values.defVal["I"])

        self.populateTable(self.tableI, defaultCZI)

        # Table for editing settings and thresholds for abrupt change of cant deficiency
        labelDI = QLabel(lan["abrupt_cant_def"])
        layout.addWidget(labelDI)

        self.tableDI = QTableWidget(0, 5)
        self.tableDI.setHorizontalHeaderLabels([
            lan["Vbottom"],
            lan["Vtop"],
            lan["dI_std"],
            lan["dI_lim"],
            lan["dI_max"]
        ])

        headerDI = self.tableDI.horizontalHeader()
        headerDI.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tableDI)

        # Default values for dI according to the Czech standard
        defaultCZDI = self.settingsData.get("dI", default_values.defVal["dI"])

        self.populateTable(self.tableDI, defaultCZDI)

        # Table for editing settings and thresholds for cant ramp gradient
        labelNlin = QLabel(lan["nLin"])
        layout.addWidget(labelNlin)

        self.tableNlin = QTableWidget(0, 8)
        self.tableNlin.setHorizontalHeaderLabels([
            lan["Vbottom"],
            lan["Vtop"],
            lan["n_n"],
            lan["n_n_abs"],
            lan["n_lim"],
            lan["n_lim_abs"],
            lan["n_min"],
            lan["n_min_abs"]
        ])

        headerNlin = self.tableNlin.horizontalHeader()
        headerNlin.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tableNlin)

        # Default values for nLin according to the Czech standard
        defaultCZnLin = self.settingsData.get("nLin", default_values.defVal["nLin"])

        self.populateTable(self.tableNlin, defaultCZnLin)

        # Table for editing settings and thresholds for cant deficiency gradient
        labelNIlin = QLabel(lan["nILin"])
        layout.addWidget(labelNIlin)

        self.tableNIlin = QTableWidget(0, 5)
        self.tableNIlin.setHorizontalHeaderLabels([
            lan["Vbottom"],
            lan["Vtop"],
            lan["nI_n"],
            lan["nI_lim"],
            lan["nI_min"],
        ])

        headerNIlin = self.tableNIlin.horizontalHeader()
        headerNIlin.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tableNIlin)

        # Default values for nILin according to the Czech standard
        defaultCZnILin = self.settingsData.get("nILin", default_values.defVal["nILin"])

        self.populateTable(self.tableNIlin, defaultCZnILin)

        toolbarLayoutGeometry = QHBoxLayout()
        
        self.btnImportGeometry = QPushButton(lan["importCSV"])
        self.btnImportGeometry.clicked.connect(self.importGeometryCSV)
        toolbarLayoutGeometry.addWidget(self.btnImportGeometry)
        
        self.btnExportGeometry = QPushButton(lan["exportCSV"])
        self.btnExportGeometry.clicked.connect(self.exportGeometryCSV)
        toolbarLayoutGeometry.addWidget(self.btnExportGeometry)
        
        layout.addLayout(toolbarLayoutGeometry)

        # Buttons for the whole dialog
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def populateTable(self, tableWidget, data):
        tableWidget.setRowCount(len(data))
        for row, rowData in enumerate(data):
            for col, value in enumerate(rowData):
                item = QTableWidgetItem(str(value))
                tableWidget.setItem(row, col, item)

    def importGeometryCSV(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "CSV Files (*.csv)")
        
        # If cancelled, do nothing
        if not filepath:
            return
        
        # Read file content 
        fileContent = readfile.ReadFile().Read(filepath)
        
        if fileContent.startswith("Error"):
            err = QMessageBox()
            err.setWindowTitle("Error")
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()
            return
        
        try:
            # Reads CSV file content
            reader = csv.reader(io.StringIO(fileContent), delimiter=',')
            # Skips header
            next(reader, None)

            iData = []
            diData = []
            nlinData = []
            nilinData = []

            for row in reader:
                if not row:
                    continue
                section = row[0]
                if section == "I" and len(row) >= 6:
                    iData.append(row[1:6])
                elif section == "DI" and len(row) >= 6:
                    diData.append(row[1:6])
                elif section == "nLin" and len(row) >= 9:
                    nlinData.append(row[1:9])
                elif section == "nILin" and len(row) >= 6:
                    nilinData.append(row[1:6])

            if iData: self.populateTable(self.tableI, iData)
            if diData: self.populateTable(self.tableDI, diData)
            if nlinData: self.populateTable(self.tableNlin, nlinData)
            if nilinData: self.populateTable(self.tableNIlin, nilinData)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        
    def exportGeometryCSV(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File", "", "CSV Files (*.csv)")
        
        # If cancelled, do nothing
        if not filepath:
            return
        
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                headers = ["Section", "Col1", "Col2", "Col3", "Col4", "Col5", "Col6", "Col7", "Col8"]
                writer.writerow(headers)

                for row in range(self.tableI.rowCount()):
                    rowData = ["I"] + [self.tableI.item(row, col).text() if self.tableI.item(row, col) else "" for col in range(self.tableI.columnCount())]
                    writer.writerow(rowData)

                for row in range(self.tableDI.rowCount()):
                    rowData = ["DI"] + [self.tableDI.item(row, col).text() if self.tableDI.item(row, col) else "" for col in range(self.tableDI.columnCount())]
                    writer.writerow(rowData)

                for row in range(self.tableNlin.rowCount()):
                    rowData = ["nLin"] + [self.tableNlin.item(row, col).text() if self.tableNlin.item(row, col) else "" for col in range(self.tableNlin.columnCount())]
                    writer.writerow(rowData)

                for row in range(self.tableNIlin.rowCount()):
                    rowData = ["nILin"] + [self.tableNIlin.item(row, col).text() if self.tableNIlin.item(row, col) else "" for col in range(self.tableNIlin.columnCount())]
                    writer.writerow(rowData)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        
    def getSettings(self):
        settingsData = {
            "I": [],
            "dI": [],
            "nLin": [],
            "nILin": [],
        }

        try:
            settingsData["maxD"] = float(self.inputMaxD.text())
        except ValueError:
            settingsData["maxD"] = 150.0
            
        try:
            settingsData["vInit"] = [float(self.inputVInit.text())]
        except ValueError:
            settingsData["vInit"] = [120.0]

        try:
            settingsData["iterationStep"] = max(0.1, float(self.inputIterStep.text()))
        except ValueError:
            settingsData["iterationStep"] = 5.0

        try:
            settingsData["maxIterations"] = max(1, int(self.inputMaxIter.text()))
        except ValueError:
            settingsData["maxIterations"] = 50

        # Table I
        for row in range(self.tableI.rowCount()):
            try:
                settingsData["I"].append([
                    float(self.tableI.item(row, 0).text()),
                    float(self.tableI.item(row, 1).text()),
                    float(self.tableI.item(row, 2).text()),
                    float(self.tableI.item(row, 3).text()),
                    float(self.tableI.item(row, 4).text())
                ])

            except(ValueError, AttributeError):
                continue
        
        # Table dI
        for row in range(self.tableDI.rowCount()):
            try:
                settingsData["dI"].append([
                    float(self.tableDI.item(row, 0).text()),
                    float(self.tableDI.item(row, 1).text()),
                    float(self.tableDI.item(row, 2).text()),
                    float(self.tableDI.item(row, 3).text()),
                    float(self.tableDI.item(row, 4).text())
                ])

            except(ValueError, AttributeError):
                continue

        # Table nLin
        for row in range(self.tableNlin.rowCount()):
            try:
                settingsData["nLin"].append([
                    float(self.tableNlin.item(row, 0).text()),
                    float(self.tableNlin.item(row, 1).text()),
                    float(self.tableNlin.item(row, 2).text()),
                    float(self.tableNlin.item(row, 3).text()),
                    float(self.tableNlin.item(row, 4).text()),
                    float(self.tableNlin.item(row, 5).text()),
                    float(self.tableNlin.item(row, 6).text()),
                    float(self.tableNlin.item(row, 7).text())
                ])

            except(ValueError, AttributeError):
                continue
        
        # Table nILin
        for row in range(self.tableNIlin.rowCount()):
            try:
                settingsData["nILin"].append([
                    float(self.tableNIlin.item(row, 0).text()),
                    float(self.tableNIlin.item(row, 1).text()),
                    float(self.tableNIlin.item(row, 2).text()),
                    float(self.tableNIlin.item(row, 3).text()),
                    float(self.tableNIlin.item(row, 4).text()),
                ])

            except(ValueError, AttributeError):
                continue

        return settingsData
    
class DesignApproachDialog(QDialog):
    def __init__(self, settingsData, lan, parent=None):
        super().__init__(parent)
        self.lan = lan
        self.settingsData = settingsData
        
        self.setWindowTitle(lan["designApproach"])

        layout = QVBoxLayout(self)
        labelLimit = QLabel(lan["designApproachLimitDescription"])
        layout.addWidget(labelLimit)

        formLayout = QFormLayout()

        self.designApproach = self.settingsData.get("designApproach", {})
        if isinstance(self.designApproach, str):
            self.designApproach = {
                "I": self.designApproach,
                "dI": self.designApproach,
                "nLin": self.designApproach,
                "nILin": self.designApproach
            }

        self.comboboxes = {}
        parameters = [
            ("I", lan.get("cant_def", "cant deficiency I [mm]")),
            ("dI", lan.get("abrupt_cant_def", "abrupt change of cant deficiency deltaI [mm]")),
            ("nLin", lan.get("nLin", "cant ramp gradient n [-]")),
            ("nILin", lan.get("nILin", "Coefficient of cant deficiency change nI [-]"))
        ]

        for paramKey, paramLabel in parameters:
            cb = QComboBox(self)
            cb.addItems([lan["standard"], lan["limit"], lan["minmax"]])
            
            currentVal = self.designApproach.get(paramKey, "standard")
            if currentVal == "standard":
                cb.setCurrentText(lan["standard"])
            elif currentVal == "limit":
                cb.setCurrentText(lan["limit"])
            elif currentVal == "minmax":
                cb.setCurrentText(lan["minmax"])
                
            self.comboboxes[paramKey] = cb
            formLayout.addRow(QLabel(paramLabel), cb)
            
        layout.addLayout(formLayout)

        # Extra empirical/geometric options layered on top of the standard approach columns
        self.checkDisableGeometryMaxD = QCheckBox(lan.get("designApproachDisableRadiusCant", "Disable empirical cant radius limit D <= (R-50)/1.5"))
        self.checkDisableGeometryMaxD.setChecked(bool(self.settingsData.get("disableGeometryMaxD", False)))
        layout.addWidget(self.checkDisableGeometryMaxD)

        self.checkBalanceInflectionCants = QCheckBox(lan.get("designApproachBalanceInflections", "Balance cant at inflection points (L1/L2 = D1/D2)"))
        self.checkBalanceInflectionCants.setChecked(bool(self.settingsData.get("balanceInflectionCants", False)))
        layout.addWidget(self.checkBalanceInflectionCants)

        # Buttons for the whole dialog
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def getDesignApproach(self):
        result = {}
        for paramKey, cb in self.comboboxes.items():
            selected = cb.currentText()
            if selected == self.lan["standard"]:
                result[paramKey] = "standard"
            elif selected == self.lan["limit"]:
                result[paramKey] = "limit"
            elif selected == self.lan["minmax"]:
                result[paramKey] = "minmax"
            else:
                result[paramKey] = "standard"
        return result

    def isGeometryMaxDDisabled(self):
        return self.checkDisableGeometryMaxD.isChecked()

    def isInflectionBalancingEnabled(self):
        return self.checkBalanceInflectionCants.isChecked()

class AlignmentOptimizationDialog(QDialog):
    def __init__(self, settingsData, lan, parent=None):
        super().__init__(parent)
        self.lan = lan or {}
        self.settingsData = settingsData
        config = settingsData.get("alignmentOptimization", {}) if isinstance(settingsData, dict) else {}

        self.setWindowTitle(self.lan.get("alignmentOptimization", "Alignment Optimization"))

        layout = QVBoxLayout(self)
        formLayout = QFormLayout()

        self.dMaxInput = QLineEdit(str(config.get("dMaxM", 0.5)))
        formLayout.addRow(QLabel(self.lan.get("optDMaxLabel", "Maximum lateral shift d_max [m]:")), self.dMaxInput)

        self.lMinInput = QLineEdit(str(config.get("lMinM", 25.0)))
        formLayout.addRow(QLabel(self.lan.get("optLMinLabel", "Minimum element length L_min [m]:")), self.lMinInput)

        self.lkMaxInput = QLineEdit(str(config.get("lkMaxM", geometry_engine.DEFAULT_LK_MAX_M)))
        formLayout.addRow(QLabel(self.lan.get("optLkMaxLabel", "Maximum transition length L_k,max [m]:")), self.lkMaxInput)

        # The radius ceiling is optional, so the value only becomes editable once it is switched on
        self.rMaxEnableCheck = QCheckBox(self.lan.get("optRMaxEnable", "Limit the maximum curve radius"))
        self.rMaxEnableCheck.setChecked(bool(config.get("isRMaxEnabled", False)))
        self.rMaxInput = QDoubleSpinBox()
        self.rMaxInput.setRange(R_MAX_MINIMUM_M, R_MAX_MAXIMUM_M)
        self.rMaxInput.setDecimals(0)
        self.rMaxInput.setSingleStep(100.0)
        self.rMaxInput.setSuffix(" " + self.lan.get("unitM", "m"))
        self.rMaxInput.setValue(float(config.get("rMaxM", geometry_engine.DEFAULT_R_MAX_M)))
        self.rMaxInput.setEnabled(self.rMaxEnableCheck.isChecked())
        self.rMaxEnableCheck.toggled.connect(self.rMaxInput.setEnabled)
        formLayout.addRow(self.rMaxEnableCheck, self.rMaxInput)

        layout.addLayout(formLayout)
        layout.addWidget(QLabel(self.lan.get("optPatternsLabel", "Pattern optimization modes")))

        patternFormLayout = QFormLayout()
        # An L-C-L group carries no transitions, so only the arc shift is offered for it
        self.comboModeLcl = QComboBox(self)
        self.comboModeLcl.addItem(self.lan.get("optModeNone", "Do not optimize"), geometry_engine.OPTIMIZATION_MODE_NONE)
        self.comboModeLcl.addItem(self.lan.get("optModeShiftArc", "3 - Enlarge radius only (C)"), geometry_engine.OPTIMIZATION_MODE_SHIFT_ARC)
        self.comboModeLcl.setToolTip(self.lan.get("optPatternLclTip",
                                                  "Line-Curve-Line has no transition curves, so only the radius can be enlarged"))
        self.setComboCurrentData(self.comboModeLcl, config.get("modeLcl", geometry_engine.OPTIMIZATION_MODE_NONE))
        patternFormLayout.addRow(QLabel(self.lan.get("optPatternLcl", "Line-Curve-Line")), self.comboModeLcl)

        self.comboModeLscsl = QComboBox(self)
        self.comboModeLscsl.addItem(self.lan.get("optModeNone", "Do not optimize"), geometry_engine.OPTIMIZATION_MODE_NONE)
        self.comboModeLscsl.addItem(self.lan.get("optModeShiftAndExtend", "1 - Shift arc and extend transitions (C+S)"), geometry_engine.OPTIMIZATION_MODE_SHIFT_AND_EXTEND)
        self.comboModeLscsl.addItem(self.lan.get("optModeExtendSpirals", "2 - Extend transitions only (S)"), geometry_engine.OPTIMIZATION_MODE_EXTEND_SPIRALS)
        self.comboModeLscsl.addItem(self.lan.get("optModeShiftArc", "3 - Enlarge radius only (C)"), geometry_engine.OPTIMIZATION_MODE_SHIFT_ARC)
        self.comboModeLscsl.addItem(self.lan.get("optModeInvertedShift", "4 - Inverted shift (C+S)"), geometry_engine.OPTIMIZATION_MODE_INVERTED_SHIFT)
        self.comboModeLscsl.addItem(self.lan.get("optModeRatioAllocation", "5 - Configured slew allocation ratio (C / S)"), geometry_engine.OPTIMIZATION_MODE_RATIO_ALLOCATION)
        self.setComboCurrentData(self.comboModeLscsl, config.get("modeLscsl", geometry_engine.OPTIMIZATION_MODE_NONE))
        patternFormLayout.addRow(QLabel(self.lan.get("optPatternLscsl", "Line-Spiral-Curve-Spiral-Line")), self.comboModeLscsl)

        layout.addLayout(patternFormLayout)
        self.buildRatioControls(layout, config)
        self.comboModeLscsl.currentIndexChanged.connect(self.updateRatioVisibility)
        self.updateRatioVisibility()

        # Buttons for the whole dialog
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(self.lan.get("optRun", "Optimize"))
        self.buttonBox.accepted.connect(self.onAccept)
        self.buttonBox.rejected.connect(self.reject)

        # Leaving phase 2 without an optimization is an explicit choice, not just a cancel
        self.isRevertRequested = False
        self.revertButton = self.buttonBox.addButton(
            self.lan.get("optRevertToBaseline", "Revert to Baseline"),
            QDialogButtonBox.ButtonRole.ResetRole)
        self.revertButton.clicked.connect(self.onRevertRequested)
        layout.addWidget(self.buttonBox)

    # Slider and the two paired spin boxes splitting the envelope, only meaningful for mode 5
    def buildRatioControls(self, layout, config):
        ratioC = int(config.get("ratioCPercent", geometry_engine.DEFAULT_RATIO_C_PERCENT))
        ratioC = min(100, max(0, ratioC))

        self.ratioHeading = QLabel(self.lan.get("optRatioLabel", "Slew allocation ratio"))
        self.ratioHeading.setToolTip(self.lan.get(
            "optRatioTip",
            "Share of the lateral slew envelope offered to the arc radius and to the transition curves"))
        layout.addWidget(self.ratioHeading)

        self.ratioSlider = QSlider(Qt.Orientation.Horizontal)
        self.ratioSlider.setRange(0, 100)
        self.ratioSlider.setValue(ratioC)
        layout.addWidget(self.ratioSlider)

        self.ratioFormLayout = QFormLayout()
        self.ratioCLabel = QLabel(self.lan.get("optRatioC", "Radius allocation C [%]:"))
        self.ratioCInput = QSpinBox()
        self.ratioCInput.setRange(0, 100)
        self.ratioCInput.setValue(ratioC)
        self.ratioFormLayout.addRow(self.ratioCLabel, self.ratioCInput)

        self.ratioSLabel = QLabel(self.lan.get("optRatioS", "Transition allocation S [%]:"))
        self.ratioSInput = QSpinBox()
        self.ratioSInput.setRange(0, 100)
        self.ratioSInput.setValue(100 - ratioC)
        self.ratioFormLayout.addRow(self.ratioSLabel, self.ratioSInput)
        layout.addLayout(self.ratioFormLayout)

        self.ratioSlider.valueChanged.connect(self.onRatioCChanged)
        self.ratioCInput.valueChanged.connect(self.onRatioCChanged)
        self.ratioSInput.valueChanged.connect(self.onRatioSChanged)

    # Every ratio control shows one number, so each edit rewrites the other two without echoing back
    def applyRatioC(self, ratioC):
        ratioC = min(100, max(0, int(ratioC)))
        for widget, value in ((self.ratioSlider, ratioC), (self.ratioCInput, ratioC),
                              (self.ratioSInput, 100 - ratioC)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

    def onRatioCChanged(self, ratioC):
        self.applyRatioC(ratioC)

    def onRatioSChanged(self, ratioS):
        self.applyRatioC(100 - int(ratioS))

    # The ratio only means something while mode 5 is chosen, so it is hidden the rest of the time
    def updateRatioVisibility(self):
        isRatioMode = self.comboModeLscsl.currentData() == geometry_engine.OPTIMIZATION_MODE_RATIO_ALLOCATION
        for widget in (self.ratioHeading, self.ratioSlider, self.ratioCLabel, self.ratioCInput,
                       self.ratioSLabel, self.ratioSInput):
            widget.setVisible(isRatioMode)

    # currentData()-based selection helper, mirrors the addItem(text,dataKey) convention used elsewhere
    def setComboCurrentData(self, combo, dataValue):
        index = combo.findData(dataValue)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def validate(self):
        problems = []
        try:
            dMax = float(self.dMaxInput.text())
            if not (0.05 <= dMax <= 1.50):
                problems.append("optErrorDMaxRange")
        except ValueError:
            problems.append("optErrorDMaxRange")
        lMin = None
        try:
            lMin = float(self.lMinInput.text())
            if lMin <= 0:
                problems.append("optErrorLMinRange")
        except ValueError:
            problems.append("optErrorLMinRange")
        try:
            lkMax = float(self.lkMaxInput.text())
            if lkMax <= 0 or (lMin is not None and lkMax < lMin):
                problems.append("optErrorLkMaxRange")
        except ValueError:
            problems.append("optErrorLkMaxRange")
        # A ceiling below the radius that is already there would make every group infeasible
        if self.rMaxEnableCheck.isChecked() and not (R_MAX_MINIMUM_M <= self.rMaxInput.value() <= R_MAX_MAXIMUM_M):
            problems.append("optErrorRMaxRange")
        if self.comboModeLcl.currentData() == geometry_engine.OPTIMIZATION_MODE_NONE and \
           self.comboModeLscsl.currentData() == geometry_engine.OPTIMIZATION_MODE_NONE:
            problems.append("optErrorNoPatterns")
        return problems

    # Closes the dialog asking the caller to drop the optimization instead of running a new one
    def onRevertRequested(self):
        self.isRevertRequested = True
        self.accept()

    def onAccept(self):
        problems = self.validate()
        if problems:
            QMessageBox.warning(self, self.lan.get("error", "Error"),
                                 "\n".join(self.lan.get(code, code) for code in problems))
            return
        self.accept()

    def getOptimizationConfig(self):
        return {
            "dMaxM": float(self.dMaxInput.text()),
            "lMinM": float(self.lMinInput.text()),
            "lkMaxM": float(self.lkMaxInput.text()),
            "isRMaxEnabled": self.rMaxEnableCheck.isChecked(),
            "rMaxM": float(self.rMaxInput.value()),
            "ratioCPercent": int(self.ratioCInput.value()),
            "modeLcl": self.comboModeLcl.currentData(),
            "modeLscsl": self.comboModeLscsl.currentData(),
        }


class StopsSettingsDialog(QDialog):
    def __init__(self, settingsData, lan, parent=None):
        super().__init__(parent)
        self.settingsData = settingsData
        
        self.setWindowTitle(lan.get("stopsSettings", "Stops Settings"))
        self.setMinimumSize(400, 400)

        layout = QVBoxLayout(self)
        
        formLayout = QFormLayout()
        self.inputDwellTime = QLineEdit(str(self.settingsData.get("defaultDwellTime", 30.0)))
        formLayout.addRow(QLabel(lan.get("defaultDwellTime", "Default Dwell Time [s]:")), self.inputDwellTime)
        layout.addLayout(formLayout)

        labelStops = QLabel(lan.get("trainStops", "Train Stops"))
        layout.addWidget(labelStops)

        self.tableStops = QTableWidget(0, 3)
        self.tableStops.setHorizontalHeaderLabels([
            lan["station"],
            lan.get("dwellTimeTable", "Dwell Time [s]"),
            lan.get("stopName", "Stop Name")
        ])
        headerStops = self.tableStops.horizontalHeader()
        headerStops.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tableStops)

        defaultStops = self.settingsData.get("trainStops", [])
        self.populateTable(self.tableStops, defaultStops)

        toolbarLayoutStops = QHBoxLayout()
        
        self.btnAddStop = QPushButton(lan.get("addRow", "Add Row"))
        self.btnAddStop.clicked.connect(self.addStopRow)
        toolbarLayoutStops.addWidget(self.btnAddStop)

        self.btnRemoveStop = QPushButton(lan.get("removeRow", "Remove Row"))
        self.btnRemoveStop.clicked.connect(self.removeStopRow)
        toolbarLayoutStops.addWidget(self.btnRemoveStop)

        self.btnImportStops = QPushButton(lan["importCSV"])
        self.btnImportStops.clicked.connect(lambda: self.importCSV("tableStops"))
        toolbarLayoutStops.addWidget(self.btnImportStops)

        self.btnExportStops = QPushButton(lan["exportCSV"])
        self.btnExportStops.clicked.connect(lambda: self.exportCSV("tableStops"))
        toolbarLayoutStops.addWidget(self.btnExportStops)

        layout.addLayout(toolbarLayoutStops)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def addStopRow(self):
        row = self.tableStops.rowCount()
        self.tableStops.insertRow(row)
        itemStation = QTableWidgetItem("")
        defaultDwell = self.inputDwellTime.text()
        itemDwell = QTableWidgetItem(defaultDwell)
        itemName = QTableWidgetItem("")
        self.tableStops.setItem(row, 0, itemStation)
        self.tableStops.setItem(row, 1, itemDwell)
        self.tableStops.setItem(row, 2, itemName)

    def removeStopRow(self):
        currentRow = self.tableStops.currentRow()
        if currentRow >= 0:
            self.tableStops.removeRow(currentRow)

    def populateTable(self, tableWidget, data):
        tableWidget.setRowCount(len(data))
        for row, rowData in enumerate(data):
            for col, value in enumerate(rowData):
                item = QTableWidgetItem(str(value))
                tableWidget.setItem(row, col, item)

    def importCSV(self, table):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "CSV Files (*.csv)")
        if not filepath: return
        fileContent = readfile.ReadFile().Read(filepath)
        if fileContent.startswith("Error"):
            err = QMessageBox(); err.setWindowTitle("Error"); err.setIcon(QMessageBox.Icon.Warning); err.exec(); return
        try:
            reader = csv.reader(io.StringIO(fileContent), delimiter=',')
            next(reader, None)
            dataList = list(reader)
            if table == "tableStops": self.populateTable(self.tableStops, dataList)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            
    def exportCSV(self, table):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File", "", "CSV Files (*.csv)")
        if not filepath: return
        try:
            if table == "tableStops":
                with open(filepath, "w", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(["Station", "Dwell Time", "Name"])
                    for row in range(self.tableStops.rowCount()):
                        writer.writerow([self.tableStops.item(row, col).text() for col in range(self.tableStops.columnCount())])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            
    def getSettings(self):
        settingsData = {"trainStops": []}
        try: settingsData["defaultDwellTime"] = float(self.inputDwellTime.text())
        except ValueError: pass
        for row in range(self.tableStops.rowCount()):
            try: 
                station = float(self.tableStops.item(row, 0).text())
                dwell = float(self.tableStops.item(row, 1).text())
                nameItem = self.tableStops.item(row, 2)
                name = nameItem.text() if nameItem else ""
                settingsData["trainStops"].append([station, dwell, name])
            except (ValueError, AttributeError): 
                continue
        return settingsData

class SpeedSettingsDialog(QDialog):
    def __init__(self, settingsData, lan, parent=None):
        super().__init__(parent)
        self.settingsData = settingsData
        
        self.setWindowTitle(lan.get("speedSettings", "Speed Limits Settings"))
        self.setMinimumSize(400, 400)

        layout = QVBoxLayout(self)
        
        labelSpeeds = QLabel(lan.get("manualSpeedLimits", "Manual Speed Limits"))
        layout.addWidget(labelSpeeds)

        self.tableSpeeds = QTableWidget(0, 2)
        self.tableSpeeds.setHorizontalHeaderLabels([
            lan["station"],
            lan.get("speed_lim", "Speed Limit [km/h]")
        ])
        headerSpeeds = self.tableSpeeds.horizontalHeader()
        headerSpeeds.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tableSpeeds)

        defaultSpeeds = self.settingsData.get("manualSpeedLimits", [])
        self.populateTable(self.tableSpeeds, defaultSpeeds)

        toolbarLayoutSpeeds = QHBoxLayout()
        
        self.btnAddSpeed = QPushButton(lan.get("addRow", "Add Row"))
        self.btnAddSpeed.clicked.connect(self.addSpeedRow)
        toolbarLayoutSpeeds.addWidget(self.btnAddSpeed)

        self.btnRemoveSpeed = QPushButton(lan.get("removeRow", "Remove Row"))
        self.btnRemoveSpeed.clicked.connect(self.removeSpeedRow)
        toolbarLayoutSpeeds.addWidget(self.btnRemoveSpeed)

        self.btnImportSpeeds = QPushButton(lan["importCSV"])
        self.btnImportSpeeds.clicked.connect(self.importSpeedsCSV)
        toolbarLayoutSpeeds.addWidget(self.btnImportSpeeds)

        self.btnExportSpeeds = QPushButton(lan["exportCSV"])
        self.btnExportSpeeds.clicked.connect(self.exportSpeedsCSV)
        toolbarLayoutSpeeds.addWidget(self.btnExportSpeeds)

        layout.addLayout(toolbarLayoutSpeeds)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def addSpeedRow(self):
        row = self.tableSpeeds.rowCount()
        self.tableSpeeds.insertRow(row)
        itemStation = QTableWidgetItem("")
        itemSpeed = QTableWidgetItem("")
        self.tableSpeeds.setItem(row, 0, itemStation)
        self.tableSpeeds.setItem(row, 1, itemSpeed)

    def removeSpeedRow(self):
        currentRow = self.tableSpeeds.currentRow()
        if currentRow >= 0:
            self.tableSpeeds.removeRow(currentRow)

    def populateTable(self, tableWidget, data):
        tableWidget.setRowCount(len(data))
        for row, rowData in enumerate(data):
            for col, value in enumerate(rowData):
                item = QTableWidgetItem(str(value))
                tableWidget.setItem(row, col, item)

    def importSpeedsCSV(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "CSV Files (*.csv)")
        if not filepath: return
        fileContent = readfile.ReadFile().Read(filepath)
        if fileContent.startswith("Error"):
            err = QMessageBox(); err.setWindowTitle("Error"); err.setIcon(QMessageBox.Icon.Warning); err.exec(); return
        try:
            reader = csv.reader(io.StringIO(fileContent), delimiter=',')
            next(reader, None) # Skip header
            dataList = [row[:2] for row in reader] # Take only first two columns
            self.populateTable(self.tableSpeeds, dataList)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            
    def exportSpeedsCSV(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File", "", "CSV Files (*.csv)")
        if not filepath: return
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["Station", "Speed"])
                for row in range(self.tableSpeeds.rowCount()):
                    writer.writerow([self.tableSpeeds.item(row, col).text() for col in range(self.tableSpeeds.columnCount())])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            
    def getSettings(self):
        settingsData = {"manualSpeedLimits": []}
        for row in range(self.tableSpeeds.rowCount()):
            try: 
                station = float(self.tableSpeeds.item(row, 0).text())
                speed = float(self.tableSpeeds.item(row, 1).text())
                settingsData["manualSpeedLimits"].append([station, speed])
            except (ValueError, AttributeError): 
                continue
        # Sort by station
        settingsData["manualSpeedLimits"].sort(key=lambda x: x[0])
        return settingsData


# ---------------------------------------------------------------------------
# Pop-up plot window
# ---------------------------------------------------------------------------

# Standalone pop-up window with its own pyqtgraph canvas and navigation toolbar
class PopupPlotWindow(QDialog):

    def __init__(self, title, parent=None, lan=None):
        super().__init__(parent)
        self.setWindowTitle(title)

        # Make this a proper independent top-level window, not a modal dialog
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1100, 680)

        self.lan = lan if lan is not None else {}
        self.annotationItems = []
        self.markerLines = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.plotWidget = plot_widgets.CoypuPlotWidget(self.lan)
        self.plotWidget.plotTitles["main"] = title
        self.mainPlot = self.plotWidget.addPlotRow("main", 0, withCrosshair=False)

        self.toolbar = plot_widgets.PlotNavigationToolbar(self.plotWidget, self.lan, self)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.plotWidget)

        self.secondaryView = None

    # Adopt the theme of the main window so the popup does not flash white
    def applyTheme(self, isDark, tokens=None):
        self.plotWidget.applyTheme(isDark, tokens)

    # ------------------------------------------------------------------
    def drawData(
        self,
        primarySeries,
        *,
        xlabel: str = "",
        ylabel: str = "",
        title: str = "",
        grid: bool = True,
        secondarySeries=None,
        secondaryYlabel: str = "",
        secondaryFormatter=None,
        symmetricYlim: bool = False,
        textAnnotations=None,
        axlines=None,
    ):
        # Series descriptors carry x, y, label, color, linestyle, alpha, marker and step
        self.resetCanvas()

        if secondarySeries:
            self.secondaryView = self.plotWidget.addRightAxis("main", secondaryYlabel)
            if secondaryFormatter is not None:
                self.applyAxisFormatter(secondaryFormatter)

        self.drawSeries(primarySeries, onRight=False)
        if secondarySeries:
            self.drawSeries(secondarySeries, onRight=True)

        self.drawAnnotations(textAnnotations)
        self.drawMarkerLines(axlines)

        self.mainPlot.setLabel("bottom", xlabel)
        self.mainPlot.setLabel("left", ylabel)
        self.mainPlot.setTitle(title)
        self.plotWidget.setGridVisible("main", grid)
        self.plotWidget.plotTitles["main"] = title or self.windowTitle()

        self.mainPlot.enableAutoRange(axis="x")
        self.applyVerticalRange(symmetricYlim, bool(secondarySeries))
        # Reset from the context menu has to reach the same policy this draw applied
        self.plotWidget.setYRangeHandler(
            "main", lambda: self.applyVerticalRange(symmetricYlim, bool(secondarySeries)))

    # Vertical extents of the detached plot, symmetric about zero or simply fitted to the data
    def applyVerticalRange(self, symmetricYlim, hasSecondary):
        if symmetricYlim:
            self.applySymmetricRange()
            if hasSecondary:
                self.plotWidget.enableZeroLock("main")
            return

        # The axis is mouse locked by default, so the data extent is fitted once here instead
        self.mainPlot.enableAutoRange(axis="y")
        self.mainPlot.disableAutoRange(axis="y")

    # Drop every item so a repeated drawData call starts from a clean plot
    def resetCanvas(self):
        for item in self.annotationItems + self.markerLines:
            self.mainPlot.removeItem(item)
        self.annotationItems = []
        self.markerLines = []

        self.plotWidget.clearPlot("main")
        self.plotWidget.removeRightAxis("main")
        self.secondaryView = None

    # Convert descriptor dictionaries into curves on the requested axis
    def drawSeries(self, seriesList, onRight):
        for seriesIndex, series in enumerate(seriesList or []):
            xValues, yValues = series.get("x"), series.get("y")
            if xValues is None or yValues is None or len(xValues) == 0 or len(yValues) == 0:
                continue

            axisPrefix = "right" if onRight else "left"
            self.plotWidget.setSeriesData(
                "main", f"{axisPrefix}{seriesIndex}", xValues, yValues,
                name=series.get("label", ""),
                color=series.get("color", "#3b7dd8"),
                dash=series.get("linestyle", "-") != "-",
                step=bool(series.get("step", False)),
                symbol=plot_widgets.symbolFromMarker(series.get("marker")),
                onRight=onRight,
                alpha=series.get("alpha"),
            )

    # Place free text labels such as the profile gradient annotations
    def drawAnnotations(self, textAnnotations):
        for annotation in textAnnotations or []:
            textItem = pg.TextItem(annotation.get("text", ""), anchor=(0.5, 1.0))
            textItem.setPos(annotation.get("x", 0), annotation.get("y", 0))
            self.mainPlot.addItem(textItem, ignoreBounds=True)
            self.annotationItems.append(textItem)

    # Draw the stop marker lines with their optional rotated captions
    def drawMarkerLines(self, axlines):
        for axline in axlines or []:
            axisDirection = axline.get("axis", "x")
            lineColor = plot_widgets.resolveColor(axline.get("color", "#8a8a8a"))
            penStyle = plot_widgets.penStyleFromLineStyle(axline.get("linestyle", "--"))

            markerPen = pg.mkPen(lineColor, width=1, style=penStyle)
            markerPen.setColor(self.withAlpha(markerPen.color(), axline.get("alpha", 0.7)))

            labelText = axline.get("label_text", "")
            labelOpts = None
            if labelText:
                labelOpts = {
                    "position": 0.9,
                    "color": plot_widgets.resolveColor(axline.get("label_color", lineColor)),
                    "anchor": (0, 1) if axisDirection == "x" else (0, 0),
                    "rotateAxis": (1, 0) if axline.get("label_rotation", 0) else None,
                    "fill": None,
                }

            markerLine = pg.InfiniteLine(
                pos=axline.get("pos", 0),
                angle=90 if axisDirection == "x" else 0,
                movable=False, pen=markerPen,
                label=labelText or None, labelOpts=labelOpts)

            self.mainPlot.addItem(markerLine, ignoreBounds=True)
            self.markerLines.append(markerLine)

    # Apply an alpha fraction to a colour without mutating the original
    def withAlpha(self, color, alpha):
        faded = pg.mkColor(color)
        faded.setAlphaF(float(alpha))
        return faded

    # Swap in a tick formatter callable for the secondary axis
    def applyAxisFormatter(self, formatter):
        rightAxis = self.mainPlot.getAxis("right")

        # The callable receives one tick value and returns the string to display
        def tickStrings(values, scale, spacing):
            return [formatter(value) for value in values]

        rightAxis.tickStrings = tickStrings

    # Centre both y-axes on zero so the cant and curvature overlay lines up
    def applySymmetricRange(self):
        # The range is taken from the data because auto ranging happens later
        for viewBox, onRight in ((self.mainPlot.vb, False), (self.secondaryView, True)):
            if viewBox is None:
                continue
            limit = self.peakMagnitude(onRight) * POPUP_RANGE_HEADROOM
            viewBox.setYRange(-limit, limit, padding=0)

    # Largest absolute y value across the curves drawn on one of the two axes
    def peakMagnitude(self, onRight):
        peak = 1e-9
        for entry in self.plotWidget.plotSeries.get("main", {}).values():
            if entry["onRight"] != onRight or entry["y"].size == 0:
                continue
            finiteValues = entry["y"][np.isfinite(entry["y"])]
            if finiteValues.size:
                peak = max(peak, float(np.max(np.abs(finiteValues))))
        return peak
