# PySide6 imports
from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl, QEvent, Signal
from PySide6.QtWidgets import (QTabWidget, QApplication, QMainWindow, QPushButton, QWidget,
                                QHBoxLayout, QVBoxLayout, QLabel, QPlainTextEdit, QFileDialog,
                                QSplitter, QMessageBox, QStyle, QToolBar, QMenu, QStackedWidget,
                                QStatusBar, QLineEdit, QTextEdit, QComboBox, QAbstractItemView,
                                QToolButton, QSizePolicy, QProgressBar)
from PySide6.QtGui import QAction, QActionGroup, QIcon, QCursor, QDesktopServices

# pyqtgraph imports
import pyqtgraph as pg

# numpy import for data handling
import numpy as np

import json
from pathlib import Path
# Local imports
import readfile
import basemap_key
import gui_overlay
from map_viewer import MapWidget
import default_values
import geometry_engine
import vehicle_engine
import vehicle_catalog
import source_stack
import theme_manager
import icons
from theme_manager import ThemeManager
from lazy_dock import LazyDockWidget
from ribbon import RibbonBar, SERIES_TOGGLE_PROPERTY, DESTRUCTIVE_BUTTON_PROPERTY, COMPACT_ICON_SIZE
from workflow_dock import WorkflowStepperWidget
from graphs_dock import PerformanceGraphsWidget
from profile_dock import ProfilePlotWidget
from kinematics_dock import KinematicsPlotWidget
from help_dock import HelpWidget
from track_stats_dock import TrackStatisticsWidget
from xml_editor import XmlCodeEditor
from translation_manager import TranslationManager
from shortcut_manager import ShortcutManager
import optimization_runner
import profile_state
import simulation_runner
from profile_state import ProfileSelectorBar
import slew_report
from settings_dialog import ShortcutSettingsDialog
from vehicle_dialog import VehicleSettingsDialog, VehicleCatalogDialog
from purge_dialog import PurgeDataDialog
from floating_command_input import FloatingCommandInput
import batch_config
import batch_results
import batch_metrics
import batch_runner
import landxml_merger
from batch_dialog import BatchProcessingDialog
from batch_progress import BatchProgressDialog
from variant_dashboard import VariantDashboardWidget
import report_formats
import batch_export
import presets_manager
import project_file
import project_metadata
import landxml_exporter
from project_metadata import ProjectMetadataDialog
from resource_paths import getWritableRoot
import tempfile
from datetime import datetime
import copy

# Central viewport page indices
VIEW_MAP = 0
VIEW_REPORT = 1
VIEW_DASHBOARD = 2

# How long a transient status bar confirmation stays visible in milliseconds
SERIES_STATUS_TIMEOUT = 4000

# Vector icon assigned to each ribbon action, regenerated on every theme switch
ACTION_ICONS = {
    "openFileAction": "openText",
    "autodetectXMLAction": "open",
    "openParseLandXMLAction": "openLandxml",
    "openParseXMLTTPAction": "openTtp",
    "appendAutodetectXMLAction": "append",
    "appendLandXMLAction": "appendLandxml",
    "appendXMLTTPAction": "appendTtp",
    "exitAction": "exit",
    "helpAction": "help",
    "openCoypuFeederAction": "detach",
    "openShortcutSettingsAction": "settings",
    "calculateGeometryAction": "calculate",
    "calculateGeometryIAction": "calculateAlt",
    "calculateTrainSpeedAction": "run",
    "cleanTTPDataAction": "cleanPart",
    "cleanLandXMLDataAction": "cleanPart",
    "cleanDataAction": "clean",
    "cleanCalculatedCantsAction": "cleanPart",
    "cleanCalculatedSpeedsAction": "cleanPart",
    "mapSettingsAction": "map",
    "geometrySettingsAction": "settings",
    "vehicleSettingsAction": "vehicle",
    "reverseDirectionAction": "stops",
    "stopsSettingsAction": "stops",
    "speedSettingsAction": "settings",
    "designApproachAction": "settings",
    "alignmentOptimizationAction": "optimize",
    "clearOptimizationAction": "cleanPart",
    "slewReportAction": "report",
    "toggleSlewPlotAction": "style",
    "includeSlewSectionAction": "layers",
    "toggleUnitsAction": "units",
    "themeAutoAction": "themeAuto",
    "themeLightAction": "themeLight",
    "themeDarkAction": "themeDark",
    "showMapAction": "viewMap",
    "showReportAction": "viewReport",
    "resetLayoutAction": "resetLayout",
    "foldAllAction": "foldAll",
    "unfoldAllAction": "unfoldAll",
    "reportGeometryAction": "report",
    "exportGeometryReportAction": "export",
    "openBatchProcessingAction": "batch",
    "showDashboardAction": "dashboard",
    "exportBatchArchiveAction": "export",
    "reportVehicleButton": "report",
    "exportVehicleButton": "export",
    "exportPresetsAction": "export",
    "importPresetsAction": "open",
    "newProjectAction": "openText",
    "openProjectAction": "open",
    "saveProjectAction": "export",
    "saveProjectAsAction": "export",
    "projectPropertiesAction": "report",
    "exportLandXmlAction": "openLandxml",
    "recentProjectsButton": "open",
}

# Compact ribbon captions for the data series toggles, full text stays in the tooltip
SERIES_SHORT_KEYS = {
    "toggleCantAction": "shortSeriesCant",
    "toggleCantPossibleAction": "shortSeriesCantPossible",
    "toggleCDef100Action": "shortSeriesCDef100",
    "toggleCDef130Action": "shortSeriesCDef130",
    "toggleCDef150Action": "shortSeriesCDef150",
    "toggleCDefKAction": "shortSeriesCDefK",
    "toggleCantDef100Action": "shortSeriesCantDef100",
    "toggleCantDef130Action": "shortSeriesCantDef130",
    "toggleCantDef150Action": "shortSeriesCantDef150",
    "toggleCantDefKAction": "shortSeriesCantDefK",
    "toggleCurvatureAction": "shortSeriesCurvature",
    "toggleCurvatureBaselineAction": "shortSeriesCurvatureBaseline",
    "toggleSpeedAction": "shortSeriesSpeed",
    "toggleSpeed100Action": "shortSeriesSpeed100",
    "toggleSpeed130Action": "shortSeriesSpeed130",
    "toggleSpeed150Action": "shortSeriesSpeed150",
    "toggleSpeedKAction": "shortSeriesSpeedK",
    "toggleProfileAction": "shortSeriesProfile",
    "toggleKinematicsSpeedLimitTrackAction": "shortSeriesTachoTrack",
    "toggleKinematicsSpeedLimitTimeAction": "shortSeriesTachoTime",
    "toggleKinematicsDistanceTimeAction": "shortSeriesDistTime",
    "toggleKinematicsForcesAction": "shortSeriesForces",
}

# Geometry arrays kept as a muted baseline once an optimization moves the active alignment
# geometryType and curvatureSign carry no plot of their own, they let the D+I pass rerun on the import
BASELINE_COMPARISON_KEYS = ("stationHorizontal", "curvature", "alignmentCoordinates",
                            "geometryType", "curvatureSign")

# Suffix marking a baseline copy, never cleared by a recalculation
BASELINE_KEY_SUFFIX = "Baseline"

# Optimizer provenance describing the geometry change itself, not a cant or speed result
OPTIMIZATION_STATE_KEYS = ("optimizationSummary", "slewProfileStationKm", "slewProfileOffsetMm",
                           "chainageMapBaselineKm", "chainageMapActiveKm")

# Design speed profiles the geometry engine derives, cleared whenever the active geometry moves
OPTIMIZED_PROFILE_SUFFIXES = ("100", "130", "150", "K")

# Short text badges rendered as icons for the data series toggle actions
SERIES_BADGES = {
    "toggleCantAction": "D",
    "toggleCantPossibleAction": "Dp",
    "toggleCDef100Action": "I100",
    "toggleCDef130Action": "I130",
    "toggleCDef150Action": "I150",
    "toggleCDefKAction": "IK",
    "toggleCantDef100Action": "D+I100",
    "toggleCantDef130Action": "D+I130",
    "toggleCantDef150Action": "D+I150",
    "toggleCantDefKAction": "D+IK",
    "toggleCurvatureAction": "1/R",
    "toggleCurvatureBaselineAction": "1/Rb",
    "toggleSpeedAction": "v_lim",
    "toggleSpeed100Action": "V100",
    "toggleSpeed130Action": "V130",
    "toggleSpeed150Action": "V150",
    "toggleSpeedKAction": "VK",
    "toggleProfileAction": "H",
    "toggleKinematicsSpeedLimitTrackAction": "v-s",
    "toggleKinematicsSpeedLimitTimeAction": "v-t",
    "toggleKinematicsDistanceTimeAction": "s-t",
    "toggleKinematicsForcesAction": "F",
}


class MainWindow(QMainWindow):
    # Emitted once a cant and speed design finished, whichever loop produced it
    geometryCalculationFinished = Signal()

    # Emitted once a vehicle kinematics run finished
    vehicleCalculationFinished = Signal()

    def __init__(self):
        super().__init__()

        # Window settings
        self.resize(QSize(1400, 900))
        self.translationManager = TranslationManager()
        self.currentLanguage = "en"
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.setWindowTitle(lan["app_title"])

        # Other default settings
        self.epsgInput = "EPSG:5514"

        # Empty dictionaries for data to be loaded and plotted
        self.dataStorage = {}

        # Import default values to dataStorage
        self.dataStorage["settingsData"] = {}
        self.dataStorage["settingsData"] = copy.deepcopy(default_values.defVal)

        # Persistent settings store for layout, theme and language
        self.appSettings = QSettings("COYPU", "COYPU")

        # Right-click context menu keeps popup dialogs alive in this list
        self.popupWindows = []

        self.themeManager = ThemeManager(self)
        self.shortcutManager = ShortcutManager()
        self.presetManager = presets_manager.PresetManager()

        # Native .coypu project state: metadata header, current file and the unsaved changes flag
        self.projectMetadata = project_metadata.buildDefaultMetadata()
        self.currentProjectPath = None
        self.isProjectModified = False
        self.projectFileManager = project_file.ProjectFileManager()
        self.recentProjectsStore = project_file.RecentProjectsStore(self.appSettings)
        self.autoSaveTimer = QTimer(self)
        self.autoSaveTimer.setInterval(project_file.AUTO_SAVE_INTERVAL_MS)
        self.autoSaveTimer.timeout.connect(self.performAutoSave)

        # Batch processing: config presets, the last run's results, and the isolated-thread controller
        self.batchConfigStore = batch_config.BatchConfigStore()
        self.batchResults = batch_results.BatchResultStore()
        self.batchController = batch_runner.BatchController(self)
        self.batchController.variantStarted.connect(self.onBatchVariantStarted)
        self.batchController.variantFinished.connect(self.onBatchVariantFinished)
        self.batchController.batchFinished.connect(self.onBatchFinished)
        self.batchController.batchFailed.connect(self.onBatchFailed)
        self.batchProgressDialog = None
        self.batchMergedLandXml = None

        # Alignment optimization: the isolated-thread controller, the revert cache and the report window
        self.optimizationController = optimization_runner.OptimizationController(self)
        self.optimizationController.optimizationFinished.connect(self.onOptimizationFinished)
        self.optimizationController.optimizationFailed.connect(self.onOptimizationFailed)
        self.optimizationController.progressChanged.connect(self.onOptimizationProgress)
        self.baselineAlignmentCache = None
        self.slewReportWindow = None

        # Shared active speed profile driving the ribbon, the graphs dock and the statistics dock
        self.profileState = profile_state.ProfileStateManager(self)
        self.profileState.activeProfileChanged.connect(self.onActiveProfileChanged)
        self.profileState.availableProfilesChanged.connect(self.onAvailableProfilesChanged)

        # Multi profile kinematics on an isolated thread, plus the cache every selector projects from
        self.simulationController = simulation_runner.SimulationController(self)
        self.simulationController.simulationFinished.connect(self.onSimulationFinished)
        self.simulationController.simulationFailed.connect(self.onSimulationFailed)
        self.simulationController.progressChanged.connect(self.onSimulationProgress)
        self.simulationResultsByProfile = {}

        # State the group speed columns were last evaluated for, so two D+I passes are not repeated
        self.optimizationImpactSignatureCache = None

        # Reports and the statistics dock follow every calculation instead of waiting to be reopened
        self.geometryCalculationFinished.connect(self.onCalculationFinished)
        self.vehicleCalculationFinished.connect(self.onCalculationFinished)

        # Set while a report is rebuilt in the background, so the central view is left alone
        self.isReportRefreshSilent = False

        # Whichever geometry loop the user last ran, replayed against the optimized geometry
        self.lastCalculationMode = "design"

        # Lines behind the currently displayed geometry report, reused by every export format
        self.lastGeometryReportLines = []

        # Vehicle whose report is on screen, so a recalculation can refresh the same one
        self.lastVehicleReportIndex = None

        # Batch variant currently pulled into the viewport, cleared by a revert or a new project
        self.loadedBatchVariantId = None

        # Provenance for imported files and the folder based vehicle library
        self.sourceStack = source_stack.SourceStack()
        self.vehicleCatalog = vehicle_catalog.VehicleCatalog()
        self.vehicleCatalog.scanCatalog()

        self.buildActions()
        self.shortcutManager.applyShortcuts(self)
        self.buildCentralViews()
        self.buildDocks()

        # Icons need the dock toggle actions, so they are assigned after buildDocks
        self.applyActionIcons()

        self.buildRibbon()
        self.buildStatusBar()
        self.connectCursorSignals()
        self.connectMapSignals()
        self.connectProfileSignals()

        self.buildFloatingCommandInput()

        self.themeManager.themeChanged.connect(self.onThemeChanged)
        self.restoreSession()
        self.updateWindowTitle()
        self.autoSaveTimer.start()

        # Deferred so the main window is already visible when the recovery question appears
        QTimer.singleShot(0, self.promptRecoveryIfAvailable)

    # Create every QAction once and keep a named reference for translation
    def buildActions(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        style = self.style()

        # Native project actions
        self.newProjectAction = QAction(lan.get("newProject", "New Project"), self)
        self.newProjectAction.triggered.connect(self.newProject)

        self.openProjectAction = QAction(lan.get("openProject", "Open Project..."), self)
        self.openProjectAction.triggered.connect(self.openProject)

        self.saveProjectAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            lan.get("saveProject", "Save Project"), self)
        self.saveProjectAction.triggered.connect(self.saveProject)

        self.saveProjectAsAction = QAction(lan.get("saveProjectAs", "Save Project As..."), self)
        self.saveProjectAsAction.triggered.connect(self.saveProjectAs)

        self.projectPropertiesAction = QAction(
            lan.get("projectProperties", "Project Properties..."), self)
        self.projectPropertiesAction.triggered.connect(self.openProjectProperties)

        self.exportLandXmlAction = QAction(
            lan.get("exportLandXml", "Export Alignment to LandXML..."), self)
        self.exportLandXmlAction.triggered.connect(self.exportLandXml)

        # Recent projects live in their own menu button, rebuilt whenever the list changes
        self.recentProjectsMenu = QMenu(self)
        self.recentProjectsButton = self.buildVehicleMenuButton(
            lan.get("recentProjects", "Recent Projects"), self.recentProjectsMenu)

        # File actions
        self.openFileAction = QAction(lan["open_file"], self)
        self.openFileAction.triggered.connect(self.openFile)

        self.autodetectXMLAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), lan["autodetect"], self)
        self.autodetectXMLAction.setStatusTip(lan["autodetect_tip"])
        self.autodetectXMLAction.triggered.connect(self.openAutodetectXML)

        self.appendAutodetectXMLAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon),
            lan.get("append_autodetect", "Append Autodetect"), self)
        self.appendAutodetectXMLAction.setStatusTip(lan.get("append_autodetect_tip", "Autodetect and append"))
        self.appendAutodetectXMLAction.triggered.connect(self.appendAutodetectXML)

        self.openParseLandXMLAction = QAction(lan["open_parse_landxml"], self)
        self.openParseLandXMLAction.triggered.connect(self.openLandXML)

        self.appendLandXMLAction = QAction(lan.get("append_landxml", "Append LandXML"), self)
        self.appendLandXMLAction.triggered.connect(self.appendLandXML)

        self.openParseXMLTTPAction = QAction(lan["open_parse_xmlttp"], self)
        self.openParseXMLTTPAction.triggered.connect(self.openXMLTTP)

        self.appendXMLTTPAction = QAction(lan.get("append_xmlttp", "Append XML TTP"), self)
        self.appendXMLTTPAction.triggered.connect(self.appendXMLTTP)

        self.exitAction = QAction(lan["exit"], self)
        self.exitAction.triggered.connect(self.close)

        self.helpAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton), lan["help"], self)
        self.helpAction.triggered.connect(self.openHelp)

        # Opens the Coypu Feeder companion project page in the system browser
        self.openCoypuFeederAction = QAction(lan.get("openCoypuFeeder", "Coypu Feeder"), self)
        self.openCoypuFeederAction.triggered.connect(self.openCoypuFeeder)

        # Calculate actions
        self.calculateGeometryAction = QAction(lan["calculate_geometry"], self)
        self.calculateGeometryAction.triggered.connect(self.calculateGeometry)

        self.calculateGeometryIAction = QAction(lan["calculate_geometry_I"], self)
        self.calculateGeometryIAction.triggered.connect(self.calculateGeometryI)

        self.calculateTrainSpeedAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), lan["calculate_train_speed"], self)
        self.calculateTrainSpeedAction.triggered.connect(self.calculateTrainSpeed)

        # Clean actions
        self.cleanTTPDataAction = QAction(lan["cleanTTP"], self)
        self.cleanTTPDataAction.triggered.connect(self.cleanTTPData)

        self.cleanLandXMLDataAction = QAction(lan["cleanLandXML"], self)
        self.cleanLandXMLDataAction.triggered.connect(self.cleanLandXMLData)

        self.cleanDataAction = QAction(
            QIcon.fromTheme("user-trash", style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon)),
            lan["cleanAll"], self)
        self.cleanDataAction.triggered.connect(self.cleanData)

        self.cleanCalculatedCantsAction = QAction(lan["cleanCants"], self)
        self.cleanCalculatedCantsAction.triggered.connect(self.cleanCalculatedCants)

        self.cleanCalculatedSpeedsAction = QAction(lan["cleanSpeeds"], self)
        self.cleanCalculatedSpeedsAction.triggered.connect(self.cleanCalculatedSpeeds)

        self.openPurgeDialogAction = QAction(
            QIcon.fromTheme("edit-clear-all", style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)),
            lan.get("purgeData", "Purge Data..."), self)
        self.openPurgeDialogAction.triggered.connect(self.openPurgeDialog)

        # Batch processing actions
        self.openBatchProcessingAction = QAction(lan.get("batchTitle", "Batch Processing"), self)
        self.openBatchProcessingAction.triggered.connect(self.openBatchProcessing)

        self.exportBatchArchiveAction = QAction(lan.get("exportBatchArchive", "Export batch reports to ZIP..."), self)
        self.exportBatchArchiveAction.triggered.connect(self.exportBatchArchive)

        # Settings actions
        self.mapSettingsAction = QAction(
            QIcon.fromTheme("internet-web-browser",
                            style.standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)),
            lan["mapSettings"], self)
        self.mapSettingsAction.triggered.connect(self.openMapSettings)

        self.geometrySettingsAction = QAction(lan["geometrySettings"], self)
        self.geometrySettingsAction.triggered.connect(self.openGeometrySettings)

        self.vehicleSettingsAction = QAction(
            QIcon.fromTheme("preferences-system",
                            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)),
            lan.get("vehicleSettings", "Vehicle Settings"), self)
        self.vehicleSettingsAction.triggered.connect(self.openVehicleSettings)

        self.openVehicleCatalogAction = QAction(
            QIcon.fromTheme("view-list-details",
                            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)),
            lan.get("vehicleCatalog", "Vehicle Catalog"), self)
        self.openVehicleCatalogAction.triggered.connect(self.openVehicleCatalog)

        self.stopsSettingsAction = QAction(
            QIcon.fromTheme("appointment-new",
                            style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)),
            lan.get("stopsSettings", "Stops Settings"), self)
        self.stopsSettingsAction.triggered.connect(self.openStopsSettings)

        self.speedSettingsAction = QAction(lan.get("speedSettings", "Speed Limits Settings"), self)
        self.speedSettingsAction.triggered.connect(self.openSpeedSettings)

        self.openShortcutSettingsAction = QAction(lan.get("shortcutSettings", "Shortcuts"), self)
        self.openShortcutSettingsAction.triggered.connect(self.openShortcutSettings)

        self.exportPresetsAction = QAction(lan.get("exportPresets", "Export Presets..."), self)
        self.exportPresetsAction.triggered.connect(self.exportPresets)

        self.importPresetsAction = QAction(lan.get("importPresets", "Import Presets..."), self)
        self.importPresetsAction.triggered.connect(self.importPresets)

        self.designApproachAction = QAction(lan["designApproach"], self)
        self.designApproachAction.triggered.connect(self.openDesignApproach)

        self.alignmentOptimizationAction = QAction(lan.get("alignmentOptimization", "Alignment Optimization"), self)
        self.alignmentOptimizationAction.triggered.connect(self.openAlignmentOptimization)

        # triggered carries a checked flag, so the revert slot deliberately takes no arguments
        self.clearOptimizationAction = QAction(lan.get("clearOptimization", "Clear Optimization"), self)
        self.clearOptimizationAction.triggered.connect(self.revertToBaselineAlignment)
        self.clearOptimizationAction.setEnabled(False)

        self.slewReportAction = QAction(lan.get("slewReport", "Slew Report"), self)
        self.slewReportAction.triggered.connect(self.openSlewReport)
        self.slewReportAction.setEnabled(False)

        self.toggleSlewPlotAction = QAction(lan.get("toggleSlewPlot", "Toggle Slew Plot"), self)
        self.toggleSlewPlotAction.setCheckable(True)
        self.toggleSlewPlotAction.setProperty(SERIES_TOGGLE_PROPERTY, True)
        self.toggleSlewPlotAction.toggled.connect(self.onSlewPlotToggled)
        self.toggleSlewPlotAction.setEnabled(False)

        self.reverseDirectionAction = QAction(lan.get("runAgainstStationing",
                                                       "Run against stationing"), self)
        self.reverseDirectionAction.setCheckable(True)
        self.reverseDirectionAction.setProperty(SERIES_TOGGLE_PROPERTY, True)
        self.reverseDirectionAction.setToolTip(lan.get(
            "runAgainstStationingTip",
            "Drive the whole simulation from the highest chainage towards the lowest"))
        self.reverseDirectionAction.toggled.connect(self.onRunDirectionToggled)

        self.includeSlewSectionAction = QAction(lan.get("includeSlewSection", "Append Slew Summary"), self)
        self.includeSlewSectionAction.setCheckable(True)
        self.includeSlewSectionAction.setChecked(True)
        self.includeSlewSectionAction.setProperty(SERIES_TOGGLE_PROPERTY, True)

        self.toggleUnitsAction = QAction(self)
        self.toggleUnitsAction.setCheckable(True)
        self.toggleUnitsAction.setChecked(False)
        self.toggleUnitsAction.setProperty(SERIES_TOGGLE_PROPERTY, True)
        self.toggleUnitsAction.toggled.connect(self.onUnitsToggled)
        self.updateUnitsActionLabel()

        # Language actions, one per translation file discovered at startup
        self.languageActions = {}
        for langCode, displayName in self.translationManager.availableLanguages():
            languageAction = QAction(displayName, self)
            languageAction.triggered.connect(lambda checked=False, code=langCode: self.changeLanguage(code))
            self.languageActions[langCode] = languageAction

        # Theme override actions behave as a single exclusive choice
        self.themeGroup = QActionGroup(self)
        self.themeGroup.setExclusive(True)

        self.themeAutoAction = QAction(lan.get("themeAuto", "System default (auto)"), self)
        self.themeLightAction = QAction(lan.get("themeLight", "Always light"), self)
        self.themeDarkAction = QAction(lan.get("themeDark", "Always dark"), self)
        for action, mode in ((self.themeAutoAction, theme_manager.MODE_AUTO),
                             (self.themeLightAction, theme_manager.MODE_LIGHT),
                             (self.themeDarkAction, theme_manager.MODE_DARK)):
            action.setCheckable(True)
            action.setData(mode)
            self.themeGroup.addAction(action)
            action.triggered.connect(lambda checked=False, m=mode: self.applyThemeMode(m))
        self.themeAutoAction.setChecked(True)

        # Central viewport switching actions
        self.viewGroup = QActionGroup(self)
        self.viewGroup.setExclusive(True)

        self.showMapAction = QAction(
            QIcon.fromTheme("internet-web-browser",
                            style.standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)),
            lan.get("viewMap", "Map"), self)
        self.showMapAction.setCheckable(True)
        self.showMapAction.setChecked(True)
        self.showMapAction.triggered.connect(self.showMapView)
        self.viewGroup.addAction(self.showMapAction)

        self.showReportAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            lan.get("viewReport", "Report"), self)
        self.showReportAction.setCheckable(True)
        self.showReportAction.triggered.connect(self.showReportView)
        self.viewGroup.addAction(self.showReportAction)

        self.showDashboardAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            lan.get("viewDashboard", "Variant comparison"), self)
        self.showDashboardAction.setCheckable(True)
        self.showDashboardAction.triggered.connect(self.showDashboardView)

        # Pulls one finished batch variant back into the standard viewport tabs
        self.batchVariantCombo = QComboBox()
        self.batchVariantCombo.setMinimumWidth(180)
        self.batchVariantCombo.setToolTip(lan.get("batchVariantSelector", "Batch variant"))
        # Shared profile switcher shown in the Simulation ribbon tab, mirrored by both docks
        self.ribbonProfileSelector = ProfileSelectorBar(lan, isCompact=True)

        self.loadBatchVariantAction = QAction(lan.get("batchLoadVariant", "Load variant into viewport"), self)
        self.loadBatchVariantAction.triggered.connect(self.loadSelectedBatchVariant)
        self.refreshBatchVariantSelector()
        self.viewGroup.addAction(self.showDashboardAction)

        # Layout action, the tooltip spells out what the short caption hides
        self.resetLayoutAction = QAction(lan.get("resetLayout", "Reset Layout"), self)
        self.resetLayoutAction.setToolTip(
            lan.get("resetLayoutTip", "Restore Default Window Layout"))
        self.resetLayoutAction.triggered.connect(self.resetLayout)

        # XML folding actions
        self.foldAllAction = QAction(lan.get("foldAll", "Fold all"), self)
        self.foldAllAction.triggered.connect(self.foldAllXml)
        self.unfoldAllAction = QAction(lan.get("unfoldAll", "Unfold all"), self)
        self.unfoldAllAction.triggered.connect(self.unfoldAllXml)

        # Report actions
        self.reportGeometryAction = QAction(lan.get("reportGeometry", "Report - Geometry"), self)
        self.reportGeometryAction.triggered.connect(self.generateGeometryReport)

        # Vehicle report menu, rebuilt whenever the active vehicle count or names change
        self.reportVehicleMenu = QMenu(self)
        self.reportVehicleButton = self.buildVehicleMenuButton(
            lan.get("vehicleReportButton", "Vehicle Report"), self.reportVehicleMenu)

        self.exportVehicleMenu = QMenu(self)
        self.exportVehicleButton = self.buildVehicleMenuButton(
            lan.get("vehicleExportButton", "Export Vehicle Report"), self.exportVehicleMenu)

        self.rebuildVehicleReportMenus()
        self.rebuildRecentProjectsMenu()

        self.exportGeometryReportAction = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            lan.get("exportGeometryReport", "Export Geometry Report"), self)
        self.exportGeometryReportAction.triggered.connect(self.exportGeometryReport)

        self.buildSeriesActions()

    # Create the checkable series visibility actions used by the View ribbon tab
    def buildSeriesActions(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        # Each entry maps an attribute name to its language key and handler
        seriesDefinitions = [
            ("toggleCantAction", "cant", self.toggleCantVisibility),
            ("toggleCantPossibleAction", "cant_possible", self.toggleCantPossibleVisibility),
            ("toggleCDef100Action", "cdef_100", self.toggleCDef100Visibility),
            ("toggleCDef130Action", "cdef_130", self.toggleCDef130Visibility),
            ("toggleCDef150Action", "cdef_150", self.toggleCDef150Visibility),
            ("toggleCDefKAction", "cdef_K", self.toggleCDefKVisibility),
            ("toggleCantDef100Action", "cant_def_100", self.toggleCantDef100Visibility),
            ("toggleCantDef130Action", "cant_def_130", self.toggleCantDef130Visibility),
            ("toggleCantDef150Action", "cant_def_150", self.toggleCantDef150Visibility),
            ("toggleCantDefKAction", "cant_def_K", self.toggleCantDefKVisibility),
            ("toggleCurvatureAction", "curvature", self.toggleCurvatureVisibility),
            ("toggleCurvatureBaselineAction", "curvature_baseline", self.toggleCurvatureBaselineVisibility),
            ("toggleSpeedAction", "speed_lim", self.toggleSpeedVisibility),
            ("toggleSpeed100Action", "speed_lim_100", self.toggleSpeed100Visibility),
            ("toggleSpeed130Action", "speed_lim_130", self.toggleSpeed130Visibility),
            ("toggleSpeed150Action", "speed_lim_150", self.toggleSpeed150Visibility),
            ("toggleSpeedKAction", "speed_lim_K", self.toggleSpeedKVisibility),
            ("toggleProfileAction", "profile", self.toggleProfileVisibility),
            ("toggleKinematicsSpeedLimitTrackAction", "kinematicsSpeedLimitTrack",
             self.toggleKinematicsSpeedLimitTrackVisibility),
            ("toggleKinematicsSpeedLimitTimeAction", "kinematicsSpeedLimitTime",
             self.toggleKinematicsSpeedLimitTimeVisibility),
            ("toggleKinematicsDistanceTimeAction", "kinematicsDistanceTime",
             self.toggleKinematicsDistanceTimeVisibility),
            ("toggleKinematicsForcesAction", "kinematicsForces",
             self.toggleKinematicsForcesVisibility),
        ]

        # Keyed by attribute name so updateTexts can retranslate them generically
        self.seriesActionKeys = {}

        for attributeName, languageKey, handler in seriesDefinitions:
            action = QAction(lan.get(languageKey, languageKey), self)

            # Every series toggles on its own, they are deliberately not exclusive
            action.setCheckable(True)
            action.setChecked(True)
            action.setProperty(SERIES_TOGGLE_PROPERTY, True)
            action.triggered.connect(handler)
            action.triggered.connect(
                lambda isChecked=False, toggledAction=action:
                self.announceSeriesToggle(toggledAction, isChecked))
            setattr(self, attributeName, action)
            self.seriesActionKeys[attributeName] = languageKey

    # Report the new visibility of a data series in the status bar
    def announceSeriesToggle(self, action, isChecked):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        stateText = (lan.get("seriesShown", "shown") if isChecked
                     else lan.get("seriesHidden", "hidden"))
        self.statusBarWidget.showMessage(f"{action.text()}: {stateText}",
                                         SERIES_STATUS_TIMEOUT)

    # Sync the units button's caption and tooltip to whichever unit system is currently active
    def updateUnitsActionLabel(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        isKmh = self.toggleUnitsAction.isChecked()
        caption = lan.get("unitsKmhShort", "km/h\nkm") if isKmh else lan.get("unitsMsShort", "m/s\nm")
        tooltip = lan.get("unitsKmhTip", "Units: km/h, km — click for m/s, m") if isKmh \
            else lan.get("unitsMsTip", "Units: m/s, m — click for km/h, km")
        self.toggleUnitsAction.setText(caption)
        self.toggleUnitsAction.setToolTip(tooltip)
        if getattr(self, "toggleUnitsButton", None) is not None:
            self.toggleUnitsButton.setText(caption)
            self.toggleUnitsButton.setToolTip(tooltip)

    # Refresh the button label and every view that displays a speed or a distance
    def onUnitsToggled(self, checked):
        self.updateUnitsActionLabel()
        self.refreshUnitDependentViews()
        self.markProjectModified()
        if getattr(self, "statusBarWidget", None) is not None:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            stateText = lan.get("unitsKmhTip", "Units: km/h, km") if checked \
                else lan.get("unitsMsTip", "Units: m/s, m")
            self.statusBarWidget.showMessage(stateText, SERIES_STATUS_TIMEOUT)

    # True while the km/h and km unit system is selected
    def isKmhUnits(self):
        return self.toggleUnitsAction.isChecked()

    # Caption of the active speed unit, shared by the reports and the map legend
    def speedUnitLabel(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        return lan.get("unitKmh", "km/h") if self.isKmhUnits() else lan.get("unitMs", "m/s")

    # Caption of the active distance unit
    def distanceUnitLabel(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        return lan.get("unitKm", "km") if self.isKmhUnits() else lan.get("unitM", "m")

    # Turn an internal km/h speed into the displayed unit
    def convertSpeedForDisplay(self, speedKmh):
        return float(speedKmh) if self.isKmhUnits() else float(speedKmh) / 3.6

    # Every plot axis, table column, readout and report that carries a unit
    def refreshUnitDependentViews(self):
        useKmh = self.isKmhUnits()
        self.graphsWidget.setUnitSystem(useKmh)
        self.profileWidget.setUnitSystem(useKmh)
        self.kinematicsWidget.setUnitSystem(useKmh)
        self.graphsWidget.updateLabels(self.translationManager.getLanguage(self.currentLanguage))

        self.plotKinematics()
        self.plotCant()
        self.plotSpeedLimits()
        self.mapWidget.setUnitSystem(useKmh)
        self.updateMapWithSpeeds()
        self.refreshGeometryReport()
        self.refreshVehicleReport()
        self.refreshSlewReportWindow()

    # Give every ribbon action a generated vector icon or a short text badge
    def applyActionIcons(self):
        for attributeName, iconName in ACTION_ICONS.items():
            action = getattr(self, attributeName, None)
            if action is not None:
                action.setIcon(icons.makeIcon(iconName))

        for attributeName, badgeText in SERIES_BADGES.items():
            action = getattr(self, attributeName, None)
            if action is not None:
                action.setIcon(icons.makeBadge(badgeText))

        for dock in self.allDocks():
            dock.toggleViewAction().setIcon(icons.makeIcon("panel"))

    # Every dock of the main window in a stable order, empty before buildDocks runs
    def allDocks(self):
        dockNames = ("dockWorkflow", "dockGraphs", "dockProfile", "dockKinematics",
                     "dockTrackStats", "dockLandXmlRaw", "dockLandXmlParsed", "dockTtpRaw",
                     "dockTtpParsed", "dockHelp")
        return tuple(getattr(self, name) for name in dockNames if hasattr(self, name))

    # Build the central stacked viewport holding the map and the report page
    def buildCentralViews(self):
        self.centralStack = QStackedWidget()

        # View 1 is the interactive alignment map
        self.mapWidget = MapWidget(self, self.translationManager.getLanguage(self.currentLanguage))
        self.mapWidget.mapFailed.connect(self.onMapFailed)
        self.centralStack.addWidget(self.mapWidget)

        # View 2 is the generated calculation report
        reportPage = QWidget()
        reportLayout = QVBoxLayout(reportPage)
        reportLayout.setContentsMargins(0, 0, 0, 0)
        reportLayout.setSpacing(0)

        self.reportSplitter = QSplitter(Qt.Orientation.Horizontal)
        self.reportGeometryWidget = QPlainTextEdit()
        self.reportGeometryWidget.setReadOnly(True)
        self.reportSplitter.addWidget(self.reportGeometryWidget)
        self.reportVehicleTable = pg.TableWidget(sortable=False)
        self.reportSplitter.addWidget(self.reportVehicleTable)
        reportLayout.addWidget(self.reportSplitter)

        self.centralStack.addWidget(reportPage)

        # View 3 is the variant comparison dashboard, populated once a batch has run
        self.variantDashboardWidget = VariantDashboardWidget(self.translationManager.getLanguage(self.currentLanguage))
        self.centralStack.addWidget(self.variantDashboardWidget)

        self.setCentralWidget(self.centralStack)

    # Build every dockable panel and arrange the default layout
    def buildDocks(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        self.setDockNestingEnabled(True)
        self.setDockOptions(QMainWindow.DockOption.AllowNestedDocks |
                            QMainWindow.DockOption.AllowTabbedDocks |
                            QMainWindow.DockOption.AnimatedDocks)

        # Dock 1 - interactive workflow guide
        self.workflowWidget = WorkflowStepperWidget(lan)
        self.workflowWidget.stepTriggered.connect(self.onWorkflowStep)
        self.dockWorkflow = LazyDockWidget(lan.get("dockWorkflow", "Workflow"), "dockWorkflow")
        self.dockWorkflow.setWidget(self.workflowWidget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dockWorkflow)

        # XML source viewers with folding support
        self.textboxRawLandXML = XmlCodeEditor()
        self.dockLandXmlRaw = LazyDockWidget(lan.get("dockLandXmlRaw", "LandXML - source"),
                                             "dockLandXmlRaw")
        self.dockLandXmlRaw.setWidget(self.textboxRawLandXML)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dockLandXmlRaw)

        self.textboxRawTTP = XmlCodeEditor()
        self.dockTtpRaw = LazyDockWidget(lan.get("dockTtpRaw", "XML TTP - source"), "dockTtpRaw")
        self.dockTtpRaw.setWidget(self.textboxRawTTP)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dockTtpRaw)

        # Parsed XML tables
        self.tableLandXML = pg.TableWidget(sortable=False)
        self.dockLandXmlParsed = LazyDockWidget(lan.get("dockLandXmlParsed", "LandXML - data"),
                                                "dockLandXmlParsed", self.renderTableLandXML)
        self.dockLandXmlParsed.setWidget(self.tableLandXML)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dockLandXmlParsed)

        self.tableTTP = pg.TableWidget(sortable=False)
        self.dockTtpParsed = LazyDockWidget(lan.get("dockTtpParsed", "XML TTP - data"),
                                            "dockTtpParsed")
        self.dockTtpParsed.setWidget(self.tableTTP)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dockTtpParsed)

        # Dock 2 - linked track geometry and speed profile graphs, headed by the shared profile switcher
        self.graphsWidget = PerformanceGraphsWidget(lan)
        self.graphsProfileSelector = ProfileSelectorBar(lan)
        graphsContainer = QWidget()
        graphsContainerLayout = QVBoxLayout(graphsContainer)
        graphsContainerLayout.setContentsMargins(4, 2, 4, 0)
        graphsContainerLayout.setSpacing(2)
        graphsContainerLayout.addWidget(self.graphsProfileSelector)
        graphsContainerLayout.addWidget(self.graphsWidget, 1)
        self.dockGraphs = LazyDockWidget(lan.get("dockGraphs", "Track geometry and speed profile"),
                                         "dockGraphs", self.refreshGraphsDock)
        self.dockGraphs.setWidget(graphsContainer)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dockGraphs)

        # Remaining plot docks, all rendered with pyqtgraph
        self.profileWidget = ProfilePlotWidget(lan)
        self.dockProfile = LazyDockWidget(lan.get("dockProfile", "Plots - Profile"),
                                          "dockProfile", self.renderProfile)
        self.dockProfile.setWidget(self.profileWidget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockProfile)

        self.kinematicsWidget = KinematicsPlotWidget(lan)
        self.dockKinematics = LazyDockWidget(lan.get("dockKinematics", "Plots - Kinematics"),
                                             "dockKinematics", self.renderKinematics)
        self.dockKinematics.setWidget(self.kinematicsWidget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockKinematics)

        # Track length, design/actual speed maxima and travel time summary
        self.trackStatsWidget = TrackStatisticsWidget(lan)
        self.dockTrackStats = LazyDockWidget(lan.get("dockTrackStats", "Track Statistics"),
                                             "dockTrackStats", self.refreshTrackStatsDock)
        self.dockTrackStats.setWidget(self.trackStatsWidget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockTrackStats)

        # Documentation panel rendering the project README
        self.helpWidget = HelpWidget(lan)
        self.dockHelp = LazyDockWidget(lan.get("dockHelp", "Help"), "dockHelp")
        self.dockHelp.setWidget(self.helpWidget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockHelp)
        self.dockHelp.hide()

        # Group related docks into tab stacks so the default layout stays readable
        self.tabifyDockWidget(self.dockLandXmlRaw, self.dockTtpRaw)
        self.tabifyDockWidget(self.dockLandXmlParsed, self.dockTtpParsed)
        self.tabifyDockWidget(self.dockLandXmlParsed, self.dockGraphs)
        self.tabifyDockWidget(self.dockProfile, self.dockKinematics)
        self.tabifyDockWidget(self.dockProfile, self.dockTrackStats)
        self.tabifyDockWidget(self.dockProfile, self.dockHelp)

        self.dockLandXmlRaw.raise_()
        self.dockGraphs.raise_()
        self.dockProfile.raise_()

        # Every dock builds its own title bar menu from the active translations
        for dock in self.allDocks():
            dock.setLanguage(lan)

        # Snapshot of the freshly built arrangement used by the reset action
        self.defaultLayoutState = self.saveState()
        self.defaultGeometry = self.saveGeometry()

    # Assemble the ribbon tabs from the previously created actions
    def buildRibbon(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        self.ribbonBar = RibbonBar()

        projectPage = self.ribbonBar.addPage("project", lan.get("ribbonProject", "Project"),
                                             "ribbonProject")
        projectGroup = projectPage.addGroup(lan.get("groupProject", "Project"), "groupProject")
        projectGroup.addAction(self.newProjectAction, shortKey="shortNewProject")
        projectGroup.addAction(self.openProjectAction, shortKey="shortOpenProject")
        projectGroup.addAction(self.saveProjectAction, shortKey="shortSaveProject")
        projectGroup.addAction(self.saveProjectAsAction, shortKey="shortSaveProjectAs")
        projectGroup.addAction(self.projectPropertiesAction, shortKey="shortProjectProperties")
        projectGroup.addWidget(self.recentProjectsButton)

        openGroup = projectPage.addGroup(lan.get("groupOpen", "Open"), "groupOpen")
        openGroup.addAction(self.autodetectXMLAction, shortKey="shortAutodetect")
        openGroup.addAction(self.openParseLandXMLAction, shortKey="shortLandxml")
        openGroup.addAction(self.openParseXMLTTPAction, shortKey="shortTtp")
        openGroup.addAction(self.openFileAction, shortKey="shortOpenFile")

        appendGroup = projectPage.addGroup(lan.get("groupAppend", "Append"), "groupAppend")
        appendGroup.addAction(self.appendAutodetectXMLAction, shortKey="shortAutodetect")
        appendGroup.addAction(self.appendLandXMLAction, shortKey="shortLandxml")
        appendGroup.addAction(self.appendXMLTTPAction, shortKey="shortTtp")

        cleanGroup = projectPage.addGroup(lan.get("groupClean", "Clean"), "groupClean")
        cleanGroup.addAction(self.cleanDataAction, shortKey="shortCleanAll")
        cleanGroup.addAction(self.cleanLandXMLDataAction, shortKey="shortLandxml")
        cleanGroup.addAction(self.cleanTTPDataAction, shortKey="shortTtp")
        cleanGroup.addAction(self.openPurgeDialogAction, shortKey="shortPurge")

        projectExportGroup = projectPage.addGroup(lan.get("groupExport", "Export"), "groupExport")
        projectExportGroup.addAction(self.exportLandXmlAction, shortKey="shortExportLandXml")

        exitGroup = projectPage.addGroup(lan.get("groupSession", "Session"), "groupSession")
        exitGroup.addAction(self.helpAction, shortKey="shortHelp")
        exitGroup.addAction(self.openCoypuFeederAction, shortKey="shortCoypuFeeder")
        exitGroup.addAction(self.exitAction, shortKey="shortExit")

        geometryPage = self.ribbonBar.addPage("geometry", lan.get("ribbonGeometry", "Geometry"),
                                              "ribbonGeometry")
        calculateGroup = geometryPage.addGroup(lan.get("groupCalculate", "Calculate"),
                                               "groupCalculate")
        calculateGroup.addAction(self.calculateGeometryAction, shortKey="shortCalcDesign")
        calculateGroup.addAction(self.calculateGeometryIAction, shortKey="shortCalcAsBuilt")

        geometryCleanGroup = geometryPage.addGroup(lan.get("groupClean", "Clean"), "groupClean")
        geometryCleanGroup.addAction(self.cleanCalculatedCantsAction, shortKey="shortCleanCants")
        geometryCleanGroup.addAction(self.cleanCalculatedSpeedsAction, shortKey="shortCleanSpeeds")

        geometryConfigGroup = geometryPage.addGroup(lan.get("groupConfig", "Configuration"),
                                                    "groupConfig")
        geometryConfigGroup.addAction(self.geometrySettingsAction, shortKey="shortLimits")
        geometryConfigGroup.addAction(self.designApproachAction, shortKey="shortApproach")
        geometryConfigGroup.addAction(self.speedSettingsAction, shortKey="shortSpeeds")

        optimizeGroup = geometryPage.addGroup(lan.get("groupOptimize", "Optimization"), "groupOptimize")
        optimizeGroup.addAction(self.alignmentOptimizationAction, shortKey="shortOptimize")
        self.clearOptimizationButton = optimizeGroup.addAction(self.clearOptimizationAction,
                                                               shortKey="shortClearOptimize")
        # Marks the button for the soft red tint the ribbon stylesheet applies while it is enabled
        self.clearOptimizationButton.setProperty(DESTRUCTIVE_BUTTON_PROPERTY, True)
        optimizeGroup.addAction(self.slewReportAction, shortKey="shortSlewReport")
        optimizeGroup.addAction(self.toggleSlewPlotAction, shortKey="shortToggleSlewPlot")

        geometryReportGroup = geometryPage.addGroup(lan.get("groupReport", "Report"), "groupReport")
        geometryReportGroup.addAction(self.reportGeometryAction, shortKey="shortReport")
        geometryReportGroup.addAction(self.exportGeometryReportAction, shortKey="shortExport")
        geometryReportGroup.addAction(self.includeSlewSectionAction, isLarge=False,
                                      shortKey="shortIncludeSlew")

        simulationPage = self.ribbonBar.addPage("simulation", lan.get("ribbonSimulation", "Simulation"),
                                                "ribbonSimulation")
        runGroup = simulationPage.addGroup(lan.get("groupCalculate", "Calculate"), "groupCalculate")
        runGroup.addAction(self.calculateTrainSpeedAction, shortKey="shortRunSimulation")
        runGroup.addAction(self.reverseDirectionAction, isLarge=False, shortKey="shortRunDirection")

        simulationProfileGroup = simulationPage.addGroup(lan.get("groupProfile", "Speed profile"),
                                                        "groupProfile")
        simulationProfileGroup.addWidget(self.ribbonProfileSelector)

        simulationConfigGroup = simulationPage.addGroup(lan.get("groupConfig", "Configuration"),
                                                        "groupConfig")
        simulationConfigGroup.addAction(self.vehicleSettingsAction, shortKey="shortVehicles")
        simulationConfigGroup.addAction(self.openVehicleCatalogAction, shortKey="shortVehicleCatalog")
        simulationConfigGroup.addAction(self.stopsSettingsAction, shortKey="shortStops")
        self.toggleUnitsButton = simulationConfigGroup.addAction(self.toggleUnitsAction)

        simulationReportGroup = simulationPage.addGroup(lan.get("groupReport", "Report"), "groupReport")
        simulationReportGroup.addWidget(self.reportVehicleButton)

        simulationExportGroup = simulationPage.addGroup(lan.get("groupExport", "Export"), "groupExport")
        simulationExportGroup.addWidget(self.exportVehicleButton)

        batchPage = self.ribbonBar.addPage("batch", lan.get("ribbonBatch", "Batch"), "ribbonBatch")
        batchRunGroup = batchPage.addGroup(lan.get("groupBatchRun", "Run"), "groupBatchRun")
        batchRunGroup.addAction(self.openBatchProcessingAction, shortKey="shortBatch")
        batchCompareGroup = batchPage.addGroup(lan.get("groupBatchCompare", "Compare"), "groupBatchCompare")
        batchCompareGroup.addAction(self.showDashboardAction, shortKey="shortDashboard")
        batchExportGroup = batchPage.addGroup(lan.get("groupBatchExport", "Export"), "groupBatchExport")
        batchExportGroup.addAction(self.exportBatchArchiveAction, shortKey="shortBatchExport")

        viewPage = self.ribbonBar.addPage("view", lan.get("ribbonView", "View"), "ribbonView")
        centralGroup = viewPage.addGroup(lan.get("groupCentral", "Central view"), "groupCentral")
        centralGroup.addAction(self.showMapAction, shortKey="viewMap")
        centralGroup.addAction(self.showReportAction, shortKey="viewReport")
        centralGroup.addAction(self.showDashboardAction, shortKey="viewDashboard")

        batchInspectorGroup = viewPage.addGroup(lan.get("batchVariantSelector", "Batch variant"),
                                                "batchVariantSelector")
        batchInspectorGroup.addWidget(self.batchVariantCombo)
        batchInspectorGroup.addAction(self.loadBatchVariantAction, shortKey="batchLoadVariant")

        panelsGroup = viewPage.addGroup(lan.get("groupPanels", "Panels"), "groupPanels")
        panelShortKeys = ("shortPanelWorkflow", "shortPanelGraphs", "shortPanelProfile",
                          "shortPanelKinematics", "shortPanelTrackStats", "shortPanelLandxmlRaw",
                          "shortPanelLandxmlData", "shortPanelTtpRaw", "shortPanelTtpData",
                          "shortPanelHelp")
        for dock, shortKey in zip(self.allDocks(), panelShortKeys):
            panelsGroup.addAction(dock.toggleViewAction(), isLarge=False, shortKey=shortKey)

        layoutGroup = viewPage.addGroup(lan.get("groupLayout", "Layout"), "groupLayout")
        layoutGroup.addAction(self.resetLayoutAction, isLarge=False, shortKey="shortResetLayout")
        layoutGroup.addAction(self.foldAllAction, isLarge=False, shortKey="foldAll")
        layoutGroup.addAction(self.unfoldAllAction, isLarge=False, shortKey="unfoldAll")

        seriesPage = self.ribbonBar.addPage("series", lan.get("groupSeries", "Data series"),
                                            "groupSeries")
        cantSeriesGroup = seriesPage.addGroup(lan.get("groupSeriesCant", "Cant"), "groupSeriesCant")
        for attributeName in ("toggleCantAction", "toggleCantPossibleAction", "toggleCDef100Action",
                              "toggleCDef130Action", "toggleCDef150Action", "toggleCDefKAction",
                              "toggleCantDef100Action", "toggleCantDef130Action",
                              "toggleCantDef150Action", "toggleCantDefKAction",
                              "toggleCurvatureAction", "toggleCurvatureBaselineAction"):
            cantSeriesGroup.addAction(getattr(self, attributeName), isLarge=False,
                                      shortKey=SERIES_SHORT_KEYS[attributeName])

        speedSeriesGroup = seriesPage.addGroup(lan.get("groupSeriesSpeed", "Speed"),
                                               "groupSeriesSpeed")
        for attributeName in ("toggleSpeedAction", "toggleSpeed100Action", "toggleSpeed130Action",
                              "toggleSpeed150Action", "toggleSpeedKAction", "toggleProfileAction"):
            speedSeriesGroup.addAction(getattr(self, attributeName), isLarge=False,
                                       shortKey=SERIES_SHORT_KEYS[attributeName])

        kinematicsSeriesGroup = seriesPage.addGroup(lan.get("plotsKinematics", "Kinematics"),
                                                    "plotsKinematics")
        for attributeName in ("toggleKinematicsSpeedLimitTrackAction",
                              "toggleKinematicsSpeedLimitTimeAction",
                              "toggleKinematicsDistanceTimeAction",
                              "toggleKinematicsForcesAction"):
            kinematicsSeriesGroup.addAction(getattr(self, attributeName), isLarge=False,
                                            shortKey=SERIES_SHORT_KEYS[attributeName])

        settingsPage = self.ribbonBar.addPage("settings", lan.get("ribbonSettings", "Settings"),
                                              "ribbonSettings")
        themeGroup = settingsPage.addGroup(lan.get("groupTheme", "Theme"), "groupTheme")
        themeGroup.addAction(self.themeAutoAction, isLarge=False, shortKey="shortThemeAuto")
        themeGroup.addAction(self.themeLightAction, isLarge=False, shortKey="shortThemeLight")
        themeGroup.addAction(self.themeDarkAction, isLarge=False, shortKey="shortThemeDark")

        languageGroup = settingsPage.addGroup(lan.get("groupLanguage", "Language"), "groupLanguage")
        for languageAction in self.languageActions.values():
            languageGroup.addAction(languageAction, isLarge=False)

        settingsConfigGroup = settingsPage.addGroup(lan.get("groupConfig", "Configuration"),
                                                    "groupConfig")
        settingsConfigGroup.addAction(self.mapSettingsAction, shortKey="shortMap")
        settingsConfigGroup.addAction(self.vehicleSettingsAction, shortKey="shortVehicles")
        settingsConfigGroup.addAction(self.stopsSettingsAction, shortKey="shortStops")
        settingsConfigGroup.addAction(self.geometrySettingsAction, shortKey="shortLimits")
        settingsConfigGroup.addAction(self.openShortcutSettingsAction, shortKey="shortShortcuts")

        presetsGroup = settingsPage.addGroup(lan.get("groupPresets", "Presets"), "groupPresets")
        presetsGroup.addAction(self.exportPresetsAction, shortKey="shortExport")
        presetsGroup.addAction(self.importPresetsAction, shortKey="shortImport")

        # The ribbon replaces the classic menu bar at the top of the window
        self.setMenuWidget(self.ribbonBar)

    # Build the status bar showing engine state, chainage and active theme
    def buildStatusBar(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        self.statusBarWidget = QStatusBar()
        self.setStatusBar(self.statusBarWidget)

        self.statusEngineLabel = QLabel()
        self.statusChainageLabel = QLabel()
        self.statusThemeLabel = QLabel()

        # Non modal progress of a running simulation, hidden whenever no run is in flight
        self.statusSimulationProgress = QProgressBar()
        self.statusSimulationProgress.setMaximumWidth(140)
        self.statusSimulationProgress.setTextVisible(False)
        self.statusSimulationProgress.hide()

        self.statusBarWidget.addWidget(self.statusEngineLabel, 1)
        self.statusBarWidget.addPermanentWidget(self.statusSimulationProgress)
        self.statusBarWidget.addPermanentWidget(self.statusChainageLabel)
        self.statusBarWidget.addPermanentWidget(self.statusThemeLabel)

        self.commandLineEdit = QLineEdit()
        self.commandLineEdit.setPlaceholderText(lan.get("commandBarPlaceholder", "Command..."))
        self.commandLineEdit.setMaximumWidth(200)
        self.commandLineEdit.returnPressed.connect(self.executeCommandLine)
        self.statusBarWidget.addPermanentWidget(self.commandLineEdit)

        self.setEngineStatus(lan.get("statusReady", "Ready"))
        self.updateStatusChainage(None)

    # Connect the crosshair signals so graphs, profile, map and status bar stay in sync
    def connectCursorSignals(self):
        self.graphsWidget.cursorMoved.connect(self.onCursorMoved)
        self.profileWidget.cursorMoved.connect(self.onCursorMoved)
        self.mapWidget.cursorMoved.connect(self.onCursorMoved)
        self.variantDashboardWidget.cursorMoved.connect(self.onCursorMoved)

    # Keep the map settings dialog and the floating map controls in agreement
    def connectMapSignals(self):
        self.mapWidget.controlsPanel.drawModeChanged.connect(self.onMapDrawModeChanged)
        self.mapWidget.setStations(self.collectStations())

    # Remember the style chosen from the floating map controls
    def onMapDrawModeChanged(self, drawMode):
        self.dataStorage.setdefault("settingsData", {})["mapDrawMode"] = drawMode

    # Push the scheduled stops into every view that can show them
    def refreshStations(self):
        stations = self.collectStations()
        self.mapWidget.setStations(stations)
        self.graphsWidget.setStations(stations)
        self.profileWidget.setStations(stations)
        self.dockTrackStats.requestUpdate()

    # Propagate a chainage to every view regardless of which one produced it
    def onCursorMoved(self, stationKm):
        self.updateStatusChainage(stationKm)
        self.graphsWidget.setCursorStation(stationKm)
        self.profileWidget.setCursorStation(stationKm)
        self.mapWidget.setCursorStation(stationKm)
        self.variantDashboardWidget.setCursorStation(stationKm)

    # Render the chainage readout in the status bar
    def updateStatusChainage(self, stationKm):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        label = lan.get("statusChainage", "Chainage")
        if stationKm is None:
            self.statusChainageLabel.setText(f"{label}: -")
            return

        if self.isKmhUnits():
            self.statusChainageLabel.setText(f"{label}: {stationKm:.3f} {self.distanceUnitLabel()}")
        else:
            self.statusChainageLabel.setText(
                f"{label}: {stationKm * 1000.0:.1f} {self.distanceUnitLabel()}")

    # Render the core engine state in the status bar
    def setEngineStatus(self, text):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.statusEngineLabel.setText(f'{lan.get("statusEngine", "Engine")}: {text}')

    # Resolve and trigger a typed alias or command name, showing feedback in the status bar
    def runTypedCommand(self, typedText):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        if self.shortcutManager.executeTypedCommand(self, typedText):
            self.statusBarWidget.showMessage(
                f'{lan.get("commandExecuted", "Command executed:")} {typedText}', SERIES_STATUS_TIMEOUT)
        else:
            self.statusBarWidget.showMessage(
                f'{lan.get("commandUnknown", "Unknown command:")} {typedText}', SERIES_STATUS_TIMEOUT)

    # Resolve and trigger a typed alias or command name from the AutoCAD-style command bar
    def executeCommandLine(self):
        typedText = self.commandLineEdit.text()
        self.runTypedCommand(typedText)
        self.commandLineEdit.clear()

    # Build the floating HUD command input and install the global keypress interceptor
    def buildFloatingCommandInput(self):
        self.floatingCommandInput = FloatingCommandInput(self.shortcutManager, self)
        self.floatingCommandInput.commandSubmitted.connect(self.runTypedCommand)
        QApplication.instance().installEventFilter(self)

    # Types of focused widgets that already accept free text, never hijacked by the floating HUD
    def isTextEntryWidget(self, widget):
        textEntryTypes = (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractItemView)
        return isinstance(widget, textEntryTypes)

    # Decide whether a keypress should open the floating command HUD instead of reaching its widget
    def shouldInterceptForFloatingInput(self, event):
        if not self.shortcutManager.floatingInputEnabled:
            return False
        if QApplication.activeModalWidget() is not None:
            return False
        if event.modifiers() not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        if not event.text().isalnum():
            return False
        return not self.isTextEntryWidget(QApplication.focusWidget())

    # Show the floating HUD near the cursor, seeded with the character that triggered it
    def startFloatingCommandInput(self, initialCharacter):
        self.floatingCommandInput.openAt(QCursor.pos(), initialCharacter)

    # Intercept alphanumeric keypresses application-wide to launch the floating command HUD
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and self.shouldInterceptForFloatingInput(event):
            self.startFloatingCommandInput(event.text())
            return True
        return super().eventFilter(watched, event)

    # Render the active theme name in the status bar
    def updateStatusTheme(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        modeLabels = {
            theme_manager.MODE_AUTO: lan.get("themeAuto", "System default (auto)"),
            theme_manager.MODE_LIGHT: lan.get("themeLight", "Always light"),
            theme_manager.MODE_DARK: lan.get("themeDark", "Always dark"),
        }
        activeName = lan.get("dark", "Dark") if self.themeManager.isDarkActive else lan.get("light", "Light")
        modeName = modeLabels.get(self.themeManager.currentMode, activeName)
        self.statusThemeLabel.setText(f'{lan.get("statusTheme", "Theme")}: {modeName}')

    # Apply a theme mode and remember the choice for the next session
    def applyThemeMode(self, mode):
        self.themeManager.applyTheme(mode)
        self.appSettings.setValue("theme/mode", mode)

    # React to a theme switch by restyling widgets that hold their own colours
    def onThemeChanged(self, mode):
        isDark = self.themeManager.isDarkActive
        tokens = self.themeManager.currentTokens

        # Icons are regenerated so their strokes match the new foreground colour
        icons.iconFactory.applyTheme(tokens)
        self.applyActionIcons()

        for editor in (self.textboxRawLandXML, self.textboxRawTTP):
            editor.applyTheme(isDark, tokens)

        self.workflowWidget.applyTheme(isDark, tokens)
        for profileSelector in self.profileSelectors():
            profileSelector.applyTheme(isDark, tokens)
        self.graphsWidget.applyTheme(isDark, tokens)
        self.profileWidget.applyTheme(isDark, tokens)
        self.kinematicsWidget.applyTheme(isDark, tokens)
        self.trackStatsWidget.applyTheme(isDark, tokens)
        self.helpWidget.applyTheme(isDark, tokens)
        self.mapWidget.applyTheme(isDark, tokens)
        self.variantDashboardWidget.applyTheme(isDark, tokens)
        self.updateStatusTheme()

    # Switch the central viewport to the map page
    # A page or script failure belongs in the status bar, it is not the user's mistake
    def onMapFailed(self, message):
        self.setEngineStatus(message)

    def showMapView(self):
        self.centralStack.setCurrentIndex(VIEW_MAP)
        self.showMapAction.setChecked(True)

    # Switch the central viewport to the report page
    def showReportView(self):
        # A background refresh rebuilds the text without pulling the user away from their current view
        if self.isReportRefreshSilent:
            return
        self.centralStack.setCurrentIndex(VIEW_REPORT)
        self.showReportAction.setChecked(True)

    # Switch the central viewport to the variant comparison dashboard
    def showDashboardView(self):
        self.centralStack.setCurrentIndex(VIEW_DASHBOARD)
        self.showDashboardAction.setChecked(True)

    # Collapse every node in both XML source viewers
    def foldAllXml(self):
        self.textboxRawLandXML.foldAll()
        self.textboxRawTTP.foldAll()

    # Expand every node in both XML source viewers
    def unfoldAllXml(self):
        self.textboxRawLandXML.unfoldAll()
        self.textboxRawTTP.unfoldAll()

    # Push the current data into the linked track geometry and speed graphs
    def refreshGraphsDock(self):
        lxml = self.dataStorage.get("LandXML", {})
        self.graphsWidget.setUnitSystem(self.isKmhUnits())
        self.graphsWidget.setStations(self.collectStations())
        self.graphsWidget.updateGeometryData(lxml, self.seriesVisibility())
        self.graphsWidget.setActiveProfileKey(self.profileState.activeProfileKey)
        self.graphsWidget.updateSpeedData(self.dataStorage, self.seriesVisibility())
        self.graphsWidget.updateSlewData(lxml, self.optimizationEnvelopeM())

    # Configured d_max of the applied optimization, drives the slew plot threshold lines
    def optimizationEnvelopeM(self):
        summary = self.dataStorage.get("LandXML", {}).get("optimizationSummary") or {}
        return summary.get("dMaxM")

    # Everything that must follow a finished calculation, wired to both calculation signals
    def onCalculationFinished(self):
        self.profileState.refreshAvailability(self.dataStorage)
        self.refreshOptimizationImpact()
        self.refreshGeometryReport()
        self.refreshVehicleReport()
        self.refreshTrackStatsDock()

    # Rebuild the geometry report in place, but only once the user has actually opened it
    def refreshGeometryReport(self):
        if not self.lastGeometryReportLines:
            return
        self.isReportRefreshSilent = True
        try:
            self.generateGeometryReport()
        finally:
            self.isReportRefreshSilent = False

    # Rebuild the vehicle report in place for whichever vehicle was last shown
    def refreshVehicleReport(self):
        if self.lastVehicleReportIndex is None:
            return
        self.isReportRefreshSilent = True
        try:
            self.generateVehicleReport(self.lastVehicleReportIndex)
        finally:
            self.isReportRefreshSilent = False

    # Recompute the Track Statistics dock from the current data storage
    def refreshTrackStatsDock(self):
        self.trackStatsWidget.updateStatistics(self.dataStorage, self.getVehicleName,
                                               self.isKmhUnits(),
                                               self.profileState.activeProfileKey)

    # Map every series toggle action onto the series key used by the plots
    def seriesVisibility(self):
        visibilityKeys = {
            "cant": self.toggleCantAction,
            "cantPossible": self.toggleCantPossibleAction,
            "cDef100": self.toggleCDef100Action,
            "cDef130": self.toggleCDef130Action,
            "cDef150": self.toggleCDef150Action,
            "cDefK": self.toggleCDefKAction,
            "cantDef100": self.toggleCantDef100Action,
            "cantDef130": self.toggleCantDef130Action,
            "cantDef150": self.toggleCantDef150Action,
            "cantDefK": self.toggleCantDefKAction,
            "curvature": self.toggleCurvatureAction,
            "curvatureBaseline": self.toggleCurvatureBaselineAction,
            "speedLimits": self.toggleSpeedAction,
            "speedLimits100": self.toggleSpeed100Action,
            "speedLimits130": self.toggleSpeed130Action,
            "speedLimits150": self.toggleSpeed150Action,
            "speedLimitsK": self.toggleSpeedKAction,
            "kinematicsSpeedLimitTrack": self.toggleKinematicsSpeedLimitTrackAction,
            "kinematicsSpeedLimitTime": self.toggleKinematicsSpeedLimitTimeAction,
            "kinematicsDistanceTime": self.toggleKinematicsDistanceTimeAction,
            "kinematicsForces": self.toggleKinematicsForcesAction,
        }
        return {seriesKey: action.isChecked() for seriesKey, action in visibilityKeys.items()}

    # Scheduled stops are entered against the imported chainage, so they follow the active alignment
    def projectedTrainStops(self):
        lxml = self.dataStorage.get("LandXML", {})
        projectedStops = []
        for stop in self.dataStorage.get("settingsData", {}).get("trainStops", []):
            projectedStop = list(stop)
            try:
                projectedStop[0] = geometry_engine.projectChainageKm(lxml, float(stop[0]))
            except (IndexError, ValueError, TypeError):
                continue
            projectedStops.append(projectedStop)
        return projectedStops

    # Build the chainage and name pairs of every scheduled stop, on the active stationing
    def collectStations(self):
        stations = []
        for stop in self.projectedTrainStops():
            try:
                stationKm = float(stop[0])
            except (IndexError, ValueError, TypeError):
                continue
            stations.append((stationKm, str(stop[2]) if len(stop) > 2 else ""))
        return stations

    # Dispatchers keep the existing call sites while honouring the lazy docks
    def plotCant(self):
        self.dockGraphs.requestUpdate()
        self.dockTrackStats.requestUpdate()

    def plotCurvature(self):
        self.dockGraphs.requestUpdate()

    def plotSpeedLimits(self):
        self.dockGraphs.requestUpdate()
        self.dockTrackStats.requestUpdate()

    def plotProfile(self):
        self.dockProfile.requestUpdate()

    def plotKinematics(self):
        self.dockKinematics.requestUpdate()
        self.dockGraphs.requestUpdate()
        self.dockTrackStats.requestUpdate()

    # Run the action belonging to a workflow step and mark it as completed
    def onWorkflowStep(self, stepIndex):
        # Phase 2 sits between the imports and the cant design, and is skippable
        stepHandlers = [
            self.openLandXML,
            self.openXMLTTP,
            self.openStopsSettings,
            self.openVehicleSettings,
            self.openAlignmentOptimization,
            self.calculateGeometry,
            self.calculateTrainSpeed,
            self.exportGeometryReport,
        ]
        if 0 <= stepIndex < len(stepHandlers):
            stepHandlers[stepIndex]()
            self.workflowWidget.markCompleted(stepIndex)

    # Restore geometry, dock state, theme and language from the previous session
    def restoreSession(self):
        savedLanguage = self.appSettings.value("ui/language", "en")
        if savedLanguage in self.translationManager.availableLanguageCodes():
            self.currentLanguage = savedLanguage

        savedGeometry = self.appSettings.value("layout/geometry")
        if savedGeometry is not None:
            self.restoreGeometry(savedGeometry)

        savedState = self.appSettings.value("layout/state")
        if savedState is not None:
            self.restoreState(savedState)

        savedMode = self.appSettings.value("theme/mode", theme_manager.MODE_AUTO)
        if savedMode not in (theme_manager.MODE_AUTO, theme_manager.MODE_LIGHT,
                             theme_manager.MODE_DARK):
            savedMode = theme_manager.MODE_AUTO

        for action in self.themeGroup.actions():
            action.setChecked(action.data() == savedMode)

        self.themeManager.applyTheme(savedMode)

        savedUnitsKmh = self.appSettings.value("units/kmh", False, type=bool)
        self.toggleUnitsAction.setChecked(savedUnitsKmh)

        self.updateTexts()

    # Persist geometry and dock state so the next launch reopens the same layout
    def saveSession(self):
        self.appSettings.setValue("layout/geometry", self.saveGeometry())
        self.appSettings.setValue("layout/state", self.saveState())
        self.appSettings.setValue("ui/language", self.currentLanguage)
        self.appSettings.setValue("theme/mode", self.themeManager.currentMode)
        self.appSettings.setValue("units/kmh", self.toggleUnitsAction.isChecked())


    # Window title carries the project file name and an asterisk while changes are unsaved
    def updateWindowTitle(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        projectName = (Path(self.currentProjectPath).name if self.currentProjectPath
                       else lan.get("untitledProject", "Untitled.coypu"))
        title = f"{lan['app_title']} - {projectName}"
        if self.isProjectModified:
            title += " *"
        self.setWindowTitle(title)

    # Flag the project as dirty, called by every operation that changes persisted state
    def markProjectModified(self):
        if not self.isProjectModified:
            self.isProjectModified = True
            self.updateWindowTitle()

    # Clear the dirty flag after a successful save, a load or a fresh project
    def clearProjectModified(self):
        self.isProjectModified = False
        self.updateWindowTitle()

    # Switch the central viewport to a saved index, keeping the ribbon toggle in sync
    def restoreCentralView(self, viewIndex):
        viewHandlers = {VIEW_MAP: self.showMapView, VIEW_REPORT: self.showReportView,
                        VIEW_DASHBOARD: self.showDashboardView}
        viewHandlers.get(viewIndex, self.showMapView)()

    # Extended project metadata, reachable from the ribbon, the HUD and every new project
    def openProjectProperties(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        dialog = ProjectMetadataDialog(self.projectMetadata, lan, self)
        if dialog.exec():
            self.projectMetadata = dialog.getMetadata()
            self.markProjectModified()
            self.statusBarWidget.showMessage(
                lan.get("statusMetadataSaved", "Project properties updated"), SERIES_STATUS_TIMEOUT)

    # Ask before throwing away unsaved work, returning False when the user backs out
    def confirmDiscardChanges(self):
        if not self.isProjectModified:
            return True

        lan = self.translationManager.getLanguage(self.currentLanguage)
        answer = QMessageBox.question(
            self, lan.get("unsavedChangesTitle", "Unsaved changes"),
            lan.get("unsavedChangesPrompt",
                    "This project has unsaved changes. Save them before continuing?"),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)

        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.saveProject()
        return True

    # Start an empty project and immediately ask for its identification
    def newProject(self):
        if not self.confirmDiscardChanges():
            return
        # Rebuilding the map inside the closing confirm dialog crashes the embedded web view
        QTimer.singleShot(0, self.startNewProject)

    # Wipe every dataset, forget the current file and prompt for the new project metadata
    def startNewProject(self):
        self.performCompleteReset()
        self.mapWidget.clearViewState()
        self.currentProjectPath = None
        self.projectMetadata = project_metadata.buildDefaultMetadata()
        self.discardRecoverySnapshot()
        self.clearProjectModified()
        self.openProjectProperties()

    # File name suggested by the Save As dialog, derived from the project title
    def suggestProjectFileName(self):
        title = self.projectMetadata.get("projectTitle", "").strip()
        slug = batch_export.slugifyLabel(title) if title else "untitled"
        return f"{slug}{project_file.PROJECT_EXTENSION}"

    # Save to the current file, falling back to Save As while the project has no path yet
    def saveProject(self):
        if not self.currentProjectPath:
            return self.saveProjectAs()
        return self.writeProjectTo(self.currentProjectPath)

    # Ask for a target path and save the project there, adopting it as the current file
    def saveProjectAs(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        suggestedPath = (self.currentProjectPath if self.currentProjectPath
                         else self.suggestProjectFileName())
        filepath, _ = QFileDialog.getSaveFileName(
            self, lan.get("saveProjectAs", "Save Project As..."), suggestedPath,
            lan.get("projectFileFilter", "COYPU Project (*.coypu)"))
        if not filepath:
            return False
        if not filepath.lower().endswith(project_file.PROJECT_EXTENSION):
            filepath += project_file.PROJECT_EXTENSION
        return self.writeProjectTo(filepath)

    # Serialize the whole live project into one .coypu archive
    def writeProjectTo(self, filepath):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        try:
            payload = self.projectFileManager.buildProjectPayload(self)
            rawAssets = self.projectFileManager.collectRawAssets(self)
            self.projectFileManager.writeProjectArchive(filepath, payload, rawAssets)
        except Exception as saveError:
            QMessageBox.critical(self, lan.get("error", "Error"), str(saveError))
            return False

        self.currentProjectPath = str(filepath)
        self.recentProjectsStore.rememberProject(filepath)
        self.rebuildRecentProjectsMenu()
        self.discardRecoverySnapshot()
        self.clearProjectModified()
        self.statusBarWidget.showMessage(
            lan.get("statusProjectSaved", "Project saved"), SERIES_STATUS_TIMEOUT)
        self.setEngineStatus(f"{lan.get('statusProjectSaved', 'Project saved')}: {filepath}")
        return True

    # Pick a .coypu archive and load it over the current session
    def openProject(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        if not self.confirmDiscardChanges():
            return
        filepath, _ = QFileDialog.getOpenFileName(
            self, lan.get("openProject", "Open Project..."), "",
            lan.get("projectFileFilter", "COYPU Project (*.coypu)"))
        if not filepath:
            return
        # Deferred so the closing file dialog never overlaps the folium rebuild
        QTimer.singleShot(0, lambda: self.loadProjectFile(filepath))

    # Read one .coypu archive and rebuild every dataset, dock, plot and the map from it
    def loadProjectFile(self, filepath, adoptPath=True):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        try:
            payload, rawAssets = self.projectFileManager.readProjectArchive(filepath)
            self.projectFileManager.applyProjectPayload(self, payload, rawAssets)
        except Exception as loadError:
            QMessageBox.critical(self, lan.get("error", "Error"), str(loadError))
            return False

        if adoptPath:
            self.currentProjectPath = str(filepath)
            self.recentProjectsStore.rememberProject(filepath)

        self.refreshAfterProjectLoad()
        self.clearProjectModified()
        self.statusBarWidget.showMessage(
            lan.get("statusProjectLoaded", "Project loaded"), SERIES_STATUS_TIMEOUT)
        self.setEngineStatus(f"{lan.get('statusProjectLoaded', 'Project loaded')}: {filepath}")
        return True

    # Rebuild every table, source viewer, plot and the map from freshly loaded project data
    def refreshAfterProjectLoad(self):
        lxml = self.dataStorage.get("LandXML", {})
        self.seedProfileCacheFromStorage()

        self.updateTableLandXML(lxml)
        self.tableTTP.setData({
            "stationSpeedLimits": self.dataStorage.get("stationSpeedLimits", []),
            "speedLimits": self.dataStorage.get("speedLimits", []),
        })
        self.refreshLandXmlSourceText()
        self.refreshTtpSourceText()
        self.reportGeometryWidget.setPlainText("\n".join(self.lastGeometryReportLines))

        self.rebuildVehicleReportMenus()
        self.rebuildRecentProjectsMenu()
        self.refreshStations()
        self.updateOptimizationActionState()
        self.toggleSlewPlotAction.setChecked(bool(lxml.get("slewProfileOffsetMm") is not None
                                                  and len(lxml.get("slewProfileOffsetMm", [])) > 0))
        self.applyStoredRunDirection()
        self.plotCant()
        self.plotCurvature()
        self.plotProfile()
        self.plotSpeedLimits()
        self.plotKinematics()
        self.refreshTrackStatsDock()

        if lxml.get("alignmentCoordinates"):
            self.updateMapWithSpeeds()
        else:
            self.mapWidget.resetMap()

        self.updateTexts()

    # Rebuild the recent projects submenu from the persisted list, newest first
    def rebuildRecentProjectsMenu(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.recentProjectsMenu.clear()

        recentPaths = self.recentProjectsStore.recentProjects()
        if not recentPaths:
            emptyAction = self.recentProjectsMenu.addAction(
                lan.get("recentProjectsEmpty", "No recent projects"))
            emptyAction.setEnabled(False)
            return

        for projectPath in recentPaths:
            entryAction = self.recentProjectsMenu.addAction(Path(projectPath).name)
            entryAction.setToolTip(projectPath)
            entryAction.triggered.connect(
                lambda checked=False, path=projectPath: self.openRecentProject(path))

        self.recentProjectsMenu.addSeparator()
        clearAction = self.recentProjectsMenu.addAction(
            lan.get("recentProjectsClear", "Clear list"))
        clearAction.triggered.connect(self.clearRecentProjects)

    # Open one entry of the recent projects submenu with the usual unsaved changes guard
    def openRecentProject(self, projectPath):
        if not self.confirmDiscardChanges():
            return
        QTimer.singleShot(0, lambda: self.loadProjectFile(projectPath))

    # Forget every remembered project, used when the list points at moved files
    def clearRecentProjects(self):
        self.recentProjectsStore.clearProjects()
        self.rebuildRecentProjectsMenu()

    # File name suggested by the LandXML export dialog
    def suggestExportFileName(self):
        title = self.projectMetadata.get("projectTitle", "").strip()
        slug = batch_export.slugifyLabel(title) if title else "alignment"
        return f"COYPU_{slug}.xml"

    # Write the merged alignment, its optimized cant and its vertical profile as LandXML 1.2
    def exportLandXml(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        lxml = self.dataStorage.get("LandXML", {})
        if len(lxml.get("stationHorizontal", [])) == 0:
            QMessageBox.warning(self, lan.get("error", "Error"),
                                lan.get("no_data", "No data available. Calculate values first."))
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, lan.get("exportLandXml", "Export Alignment to LandXML..."),
            self.suggestExportFileName(), lan.get("landXmlFileFilter", "LandXML (*.xml)"))
        if not filepath:
            return

        try:
            elementCount = landxml_exporter.exportAlignmentToFile(
                filepath, lxml, self.projectMetadata, self.dataStorage.get("settingsData", {}))
        except Exception as exportError:
            QMessageBox.critical(self, lan.get("error", "Error"), str(exportError))
            return

        successText = lan.get("landXmlExportDone", "Alignment exported to LandXML")
        elementsText = lan.get("landXmlExportElements", "Geometry elements")
        QMessageBox.information(self, lan.get("exportLandXml", "Export Alignment to LandXML..."),
                                f"{successText}\n{filepath}\n{elementsText}: {elementCount}")
        self.statusBarWidget.showMessage(successText, SERIES_STATUS_TIMEOUT)
        self.setEngineStatus(f"{successText}: {filepath}")

    # Path the background recovery snapshot is written to for the current project
    def recoverySnapshotPath(self):
        return project_file.recoveryPathFor(self.currentProjectPath)

    # Background recovery snapshot, skipped whenever there is nothing unsaved to protect
    def performAutoSave(self):
        if not self.isProjectModified:
            return

        lan = self.translationManager.getLanguage(self.currentLanguage)
        snapshotPath = self.recoverySnapshotPath()
        try:
            payload = self.projectFileManager.buildProjectPayload(self)
            rawAssets = self.projectFileManager.collectRawAssets(self)
            self.projectFileManager.writeProjectArchive(snapshotPath, payload, rawAssets)
        except Exception:
            # A failed snapshot must never interrupt the user, the next tick simply tries again
            return

        self.appSettings.setValue(project_file.RECOVERY_PATH_SETTING, str(snapshotPath))
        self.statusBarWidget.showMessage(
            lan.get("statusAutoSaved", "Recovery snapshot saved"), SERIES_STATUS_TIMEOUT)

    # Delete the recovery snapshot and its marker once the work is safely saved or discarded
    def discardRecoverySnapshot(self):
        storedPath = self.appSettings.value(project_file.RECOVERY_PATH_SETTING, "")
        candidatePaths = {str(self.recoverySnapshotPath())}
        if storedPath:
            candidatePaths.add(str(storedPath))

        for candidatePath in candidatePaths:
            try:
                Path(candidatePath).unlink(missing_ok=True)
            except OSError:
                continue
        self.appSettings.remove(project_file.RECOVERY_PATH_SETTING)

    # Offer the snapshot a crashed session left behind, once, right after startup
    def promptRecoveryIfAvailable(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        storedPath = self.appSettings.value(project_file.RECOVERY_PATH_SETTING, "")
        candidatePath = Path(storedPath) if storedPath else project_file.recoveryPathFor(None)
        if not candidatePath.is_file():
            return

        promptText = lan.get("recoveryPrompt",
                             "An unsaved recovery snapshot was found. Restore it?")
        answer = QMessageBox.question(
            self, lan.get("recoveryTitle", "Recover Project"),
            f"{promptText}\n{candidatePath}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            self.discardRecoverySnapshot()
            return

        if not self.loadProjectFile(str(candidatePath), adoptPath=False):
            return

        # A snapshot is not the project file itself, so the restored work stays unsaved
        self.currentProjectPath = self.originalProjectPathFor(candidatePath)
        self.markProjectModified()

    # Project file a recovery snapshot belongs to, or None for the untitled snapshot
    def originalProjectPathFor(self, snapshotPath):
        snapshotText = str(snapshotPath)
        if not snapshotText.endswith(project_file.RECOVERY_SUFFIX):
            return None
        originalPath = Path(snapshotText[:-len(project_file.RECOVERY_SUFFIX)])
        return str(originalPath) if originalPath.is_file() else None

    # Return every dock to the arrangement captured right after construction
    def resetLayout(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        answer = QMessageBox.question(
            self, lan.get("resetLayout", "Reset Layout"),
            lan.get("resetLayoutConfirm",
                    "Are you sure you want to reset all windows and docks "
                    "to their default layout?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return

        # Rebuilding the dock layout inside the closing dialog crashes the web view
        QTimer.singleShot(0, self.applyDefaultLayout)

    # Restore the captured default arrangement and confirm it in the status bar
    def applyDefaultLayout(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        self.restoreGeometry(self.defaultGeometry)
        self.restoreState(self.defaultLayoutState)
        self.statusBarWidget.showMessage(
            lan.get("statusLayoutReset", "Window layout restored to defaults"),
            SERIES_STATUS_TIMEOUT)

    def closeEvent(self, event):
        if not self.confirmDiscardChanges():
            event.ignore()
            return
        if self.batchController.isRunning():
            self.batchController.cancelBatch()
            self.batchController.waitForFinish()
        if self.optimizationController.isRunning():
            self.optimizationController.waitForFinish()
        if self.simulationController.isRunning():
            self.simulationController.cancelSimulation()
            self.simulationController.waitForFinish()
        self.autoSaveTimer.stop()
        self.discardRecoverySnapshot()
        self.saveSession()
        super().closeEvent(event)

    # Change language function
    def changeLanguage(self, langCode):
        self.currentLanguage = langCode
        self.appSettings.setValue("ui/language", langCode)
        self.updateTexts()

    def updateTexts(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        self.updateWindowTitle()

        # Ribbon tab captions
        self.ribbonBar.setPageTitle("project", lan.get("ribbonProject", "Project"))
        self.ribbonBar.setPageTitle("geometry", lan.get("ribbonGeometry", "Geometry"))
        self.ribbonBar.setPageTitle("simulation", lan.get("ribbonSimulation", "Simulation"))
        self.ribbonBar.setPageTitle("batch", lan.get("ribbonBatch", "Batch"))
        self.ribbonBar.setPageTitle("view", lan.get("ribbonView", "View"))
        self.ribbonBar.setPageTitle("series", lan.get("groupSeries", "Data series"))
        self.ribbonBar.setPageTitle("settings", lan.get("ribbonSettings", "Settings"))

        # Native project actions
        self.newProjectAction.setText(lan.get("newProject", "New Project"))
        self.openProjectAction.setText(lan.get("openProject", "Open Project..."))
        self.saveProjectAction.setText(lan.get("saveProject", "Save Project"))
        self.saveProjectAsAction.setText(lan.get("saveProjectAs", "Save Project As..."))
        self.projectPropertiesAction.setText(lan.get("projectProperties", "Project Properties..."))
        self.exportLandXmlAction.setText(lan.get("exportLandXml", "Export Alignment to LandXML..."))
        self.recentProjectsButton.setText(lan.get("recentProjects", "Recent Projects"))
        self.rebuildRecentProjectsMenu()

        # File actions
        self.openFileAction.setText(lan["open_file"])
        self.autodetectXMLAction.setText(lan["autodetect"])
        self.autodetectXMLAction.setStatusTip(lan["autodetect_tip"])
        self.appendAutodetectXMLAction.setText(lan.get("append_autodetect", "Append Autodetect"))
        self.appendAutodetectXMLAction.setStatusTip(lan.get("append_autodetect_tip", "Autodetect and append"))
        self.openParseLandXMLAction.setText(lan["open_parse_landxml"])
        self.appendLandXMLAction.setText(lan.get("append_landxml", "Append LandXML"))
        self.openParseXMLTTPAction.setText(lan["open_parse_xmlttp"])
        self.appendXMLTTPAction.setText(lan.get("append_xmlttp", "Append XML TTP"))
        self.exitAction.setText(lan["exit"])
        self.helpAction.setText(lan["help"])
        self.openCoypuFeederAction.setText(lan.get("openCoypuFeeder", "Coypu Feeder"))

        # Calculate actions
        self.calculateGeometryAction.setText(lan["calculate_geometry"])
        self.calculateGeometryIAction.setText(lan["calculate_geometry_I"])
        self.calculateTrainSpeedAction.setText(lan["calculate_train_speed"])

        # Clean actions
        self.cleanTTPDataAction.setText(lan["cleanTTP"])
        self.cleanLandXMLDataAction.setText(lan["cleanLandXML"])
        self.cleanDataAction.setText(lan["cleanAll"])
        self.cleanCalculatedCantsAction.setText(lan["cleanCants"])
        self.cleanCalculatedSpeedsAction.setText(lan["cleanSpeeds"])

        # Batch processing actions
        self.openBatchProcessingAction.setText(lan.get("batchTitle", "Batch Processing"))
        self.exportBatchArchiveAction.setText(lan.get("exportBatchArchive", "Export batch reports to ZIP..."))

        # Settings actions
        self.mapSettingsAction.setText(lan["mapSettings"])
        self.geometrySettingsAction.setText(lan["geometrySettings"])
        self.openShortcutSettingsAction.setText(lan.get("shortcutSettings", "Shortcuts"))
        self.vehicleSettingsAction.setText(lan.get("vehicleSettings", "Vehicle Settings"))
        self.stopsSettingsAction.setText(lan.get("stopsSettings", "Stops Settings"))
        self.speedSettingsAction.setText(lan.get("speedSettings", "Speed Limits Settings"))
        self.designApproachAction.setText(lan["designApproach"])
        self.alignmentOptimizationAction.setText(lan.get("alignmentOptimization", "Alignment Optimization"))
        self.clearOptimizationAction.setText(lan.get("clearOptimization", "Clear Optimization"))
        self.slewReportAction.setText(lan.get("slewReport", "Slew Report"))
        self.toggleSlewPlotAction.setText(lan.get("toggleSlewPlot", "Toggle Slew Plot"))
        self.includeSlewSectionAction.setText(lan.get("includeSlewSection", "Append Slew Summary"))
        self.reverseDirectionAction.setText(lan.get("runAgainstStationing", "Run against stationing"))
        self.reverseDirectionAction.setToolTip(lan.get(
            "runAgainstStationingTip",
            "Drive the whole simulation from the highest chainage towards the lowest"))
        if self.slewReportWindow is not None:
            self.slewReportWindow.updateTexts(lan)
        self.updateUnitsActionLabel()
        self.exportPresetsAction.setText(lan.get("exportPresets", "Export Presets..."))
        self.importPresetsAction.setText(lan.get("importPresets", "Import Presets..."))

        # Theme, view and layout actions
        self.themeAutoAction.setText(lan.get("themeAuto", "System default (auto)"))
        self.themeLightAction.setText(lan.get("themeLight", "Always light"))
        self.themeDarkAction.setText(lan.get("themeDark", "Always dark"))
        self.showMapAction.setText(lan.get("viewMap", "Map"))
        self.showReportAction.setText(lan.get("viewReport", "Report"))
        self.showDashboardAction.setText(lan.get("viewDashboard", "Variant comparison"))
        self.loadBatchVariantAction.setText(lan.get("batchLoadVariant", "Load variant into viewport"))
        self.batchVariantCombo.setToolTip(lan.get("batchVariantSelector", "Batch variant"))
        self.resetLayoutAction.setText(lan.get("resetLayout", "Reset Layout"))
        self.resetLayoutAction.setToolTip(
            lan.get("resetLayoutTip", "Restore Default Window Layout"))
        self.foldAllAction.setText(lan.get("foldAll", "Fold all"))
        self.unfoldAllAction.setText(lan.get("unfoldAll", "Unfold all"))

        # Series visibility actions are translated from their recorded keys
        for attributeName, languageKey in self.seriesActionKeys.items():
            getattr(self, attributeName).setText(lan.get(languageKey, languageKey))

        # Report actions
        self.reportGeometryAction.setText(lan.get("reportGeometry", "Report - Geometry"))
        self.exportGeometryReportAction.setText(lan.get("exportGeometryReport", "Export Geometry Report"))
        self.rebuildVehicleReportMenus()

        # Dock titles
        self.dockWorkflow.setWindowTitle(lan.get("dockWorkflow", "Workflow"))
        self.dockGraphs.setWindowTitle(lan.get("dockGraphs", "Track geometry and speed profile"))
        self.dockProfile.setWindowTitle(lan.get("dockProfile", "Plots - Profile"))
        self.dockKinematics.setWindowTitle(lan.get("dockKinematics", "Plots - Kinematics"))
        self.dockTrackStats.setWindowTitle(lan.get("dockTrackStats", "Track Statistics"))
        self.dockLandXmlRaw.setWindowTitle(lan.get("dockLandXmlRaw", "LandXML - source"))
        self.dockLandXmlParsed.setWindowTitle(lan.get("dockLandXmlParsed", "LandXML - data"))
        self.dockTtpRaw.setWindowTitle(lan.get("dockTtpRaw", "XML TTP - source"))
        self.dockTtpParsed.setWindowTitle(lan.get("dockTtpParsed", "XML TTP - data"))
        self.dockHelp.setWindowTitle(lan.get("dockHelp", "Help"))

        for dock in self.allDocks():
            dock.setLanguage(lan)

        # Child widgets holding their own captions
        self.workflowWidget.updateTexts(lan)
        for profileSelector in self.profileSelectors():
            profileSelector.updateTexts(lan)
        self.onAvailableProfilesChanged()
        self.graphsWidget.updateLabels(lan)
        self.profileWidget.updateLabels(lan)
        self.kinematicsWidget.updateLabels(lan)
        self.trackStatsWidget.updateTexts(lan)
        self.helpWidget.updateTexts(lan)
        self.mapWidget.updateTexts(lan)
        self.variantDashboardWidget.updateLabels(lan)
        self.ribbonBar.retranslate(lan)

        self.setEngineStatus(lan.get("statusReady", "Ready"))
        self.updateStatusChainage(None)
        self.updateStatusTheme()

    def getVehicleName(self, vehicleIndex):
        # trainParam[0][0] from vehicle settings, returns an empty string when not available
        vehicles = self.dataStorage.get("settingsData", {}).get("vehicles", [])
        try:
            return str(vehicles[vehicleIndex]["trainParam"][0][0]).strip()
        except (IndexError, KeyError, TypeError):
            return ""

    # Build a compact ribbon-styled QToolButton that opens a QMenu instead of triggering a single action
    def buildVehicleMenuButton(self, text, menu):
        button = QToolButton()
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(COMPACT_ICON_SIZE)
        button.setMaximumWidth(168)
        button.setStyleSheet("QToolButton { font-size: 9px; }")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        return button

    # Rebuild the per-vehicle report and export menus from the currently active vehicle slots
    def rebuildVehicleReportMenus(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        activeCount = len(self.dataStorage.get("settingsData", {}).get("vehicles", [])) or 1

        self.reportVehicleButton.setText(lan.get("vehicleReportButton", "Vehicle Report"))
        self.exportVehicleButton.setText(lan.get("vehicleExportButton", "Export Vehicle Report"))

        self.reportVehicleMenu.clear()
        self.exportVehicleMenu.clear()
        for vehicleIndex in range(activeCount):
            caption = self.getVehicleName(vehicleIndex) or f'{lan.get("vehicle", "Vehicle")} {vehicleIndex + 1}'

            reportAction = self.reportVehicleMenu.addAction(caption)
            reportAction.triggered.connect(
                lambda checked=False, index=vehicleIndex: self.generateVehicleReport(index))

            exportAction = self.exportVehicleMenu.addAction(caption)
            exportAction.triggered.connect(
                lambda checked=False, index=vehicleIndex: self.exportVehicleReport(index))

    def getFileContent(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*);;Text Files (*.txt);;XML Files (*.xml)")

        # If cancelled, do nothing
        if not filepath:
            return None, None

        # Read file content
        fileContent = readfile.ReadFile().Read(filepath)
        return fileContent, Path(filepath).name

    def openFile(self):
        fileContent, _ = self.getFileContent()
        if fileContent is not None:
            self.textboxRawLandXML.setXmlText(fileContent)

    def openAutodetectXML(self):
        fileContent, fileName = self.getFileContent()
        if fileContent is None:
            return

        xmlType = readfile.ReadFile().XMLType(fileContent)
        if xmlType == 1:
            self.parseLandXML(fileContent, fileName)
        elif xmlType == 2:
            self.parseXMLTTP(fileContent, fileName)
        else:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan.get("unknown_xml_file", "Unknown XML file format."))
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()

    def appendAutodetectXML(self):
        fileContent, fileName = self.getFileContent()
        if fileContent is None:
            return

        xmlType = readfile.ReadFile().XMLType(fileContent)
        if xmlType == 1:
            self.appendLandXMLContent(fileContent, fileName)
        elif xmlType == 2:
            self.appendXMLTTPContent(fileContent, fileName)
        else:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan.get("unknown_xml_file", "Unknown XML format."))
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()

    def openLandXML(self):
        fileContent, fileName = self.getFileContent()
        self.parseLandXML(fileContent, fileName)

    def openXMLTTP(self):
        fileContent, fileName = self.getFileContent()
        self.parseXMLTTP(fileContent, fileName)

    def appendXMLTTP(self):
        if "stationSpeedLimits" not in self.dataStorage or len(self.dataStorage.get("stationSpeedLimits", [])) == 0:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan.get("no_data", "No data available. Calculate values first."))
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()
            return

        fileContent, fileName = self.getFileContent()
        if not fileContent:
            return
        self.appendXMLTTPContent(fileContent, fileName)

    def appendXMLTTPContent(self, fileContent, fileName=None):
        if "stationSpeedLimits" not in self.dataStorage or len(self.dataStorage.get("stationSpeedLimits", [])) == 0:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan.get("no_data", "No data available. Calculate values first."))
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()
            return

        XMLTTPData = readfile.ReadFile().ParseXMLTTP(fileContent)
        newStations = XMLTTPData["stationSpeedLimits"]
        newSpeeds = XMLTTPData["speedLimits"]

        validMask = (newSpeeds != 0) & ~np.isnan(newSpeeds)
        newStations = newStations[validMask]
        newSpeeds = newSpeeds[validMask]

        lan = self.translationManager.getLanguage(self.currentLanguage)
        sections = self.TTPSections(newStations)
        
        if len(sections) > 0:
            sectionsInfo = []
            for i, section in enumerate(sections):
                sectionsInfo.append(f"{lan['station']} {section['stationStart']:.6f} km - {section['stationEnd']:.6f} km")

            HasLandXML = "stationHorizontal" in self.dataStorage.get("LandXML",{}) and len(self.dataStorage.get("LandXML",{}).get("stationHorizontal")) > 0

            dialog = gui_overlay.TTPSelectSectionDialog(sectionsInfo, HasLandXML, lan, self)
            if dialog.exec():
                selectedSectionIDs, cropToLandXML, loadAll = dialog.getSelectedSection()
            else:
                return
        else:
            selectedSectionIDs = []
            HasLandXML = False
            cropToLandXML = False
            loadAll = True

        stationsRaw = np.array(newStations)
        speedLimitsRaw = np.array(newSpeeds)

        if not loadAll:
            if not selectedSectionIDs:
                return
            tempStations = []
            tempSpeedLimits = []
            for sectionID in sorted(selectedSectionIDs):
                currentSection = sections[sectionID]
                startID = currentSection["startID"]
                endID = currentSection["endID"]+1
                secSt = stationsRaw[startID:endID]
                secSp = speedLimitsRaw[startID:endID]
                # Correct reversed (descending km) sections so that
                # getSpeedLimitAt() post-step semantics give the right limit.
                secSt, secSp = self.correctReversedTTPSection(secSt, secSp)
                tempStations.append(secSt)
                tempSpeedLimits.append(secSp)
            stationsRaw = np.concatenate(tempStations)
            speedLimitsRaw = np.concatenate(tempSpeedLimits)

            # Sort by station so the step plot is always monotonically increasing
            sortIdx = np.argsort(stationsRaw, kind='stable')
            stationsRaw    = stationsRaw[sortIdx]
            speedLimitsRaw = speedLimitsRaw[sortIdx]

        else:
            # loadAll=True — correct any reversed sections in the raw data.
            allSections = self.TTPSections(stationsRaw)
            tempStations = []
            tempSpeedLimits = []
            for section in allSections:
                secSt = stationsRaw[section["startID"]:section["endID"] + 1]
                secSp = speedLimitsRaw[section["startID"]:section["endID"] + 1]
                secSt, secSp = self.correctReversedTTPSection(secSt, secSp)
                tempStations.append(secSt)
                tempSpeedLimits.append(secSp)
            stationsRaw = np.concatenate(tempStations)
            speedLimitsRaw = np.concatenate(tempSpeedLimits)
            sortIdx = np.argsort(stationsRaw, kind='stable')
            stationsRaw    = stationsRaw[sortIdx]
            speedLimitsRaw = speedLimitsRaw[sortIdx]

        if cropToLandXML and HasLandXML:
            LandXMLMin = np.nanmin(self.dataStorage.get("LandXML",{}).get("stationHorizontal"))
            LandXMLMax = np.nanmax(self.dataStorage.get("LandXML",{}).get("stationHorizontal"))
            if not (np.isnan(LandXMLMin) or np.isnan(LandXMLMax)):
                beforeMinMask = stationsRaw <= LandXMLMin
                if np.any(beforeMinMask):
                    lastBefore = np.where(beforeMinMask)[0][-1]
                    speedLimitAtMin = speedLimitsRaw[lastBefore]
                else:
                    speedLimitAtMin = speedLimitsRaw[0] if len(speedLimitsRaw) > 0 else 0
                
                validMask = (stationsRaw > LandXMLMin) & (stationsRaw < LandXMLMax)
                stationsInside = stationsRaw[validMask]
                speedLimitsInside = speedLimitsRaw[validMask]
                
                stationsCropped = [LandXMLMin]
                speedLimitsCropped = [speedLimitAtMin]
                stationsCropped.extend(stationsInside.tolist())
                speedLimitsCropped.extend(speedLimitsInside.tolist())
                if stationsCropped[-1] < LandXMLMax:
                    stationsCropped.append(LandXMLMax)
                    speedLimitsCropped.append(speedLimitsCropped[-1])
                stationsRaw = np.array(stationsCropped, dtype=float)
                speedLimitsRaw = np.array(speedLimitsCropped, dtype=float)

        if len(stationsRaw) == 0:
            return

        # Cache this file's resolved contribution before merging, enables a later selective purge
        self.recordTtpSource(fileName, stationsRaw, speedLimitsRaw, fileContent)

        oldStations = self.dataStorage["stationSpeedLimits"]
        oldSpeeds = self.dataStorage["speedLimits"]
        mergedStations, mergedSpeeds = self.mergeTtpArrays(oldStations, oldSpeeds, stationsRaw, speedLimitsRaw)

        self.dataStorage["stationSpeedLimits"] = mergedStations
        self.dataStorage["speedLimits"] = mergedSpeeds

        TTPData = {
            "stationSpeedLimits": mergedStations,
            "speedLimits": mergedSpeeds
        }
        self.tableTTP.setData(TTPData)

        self.cleanCalculatedSpeeds()
        self.plotSpeedLimits()
        self.updateMapWithSpeeds()

    def appendLandXML(self):
        if "LandXML" not in self.dataStorage or len(self.dataStorage.get("LandXML", {}).get("stationHorizontal", [])) == 0:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan.get("no_data", "No data available. Calculate values first."))
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()
            return

        fileContent, fileName = self.getFileContent()
        if not fileContent:
            return
        self.appendLandXMLContent(fileContent, fileName)

    def appendLandXMLContent(self, fileContent, fileName=None):
        if "LandXML" not in self.dataStorage or len(self.dataStorage.get("LandXML", {}).get("stationHorizontal", [])) == 0:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan.get("no_data", "No data available. Calculate values first."))
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()
            return

        alignments = readfile.ReadFile().GetAlignments(fileContent)
        selectedIdx = 0
        if len(alignments) > 1:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            dialog = gui_overlay.AlignmentSelectDialog(alignments, lan, self)
            if dialog.exec():
                selectedIdx = dialog.getSelectedIndex()
            else:
                return

        newLandXMLData = readfile.ReadFile().ParseLandXML(fileContent, self.epsgInput, selectedIdx)

        # Cache this file's resolved contribution before merging, enables a later selective purge
        self.recordLandXMLSource(fileName, newLandXMLData, fileContent)

        self.mergeLandXMLData(newLandXMLData)

    def mergeLandXMLData(self, newData):
        oldData = self.dataStorage.get("LandXML", {})
        
        if len(newData.get("stationHorizontal", [])) == 0:
            return
            
        oldStart = np.nanmin(oldData["stationHorizontal"])
        oldEnd = np.nanmax(oldData["stationHorizontal"])
        newStart = np.nanmin(newData["stationHorizontal"])
        newEnd = np.nanmax(newData["stationHorizontal"])

        lan = self.translationManager.getLanguage(self.currentLanguage)

        if newStart >= oldEnd or (abs(newStart - oldEnd) <= abs(newEnd - oldStart)):
            isAppend = True
            cropStation = oldEnd
            if "keyX" in oldData and "keyY" in oldData and "keyX" in newData and "keyY" in newData:
                if len(oldData["keyX"]) > 0 and len(newData["keyX"]) > 0:
                    oldLastX, oldLastY = oldData["keyX"][-1], oldData["keyY"][-1]
                    newFirstX, newFirstY = newData["keyX"][0], newData["keyY"][0]
                    dist = np.sqrt((newFirstX - oldLastX)**2 + (newFirstY - oldLastY)**2)
                    if dist > 100:
                        QMessageBox.warning(self, lan.get("merge_gap_warning_title", "Warning"), lan.get("merge_gap_warning_desc", "Gap > 100m"))
        else:
            isAppend = False
            cropStation = oldStart
            if "keyX" in oldData and "keyY" in oldData and "keyX" in newData and "keyY" in newData:
                if len(oldData["keyX"]) > 0 and len(newData["keyX"]) > 0:
                    oldFirstX, oldFirstY = oldData["keyX"][0], oldData["keyY"][0]
                    newLastX, newLastY = newData["keyX"][-1], newData["keyY"][-1]
                    dist = np.sqrt((newLastX - oldFirstX)**2 + (newLastY - oldFirstY)**2)
                    if dist > 100:
                        QMessageBox.warning(self, lan.get("merge_gap_warning_title", "Warning"), lan.get("merge_gap_warning_desc", "Gap > 100m"))

        stationMap = {
            "cant": "stationCant",
            "stationCant": "stationCant",
            "stationHorizontal": "stationHorizontal",
            "geometryType": "stationHorizontal",
            "radius": "stationHorizontal",
            "curvature": "stationHorizontal",
            "curvatureSign": "stationHorizontal",
            "stationVertical": "stationVertical",
            "elevation": "stationVertical"
        }

        # One keep decision per element, taken once so the element stream, the per type geometry
        # arrays and the per element polylines all drop exactly the same elements at the overlap.
        # Cropping only the element stream would leave the type arrays long, and every element past
        # the seam would then read the coordinates of a neighbour. The seam tolerance drops an element
        # that clears the crop by rounding dust alone, which would otherwise survive with its station
        # span clamped to zero while its coordinates stayed full length.
        newStationHorizontal = np.asarray(newData.get("stationHorizontal", []), dtype=float)
        elementKeepPairs = np.zeros(len(newStationHorizontal), dtype=bool)
        seamToleranceKm = landxml_merger.SEAM_TOLERANCE_KM
        for i in range(0, len(newStationHorizontal), 2):
            endIdx = min(i + 1, len(newStationHorizontal) - 1)
            if isAppend:
                keep = newStationHorizontal[endIdx] > cropStation + seamToleranceKm
            else:
                keep = newStationHorizontal[i] < cropStation - seamToleranceKm
            elementKeepPairs[i] = keep
            elementKeepPairs[endIdx] = keep
        elementKeep = elementKeepPairs[::2]
        typeMasks = landxml_merger.elementTypeMasks(newData.get("geometryType", []), elementKeep)

        def mergeArrays(key):
            if key not in oldData or key not in newData:
                return oldData.get(key, newData.get(key, []))
            
            oldArr = oldData[key]
            newArr = newData[key]

            if key == "denseAlignment":
                if isAppend:
                    newArrCropped = [p for p in newArr if p[0] > cropStation]
                    return oldArr + newArrCropped
                else:
                    newArrCropped = [p for p in newArr if p[0] < cropStation]
                    return newArrCropped + oldArr

            if key in ["keyStations", "keyTypes", "keyX", "keyY", "keyLat", "keyLon"]:
                newStations = np.array(newData["keyStations"])
                mask = newStations > cropStation if isAppend else newStations < cropStation
            elif key in stationMap:
                sKey = stationMap[key]
                newStations = np.array(newData[sKey])
                
                if sKey == "stationHorizontal":
                    # Pole definovaná v párech (počátek-konec segmentu) sdílejí jedno rozhodnutí na prvek
                    mask = elementKeepPairs
                            
                    if key == "stationHorizontal":
                        if isinstance(newArr, np.ndarray): newArr = np.copy(newArr)
                        else: newArr = list(newArr)
                            
                        for i in range(0, len(newStations), 2):
                            if mask[i]:
                                if isAppend and newArr[i] < cropStation: newArr[i] = cropStation
                                elif not isAppend and (i+1) < len(newArr) and newArr[i+1] > cropStation: newArr[i+1] = cropStation
                else:
                    mask = newStations > cropStation if isAppend else newStations < cropStation
            elif key in landxml_merger.ELEMENT_TYPE_OF_KEY:
                mask = typeMasks[landxml_merger.ELEMENT_TYPE_OF_KEY[key]]
            elif key in landxml_merger.ELEMENT_LIST_KEYS:
                mask = elementKeep
            else:
                if isinstance(oldArr, np.ndarray) and isinstance(newArr, np.ndarray):
                    if isAppend: return np.concatenate((oldArr, newArr))
                    else: return np.concatenate((newArr, oldArr))
                elif isinstance(oldArr, list) and isinstance(newArr, list):
                    if isAppend: return oldArr + newArr
                    else: return newArr + oldArr
                return oldArr

            if isinstance(newArr, np.ndarray):
                newArrCropped = newArr[mask]
                if isAppend:
                    return np.concatenate((oldArr, newArrCropped))
                else:
                    return np.concatenate((newArrCropped, oldArr))
            elif isinstance(newArr, list):
                newArrCropped = [item for i, item in enumerate(newArr) if mask[i]]
                if isAppend:
                    return oldArr + newArrCropped
                else:
                    return newArrCropped + oldArr
            return oldArr

        mergedData = {}
        allKeys = set(list(oldData.keys()) + list(newData.keys()))
        for k in allKeys:
            mergedData[k] = mergeArrays(k)

        if "stationVertical" in mergedData and "elevation" in mergedData:
            deltaZ = np.diff(np.array(mergedData["elevation"], dtype=float))
            deltaX = np.diff(np.array(mergedData["stationVertical"], dtype=float))
            mergedData["slope"] = np.zeros_like(deltaX)
            valid = deltaX != 0
            mergedData["slope"][valid] = deltaZ[valid] / deltaX[valid]

        self.dataStorage["LandXML"] = mergedData
        self.updateTableLandXML(mergedData)

        self.cleanCalculatedCants()
        self.cleanCalculatedSpeeds()
        
        self.plotCant()
        self.plotCurvature()
        self.plotProfile()
        self.mapWidget.drawAlignment(mergedData.get("alignmentCoordinates",[]), mergedData)

    # Cache one imported LandXML file's resolved contribution, enables a later selective purge
    def recordLandXMLSource(self, fileName, landXmlData, rawText=""):
        stations = landXmlData.get("stationHorizontal", [])
        if len(stations) == 0:
            return
        stationStart = float(np.nanmin(stations))
        stationEnd = float(np.nanmax(stations))
        self.sourceStack.addEntry(source_stack.LANDXML_KIND, fileName or "LandXML.xml",
                                  copy.deepcopy(landXmlData), stationStart, stationEnd, rawText)
        self.refreshLandXmlSourceText()
        self.markProjectModified()

    # Cache one imported TTP file's resolved contribution, enables a later selective purge
    def recordTtpSource(self, fileName, stations, speedLimits, rawText=""):
        if len(stations) == 0:
            return
        stationStart = float(np.nanmin(stations))
        stationEnd = float(np.nanmax(stations))
        payload = (np.array(stations, dtype=float), np.array(speedLimits, dtype=float))
        self.sourceStack.addEntry(source_stack.TTP_KIND, fileName or "TTP.xml",
                                  payload, stationStart, stationEnd, rawText)
        self.refreshTtpSourceText()
        self.markProjectModified()

    # Replace the LandXML source viewer with a summary of the currently surviving segments
    def refreshLandXmlSourceText(self):
        entries = self.sourceStack.entriesForKind(source_stack.LANDXML_KIND)
        lines = [f"<!-- {entry.fileName}: {entry.stationStart:.3f} km - {entry.stationEnd:.3f} km -->"
                for entry in entries]
        self.textboxRawLandXML.setXmlText("\n".join(lines))

    # Replace the TTP source viewer with a summary of the currently surviving segments
    def refreshTtpSourceText(self):
        entries = self.sourceStack.entriesForKind(source_stack.TTP_KIND)
        lines = [f"<!-- {entry.fileName}: {entry.stationStart:.3f} km - {entry.stationEnd:.3f} km -->"
                for entry in entries]
        self.textboxRawTTP.setXmlText("\n".join(lines))

    # Merge two resolved TTP arrays, the gap detection mirrors a live TTP import
    def mergeTtpArrays(self, oldStations, oldSpeeds, newStations, newSpeeds):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        oldStart = np.nanmin(oldStations)
        oldEnd = np.nanmax(oldStations)
        newStart = np.nanmin(newStations)
        newEnd = np.nanmax(newStations)

        if newStart >= oldEnd or (abs(newStart - oldEnd) <= abs(newEnd - oldStart)):
            isAppend = True
            cropStation = oldEnd
            if abs(newStart - oldEnd) > 0.1:
                QMessageBox.warning(self, lan.get("merge_gap_warning_title", "Warning"),
                                    lan.get("merge_gap_warning_desc", "Gap > 100m"))
        else:
            isAppend = False
            cropStation = oldStart
            if abs(oldStart - newEnd) > 0.1:
                QMessageBox.warning(self, lan.get("merge_gap_warning_title", "Warning"),
                                    lan.get("merge_gap_warning_desc", "Gap > 100m"))

        if isAppend:
            mask = newStations > cropStation
            mergedStations = np.concatenate((oldStations, newStations[mask]))
            mergedSpeeds = np.concatenate((oldSpeeds, newSpeeds[mask]))
        else:
            mask = newStations < cropStation
            mergedStations = np.concatenate((newStations[mask], oldStations))
            mergedSpeeds = np.concatenate((newSpeeds[mask], oldSpeeds))

        return mergedStations, mergedSpeeds

    # Rebuild the merged LandXML dataset by replaying every surviving source stack entry
    def rebuildLandXMLFromStack(self):
        entries = self.sourceStack.entriesForKind(source_stack.LANDXML_KIND)

        self.dataStorage["LandXML"] = {}
        for index, entry in enumerate(entries):
            payload = copy.deepcopy(entry.payload)
            if index == 0:
                self.dataStorage["LandXML"] = payload
            else:
                self.mergeLandXMLData(payload)

        lxml = self.dataStorage.get("LandXML", {})
        self.updateTableLandXML(lxml)
        self.cleanCalculatedCants()
        self.cleanCalculatedSpeeds()
        self.plotCant()
        self.plotCurvature()
        self.plotProfile()
        self.mapWidget.drawAlignment(lxml.get("alignmentCoordinates", []), lxml)
        self.refreshLandXmlSourceText()

    # Rebuild the merged TTP dataset by replaying every surviving source stack entry
    def rebuildTtpFromStack(self):
        entries = self.sourceStack.entriesForKind(source_stack.TTP_KIND)

        if not entries:
            mergedStations = np.array([])
            mergedSpeeds = np.array([])
        else:
            mergedStations, mergedSpeeds = entries[0].payload
            mergedStations = np.array(mergedStations, dtype=float)
            mergedSpeeds = np.array(mergedSpeeds, dtype=float)
            for entry in entries[1:]:
                newStations, newSpeeds = entry.payload
                mergedStations, mergedSpeeds = self.mergeTtpArrays(
                    mergedStations, mergedSpeeds,
                    np.array(newStations, dtype=float), np.array(newSpeeds, dtype=float))

        self.dataStorage["stationSpeedLimits"] = mergedStations
        self.dataStorage["speedLimits"] = mergedSpeeds
        self.tableTTP.setData({"stationSpeedLimits": mergedStations, "speedLimits": mergedSpeeds})
        self.cleanCalculatedSpeeds()
        self.plotSpeedLimits()
        self.updateMapWithSpeeds()
        self.refreshTtpSourceText()

    def parseLandXML(self, fileContent, fileName=None):
        if fileContent is not None:
            # Check for multiple alignments and prompt the user if needed
            alignments = readfile.ReadFile().GetAlignments(fileContent)
            selectedIdx = 0
            if len(alignments) > 1:
                lan = self.translationManager.getLanguage(self.currentLanguage)
                dialog = gui_overlay.AlignmentSelectDialog(alignments, lan, self)
                if dialog.exec():
                    selectedIdx = dialog.getSelectedIndex()
                else:
                    return  # User cancelled the dialog, do nothing

            LandXMLData = readfile.ReadFile().ParseLandXML(fileContent, self.epsgInput, selectedIdx)
            self.updateTableLandXML(LandXMLData)

            # Save data to central data storage
            self.dataStorage["LandXML"] = LandXMLData

            # A fresh import replaces the whole route stack, not just the merged arrays
            self.sourceStack.clearKind(source_stack.LANDXML_KIND)
            self.recordLandXMLSource(fileName, LandXMLData, fileContent)

            # Plot and draw data
            lxml = self.dataStorage.get("LandXML",{})
            self.plotCant()
            self.plotCurvature()
            self.plotProfile()
            self.mapWidget.drawAlignment(lxml.get("alignmentCoordinates",[]), lxml)

            # Step 1 of the workflow guide is done once LandXML is parsed
            self.workflowWidget.markCompleted(0)
            self.setEngineStatus(self.translationManager.getLanguage(self.currentLanguage).get("dockLandXmlParsed", "LandXML"))

        else:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan["no_file"])
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()

    def parseXMLTTP(self, fileContent, fileName=None):
        if fileContent is not None:
            XMLTTPData = readfile.ReadFile().ParseXMLTTP(fileContent)

            lan = self.translationManager.getLanguage(self.currentLanguage)

            self.dataStorage["stationSpeedLimits"] = XMLTTPData["stationSpeedLimits"]
            self.dataStorage["speedLimits"] = XMLTTPData["speedLimits"]

            validStationSpeedLimits = (self.dataStorage["speedLimits"] != 0) & ~np.isnan(self.dataStorage["speedLimits"])
            
            self.dataStorage["stationSpeedLimits"] = self.dataStorage["stationSpeedLimits"][validStationSpeedLimits]
            self.dataStorage["speedLimits"] = self.dataStorage["speedLimits"][validStationSpeedLimits]

            sections = self.TTPSections(self.dataStorage["stationSpeedLimits"])

            if len(sections) > 0:
                sectionsInfo = []

                # Create a list of section descriptions for the dialog
                for i, section in enumerate(sections):
                    sectionsInfo.append(f"{lan['station']} {section['stationStart']:.6f} km - {section['stationEnd']:.6f} km")

                # LandXML data availability check for cropping option in TTP sections dialog
                HasLandXML = "stationHorizontal" in self.dataStorage.get("LandXML",{}) and len(self.dataStorage.get("LandXML",{}).get("stationHorizontal")) > 0

                # Show the section selection dialog
                dialog = gui_overlay.TTPSelectSectionDialog(sectionsInfo, HasLandXML, lan, self)
                if dialog.exec():
                    selectedSectionIDs, cropToLandXML, loadAll = dialog.getSelectedSection()
                else:
                    return  # User cancelled the dialog, do nothing
            
            else:
                selectedSectionIDs = []
                HasLandXML = False
                cropToLandXML = False
                loadAll = True

            # Extract data from central storage
            stationsRaw = np.array(self.dataStorage["stationSpeedLimits"])
            speedLimitsRaw = np.array(self.dataStorage["speedLimits"])

            # Crop to LandXML data range if option is selected and LandXML data is available
            if not loadAll:
                if not selectedSectionIDs:
                    return

                tempStations = []
                tempSpeedLimits = []

                for sectionID in sorted(selectedSectionIDs):
                    currentSection = sections[sectionID]
                    startID = currentSection["startID"]
                    endID = currentSection["endID"]+1

                    secSt = stationsRaw[startID:endID]
                    secSp = speedLimitsRaw[startID:endID]
                    # Correct reversed (descending km) sections so that
                    # getSpeedLimitAt() post-step semantics give the right limit.
                    secSt, secSp = self.correctReversedTTPSection(secSt, secSp)
                    tempStations.append(secSt)
                    tempSpeedLimits.append(secSp)

                stationsRaw = np.concatenate(tempStations)
                speedLimitsRaw = np.concatenate(tempSpeedLimits)

                # Sort by station so the step plot is always monotonically increasing.
                # This acts as a safety net for any edge case the section detector may miss
                # (e.g. non-standard TTP layouts or multiple selected sections).
                sortIdx = np.argsort(stationsRaw, kind='stable')
                stationsRaw    = stationsRaw[sortIdx]
                speedLimitsRaw = speedLimitsRaw[sortIdx]

            else:
                # loadAll=True — apply the same reversed-section correction to every
                # monotone section present in the raw data before storing.
                allSections = self.TTPSections(stationsRaw)
                tempStations = []
                tempSpeedLimits = []
                for section in allSections:
                    secSt = stationsRaw[section["startID"]:section["endID"] + 1]
                    secSp = speedLimitsRaw[section["startID"]:section["endID"] + 1]
                    secSt, secSp = self.correctReversedTTPSection(secSt, secSp)
                    tempStations.append(secSt)
                    tempSpeedLimits.append(secSp)
                stationsRaw = np.concatenate(tempStations)
                speedLimitsRaw = np.concatenate(tempSpeedLimits)
                sortIdx = np.argsort(stationsRaw, kind='stable')
                stationsRaw    = stationsRaw[sortIdx]
                speedLimitsRaw = speedLimitsRaw[sortIdx]

            if cropToLandXML and HasLandXML:
                LandXMLMin = np.nanmin(self.dataStorage.get("LandXML",{}).get("stationHorizontal"))
                LandXMLMax = np.nanmax(self.dataStorage.get("LandXML",{}).get("stationHorizontal"))

                if np.isnan(LandXMLMin) or np.isnan(LandXMLMax):
                    stations = stationsRaw
                    speedLimits = speedLimitsRaw
                else:

                    beforeMinMask = stationsRaw <= LandXMLMin
                    if np.any(beforeMinMask):
                        lastBefore = np.where(beforeMinMask)[0][-1]
                        speedLimitAtMin = speedLimitsRaw[lastBefore]
                    else:
                        speedLimitAtMin = speedLimitsRaw[0] if len(speedLimitsRaw) > 0 else 0
                    
                    validMask = (stationsRaw > LandXMLMin) & (stationsRaw < LandXMLMax)

                    stationsInside = stationsRaw[validMask]
                    speedLimitsInside = speedLimitsRaw[validMask]

                    stationsCropped = [LandXMLMin]
                    speedLimitsCropped = [speedLimitAtMin]
                    
                    stationsCropped.extend(stationsInside.tolist())
                    speedLimitsCropped.extend(speedLimitsInside.tolist())
                    
                    if stationsCropped[-1] < LandXMLMax:
                        stationsCropped.append(LandXMLMax)
                        speedLimitsCropped.append(speedLimitsCropped[-1])

                    stations = np.array(stationsCropped, dtype = float)
                    speedLimits = np.array(speedLimitsCropped, dtype = float)
            
            else:
                stations = stationsRaw
                speedLimits = speedLimitsRaw

            self.dataStorage["stationSpeedLimits"] = stations
            self.profileState.refreshAvailability(self.dataStorage)
            self.dataStorage["speedLimits"] = speedLimits

            # A fresh import replaces the whole TTP stack, not just the merged arrays
            self.sourceStack.clearKind(source_stack.TTP_KIND)
            self.recordTtpSource(fileName, stations, speedLimits, fileContent)

            TTPData = {
                "stationSpeedLimits": stations,
                "speedLimits": speedLimits
            }

            self.tableTTP.setData(TTPData)
            self.plotSpeedLimits()
            self.updateMapWithSpeeds()
        else:
            lan = self.translationManager.getLanguage(self.currentLanguage)
            err = QMessageBox()
            err.setWindowTitle(lan["error"])
            err.setText(lan["no_file"])
            err.setIcon(QMessageBox.Icon.Warning)
            err.exec()
            
    # def importStopsTTP(self):
    #     file_content = self.getFileContent()
    #     if file_content is not None:
    #         XMLTTPData = readfile.ReadFile().ParseXMLTTP(file_content)
    #         stations = XMLTTPData.get("stationSpeedLimits", [])
    #         settings = self.dataStorage.setdefault("settingsData", {})
    #         trainStops = settings.setdefault("trainStops", [])
    #         defaultDwell = float(settings.get("defaultDwellTime", 30.0))
    #         for st in stations:
    #             trainStops.append([float(st), defaultDwell])
    #         lan = self.translationManager.getLanguage(self.currentLanguage)
    #         msg = QMessageBox()
    #         msg.setWindowTitle(lan.get("importStopsTTP", "Import Stops"))
    #         msg.setText(f"Imported {len(stations)} stops.")
    #         msg.setIcon(QMessageBox.Icon.Information)
    #         msg.exec()
    #     else:
    #         lan = self.translationManager.getLanguage(self.currentLanguage)
    #         err = QMessageBox()
    #         err.setWindowTitle(lan["error"])
    #         err.setText(lan["no_file"])
    #         err.setIcon(QMessageBox.Icon.Warning)
    #         err.exec()

    # Redraw the vertical alignment plot from the parsed LandXML data
    def renderProfile(self):
        self.profileWidget.updateProfileData(self.dataStorage.get("LandXML", {}),
                                             self.toggleProfileAction.isChecked())

    # Redraw every kinematics plot from the latest simulation results
    def renderKinematics(self):
        self.kinematicsWidget.updateKinematicsData(
            self.dataStorage,
            self.toggleUnitsAction.isChecked(),
            self.getVehicleName,
            self.seriesVisibility())

    # ------------------------------------------------------------------
    # Pop-up plot windows (right-click context menu on any canvas)
    # ------------------------------------------------------------------

    # Build and display the QMenu with a fixed list of all graphs
    def showGraphContextMenu(self, globalPos):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        graphDefs = [
            ("speed",       lan.get("speed_lim",                   "Speed Limits")),
            ("cant_curv",   f'{lan.get("cant","Cant")} / {lan.get("curvature","Curvature")}'),
            ("profile",     lan.get("profile",                     "Profile")),
            ("tacho_track", lan.get("kinematicsSpeedLimitTrack",   "Speed–Distance")),
            ("tacho_time",  lan.get("kinematicsSpeedLimitTime",    "Speed–Time")),
            ("dist_time",   lan.get("kinematicsDistanceTime",      "Distance–Time")),
            ("forces",      lan.get("kinematicsForces",            "Forces")),
        ]

        menu = QMenu(self)
        menu.addSection(lan.get("openGraphMenu", "Open graph in new window"))
        for graphId, graphName in graphDefs:
            action = menu.addAction(graphName)
            # Default-argument binding prevents loop-variable capture issues
            action.triggered.connect(
                lambda checked=False, gid=graphId: self.openPopupPlot(gid)
            )
        menu.exec(globalPos)

    # Collect data from dataStorage and open a PopupPlotWindow for the given graph
    def openPopupPlot(self, graphId):
        lan  = self.translationManager.getLanguage(self.currentLanguage)
        lxml = self.dataStorage.get("LandXML", {})

        # Unit factors (shared with plotKinematics)
        useKmh   = self.toggleUnitsAction.isChecked()
        vFactor  = 3.6    if useKmh else 1.0
        dFactor  = 1000.0 if useKmh else 1.0
        tFactor  = 60.0   if useKmh else 1.0
        spdLbl   = lan.get("speedKmh",    "Speed [km/h]")  if useKmh else lan.get("speedM",    "Speed [m/s]")
        splimLbl = lan.get("speedLimKmh", "Speed Limit [km/h]") if useKmh else lan.get("speedLimM", "Speed Limit [m/s]")
        distLbl  = lan.get("distanceKm",  "Distance [km]") if useKmh else lan.get("distance",   "Distance [m]")
        timeLbl  = lan.get("timeMin",     "Time [min]")    if useKmh else lan.get("time",        "Time [s]")

        numVehicles    = self.dataStorage.get("num_vehicles", 1)
        colorsSpeed    = ['tab:red',   'tab:green',  'tab:blue',   'tab:purple', 'tab:orange']
        colorsTrac     = ['green',    'lime',       'darkgreen',  'seagreen',   'olive']
        colorsBrake    = ['red',      'darkred',    'salmon',     'firebrick',  'indianred']
        colorsRes      = ['orange',   'darkorange', 'gold',       'chocolate',  'goldenrod']
        limitColors    = ['lightcoral','lightgreen','lightskyblue','plum',      'moccasin']

        def vehicleLabel(vIdx):
            if numVehicles <= 1:
                return ""
            vname = self.getVehicleName(vIdx)
            return f" {vname}" if vname else f" V{vIdx+1}"

        # ---- helper: build stop-expanded time/speed/station arrays ----------
        # Insert arrival points with zero speed for dwell stops
        def expandStops(vIdx, baseTimes, baseValues):
            dwells = self.dataStorage.get(f"kinematicsDwellTimesS_{vIdx}")
            if dwells is None:
                return np.array(baseTimes), np.array(baseValues)
            tList = list(baseTimes)
            vList = list(baseValues)
            stopIdx = np.where(dwells > 0)[0]
            offset = 0
            for idx in stopIdx:
                ai = idx + offset
                arrival = tList[ai] - dwells[idx]
                tList.insert(ai, arrival)
                vList.insert(ai, 0.0)
                offset += 1
            return np.array(tList), np.array(vList)

        # Same as above but preserves the station value for the distance-time plot
        def expandStopsStation(vIdx, baseTimes, baseStations):
            dwells = self.dataStorage.get(f"kinematicsDwellTimesS_{vIdx}")
            if dwells is None:
                return np.array(baseTimes), np.array(baseStations)
            tList = list(baseTimes)
            sList = list(baseStations)
            stopIdx = np.where(dwells > 0)[0]
            offset = 0
            for idx in stopIdx:
                ai = idx + offset
                arrival = tList[ai] - dwells[idx]
                tList.insert(ai, arrival)
                sList.insert(ai, sList[ai])
                offset += 1
            return np.array(tList), np.array(sList)

        # ==================================================================
        if graphId == "speed":
            title   = lan.get("speed_lim", "Speed Limits")
            primary = []
            pairs = [
                ("stationSpeedLimits", "speedLimits",   lan.get("speed_lim"),       'black'),
                ("stationSpeed100",    "speedLimits100", lan.get("speed_lim_100"),   'red'),
                ("stationSpeed130",    "speedLimits130", lan.get("speed_lim_130"),   'teal'),
                ("stationSpeed150",    "speedLimits150", lan.get("speed_lim_150"),   'darkorchid'),
                ("stationSpeedK",      "speedLimitsK",   lan.get("speed_lim_K"),     'cornflowerblue'),
            ]
            for sk, vk, lbl, col in pairs:
                st = self.dataStorage.get(sk)
                sp = self.dataStorage.get(vk)
                if st is not None and sp is not None and len(st) > 0 and len(sp) > 0:
                    primary.append(dict(x=st, y=sp, label=lbl, color=col,
                                        step=True, marker='s'))
            win = gui_overlay.PopupPlotWindow(title, self, lan)
            win.drawData(primary,
                          xlabel=lan.get("station","Station [km]"),
                          ylabel=lan.get("speed_lim","Speed Limits"),
                          title=title)

        # ------------------------------------------------------------------
        elif graphId == "cant_curv":
            title   = f'{lan.get("cant","Cant")} / {lan.get("curvature","Curvature")}'
            primary = []
            secondary = []

            cantSeries = [
                ("stationCant",         "cant",       lan.get("cant"),         'black'),
                ("stationCantPossible", "cantPossible",lan.get("cant_possible"),'green'),
                ("stationCantPossible", "cDef100",    lan.get("cdef_100"),     'red'),
                ("stationCantPossible", "cDef130",    lan.get("cdef_130"),     'teal'),
                ("stationCantPossible", "cDef150",    lan.get("cdef_150"),     'darkorchid'),
                ("stationCantPossible", "cDefK",      lan.get("cdef_K"),       'cornflowerblue'),
                ("stationCantPossible", "cantDef100", lan.get("cant_def_100"), 'tomato'),
                ("stationCantPossible", "cantDef130", lan.get("cant_def_130"), 'aqua'),
                ("stationCantPossible", "cantDef150", lan.get("cant_def_150"), 'mediumorchid'),
                ("stationCantPossible", "cantDefK",   lan.get("cant_def_K"),   'royalblue'),
            ]
            for sk, dk, lbl, col in cantSeries:
                x = lxml.get(sk)
                y = lxml.get(dk)
                if x is not None and y is not None and len(x) > 0 and len(y) > 0:
                    primary.append(dict(x=x, y=y, label=lbl, color=col,
                                        linestyle='-', marker='o'))

            for sk, ck, lbl, col in [
                ("stationHorizontal",    "curvature",    lan.get("curvature"),     'tab:gray'),
                ("stationHorizontalBaseline", "curvatureBaseline", lan.get("curvature_baseline"), '#888888'),
            ]:
                x = lxml.get(sk)
                y = lxml.get(ck)
                if x is not None and y is not None and len(x) > 0 and len(y) > 0:
                    secondary.append(dict(x=x, y=y, label=lbl, color=col,
                                          linestyle='-', marker='o'))

            def fracFmt(x, pos=None):
                if np.isclose(x, 0, atol=1e-6):
                    return "0"
                sign = "-" if x < 0 else ""
                return f"{sign}1/{abs(int(round(1/x)))}"

            win = gui_overlay.PopupPlotWindow(title, self, lan)
            win.drawData(
                primary,
                xlabel=lan.get("station","Station [km]"),
                ylabel=lan.get("cant","Cant [mm]"),
                title=title,
                secondarySeries=secondary or None,
                secondaryYlabel=lan.get("curvature","Curvature [1/m]"),
                secondaryFormatter=fracFmt,
                symmetricYlim=True,
            )

        # ------------------------------------------------------------------
        elif graphId == "profile":
            title   = lan.get("profile", "Profile")
            primary = []
            annotations = []
            stV = lxml.get("stationVertical")
            elev = lxml.get("elevation")
            slp  = lxml.get("slope")
            if stV is not None and elev is not None and len(stV) > 0:
                primary.append(dict(x=stV, y=elev,
                                    label=lan.get("profile","Profile"),
                                    color='tab:gray', linestyle='-', marker='o'))
                if slp is not None and len(slp) > 0:
                    midX = (stV[:-1] + stV[1:]) / 2
                    midZ = (elev[:-1] + elev[1:]) / 2
                    for i in range(len(midX)):
                        annotations.append(dict(x=midX[i], y=float(midZ[i]) + 0.1,
                                                 text=f"{slp[i]:.2f} ‰", fontsize=6))
            win = gui_overlay.PopupPlotWindow(title, self, lan)
            win.drawData(primary,
                          xlabel=lan.get("station","Station [km]"),
                          ylabel=lan.get("elevation","Elevation [m]"),
                          title=title,
                          textAnnotations=annotations)

        # ------------------------------------------------------------------
        elif graphId == "tacho_track":
            title   = lan.get("kinematicsSpeedLimitTrack", "Speed–Distance")
            primary = []
            vehiclesSettTt = self.dataStorage.get("settingsData", {}).get("vehicles", [])
            for vIdx in range(numVehicles):
                stLim = self.dataStorage.get(f"stationSpeedLimitM_{vIdx}")
                spLim = self.dataStorage.get(f"speedLimitsM_{vIdx}")
                stKin = self.dataStorage.get(f"kinematicsStationM_{vIdx}")
                spKin = self.dataStorage.get(f"kinematicsSpeedM_{vIdx}")
                if stLim is not None and spLim is not None and len(stLim) > 0:
                    # Same ascending-sort fix as plotKinematics tacho_track
                    isRevTt = (vIdx < len(vehiclesSettTt) and
                                 vehiclesSettTt[vIdx].get("runReversed", False))
                    if isRevTt and len(stLim) > 1:
                        si = np.argsort(stLim)
                        stLimP = stLim[si]
                        spLimP = spLim[si]
                    else:
                        stLimP, spLimP = stLim, spLim
                    primary.append(dict(x=stLimP/dFactor, y=spLimP*vFactor,
                                        label=splimLbl+vehicleLabel(vIdx),
                                        color=limitColors[vIdx], step=True, marker='s',
                                        linestyle='--', alpha=0.7))
                if stKin is not None and spKin is not None and len(stKin) > 0:
                    primary.append(dict(x=stKin/dFactor, y=spKin*vFactor,
                                        label=spdLbl+vehicleLabel(vIdx),
                                        color=colorsSpeed[vIdx]))
            # Stop markers – vertical line at each station position
            axlines = []
            # Raw stops would miss the projected chainages entirely after an optimization
            trainStops = batch_metrics.stopsList(self.dataStorage)
            for stop in trainStops:
                try:
                    sM  = float(stop[0]) * 1000.0
                    name = str(stop[2]) if len(stop) > 2 else ""
                except (IndexError, ValueError):
                    continue
                al = dict(axis="x", pos=sM/dFactor,
                          color="gray", linestyle="--", alpha=0.7)
                if name:
                    al.update(label_text=f" {name}", label_rotation=90,
                              label_va="bottom", label_color="black",
                              label_fontsize=8, label_alpha=0.7, label_y=0)
                axlines.append(al)
            win = gui_overlay.PopupPlotWindow(title, self, lan)
            win.drawData(primary, xlabel=distLbl, ylabel=splimLbl,
                          title=title, axlines=axlines or None)

        # ------------------------------------------------------------------
        elif graphId == "tacho_time":
            title   = lan.get("kinematicsSpeedLimitTime", "Speed–Time")
            primary = []
            for vIdx in range(numVehicles):
                spLimT = self.dataStorage.get(f"speedLimitsT_{vIdx}")
                spLim   = self.dataStorage.get(f"speedLimitsM_{vIdx}")
                kinT    = self.dataStorage.get(f"kinematicsTimeS_{vIdx}")
                kinSp   = self.dataStorage.get(f"kinematicsSpeedM_{vIdx}")
                if spLimT is not None and spLim is not None and len(spLimT) > 0:
                    primary.append(dict(x=spLimT/tFactor, y=spLim*vFactor,
                                        label=splimLbl+vehicleLabel(vIdx),
                                        color=limitColors[vIdx], step=True, marker='s',
                                        linestyle='--', alpha=0.7))
                if kinT is not None and kinSp is not None and len(kinT) > 0:
                    pt, pv = expandStops(vIdx, kinT, kinSp)
                    primary.append(dict(x=pt/tFactor, y=pv*vFactor,
                                        label=spdLbl+vehicleLabel(vIdx),
                                        color=colorsSpeed[vIdx]))
            # Stop markers – vertical line at interpolated arrival time per vehicle
            axlines = []
            trainStops    = self.dataStorage.get("settingsData", {}).get("trainStops", [])
            vehiclesSett = self.dataStorage.get("settingsData", {}).get("vehicles", [])
            for stop in trainStops:
                try:
                    sM  = float(stop[0]) * 1000.0
                    name = str(stop[2]) if len(stop) > 2 else ""
                except (IndexError, ValueError):
                    continue
                for vIdx in range(numVehicles):
                    kinSt = self.dataStorage.get(f"kinematicsStationM_{vIdx}")
                    kinT2 = self.dataStorage.get(f"kinematicsTimeS_{vIdx}")
                    isRev = (vehiclesSett[vIdx].get("runReversed", False)
                              if vIdx < len(vehiclesSett) else False)
                    if kinSt is None or kinT2 is None or len(kinSt) == 0:
                        continue
                    xp, fp = kinSt, kinT2
                    if isRev:
                        xp, fp = kinSt[::-1], kinT2[::-1]
                    stopTime = np.interp(sM, xp, fp)
                    al = dict(axis="x", pos=stopTime/tFactor,
                              color=limitColors[vIdx], linestyle=":", alpha=0.5)
                    if name:
                        al.update(label_text=f" {name} (V{vIdx+1})",
                                  label_rotation=90, label_va="bottom",
                                  label_color=limitColors[vIdx],
                                  label_fontsize=7, label_alpha=0.7, label_y=0)
                    axlines.append(al)
            win = gui_overlay.PopupPlotWindow(title, self, lan)
            win.drawData(primary, xlabel=timeLbl, ylabel=splimLbl,
                          title=title, axlines=axlines or None)

        # ------------------------------------------------------------------
        elif graphId == "dist_time":
            title   = lan.get("kinematicsDistanceTime", "Distance–Time")
            primary = []
            for vIdx in range(numVehicles):
                spLimT = self.dataStorage.get(f"speedLimitsT_{vIdx}")
                stLim   = self.dataStorage.get(f"stationSpeedLimitM_{vIdx}")
                kinT    = self.dataStorage.get(f"kinematicsTimeS_{vIdx}")
                kinSt   = self.dataStorage.get(f"kinematicsStationM_{vIdx}")
                if spLimT is not None and stLim is not None and len(spLimT) > 0:
                    primary.append(dict(x=spLimT/tFactor, y=stLim/dFactor,
                                        label=splimLbl+vehicleLabel(vIdx),
                                        color=limitColors[vIdx], marker='s',
                                        linestyle='--', alpha=0.7))
                if kinT is not None and kinSt is not None and len(kinT) > 0:
                    pt, ps = expandStopsStation(vIdx, kinT, kinSt)
                    primary.append(dict(x=pt/tFactor, y=ps/dFactor,
                                        label=distLbl+vehicleLabel(vIdx),
                                        color=colorsSpeed[vIdx]))
            # Stop markers – horizontal line at each station position
            axlines = []
            # Raw stops would miss the projected chainages entirely after an optimization
            trainStops = batch_metrics.stopsList(self.dataStorage)
            for stop in trainStops:
                try:
                    sM  = float(stop[0]) * 1000.0
                    name = str(stop[2]) if len(stop) > 2 else ""
                except (IndexError, ValueError):
                    continue
                al = dict(axis="y", pos=sM/dFactor,
                          color="gray", linestyle="--", alpha=0.7)
                if name:
                    al.update(label_text=f" {name}", label_va="bottom",
                              label_color="black", label_fontsize=8,
                              label_alpha=0.7, label_x=0)
                axlines.append(al)
            win = gui_overlay.PopupPlotWindow(title, self, lan)
            win.drawData(primary, xlabel=timeLbl, ylabel=distLbl,
                          title=title, axlines=axlines or None)

        # ------------------------------------------------------------------
        elif graphId == "forces":
            title   = lan.get("kinematicsForces", "Forces Profile")
            primary = []
            for vIdx in range(numVehicles):
                kinSt = self.dataStorage.get(f"kinematicsStationM_{vIdx}")
                fTrac = self.dataStorage.get(f"kinematicsForceTractionKN_{vIdx}")
                fBrk  = self.dataStorage.get(f"kinematicsForceBrakingKN_{vIdx}")
                fRes  = self.dataStorage.get(f"kinematicsForceResistanceKN_{vIdx}")
                if kinSt is None or len(kinSt) == 0:
                    continue
                x = kinSt / dFactor
                for arr, col, lblKey in [
                    (fTrac, colorsTrac[vIdx],  "forceTraction"),
                    (fBrk,  colorsBrake[vIdx], "forceBraking"),
                    (fRes,  colorsRes[vIdx],   "forceResistance"),
                ]:
                    if arr is not None and len(arr) > 0:
                        primary.append(dict(x=x, y=arr,
                                            label=lan.get(lblKey, lblKey)+vehicleLabel(vIdx),
                                            color=col))
            win = gui_overlay.PopupPlotWindow(title, self, lan)
            win.drawData(primary,
                          xlabel=distLbl,
                          ylabel=lan.get("forceKN", "Force [kN]"),
                          title=title)

        else:
            return  # unknown id — do nothing

        # Adopt the active theme so the popup does not open with default colours
        win.applyTheme(self.themeManager.isDarkActive, self.themeManager.currentTokens)

        # Show window and keep reference alive so Qt doesn't GC it
        win.show()
        self.popupWindows.append(win)

    def cleanData(self):
        self.cleanLandXMLData()
        self.cleanTTPData()
        self.cleanCalculatedCants()
        self.cleanCalculatedSpeeds()

        keep = ["settingsData",]

        for key in list(self.dataStorage.keys()):
            if key not in keep:
                del self.dataStorage[key]

        self.baselineAlignmentCache = None
        self.optimizationImpactSignatureCache = None
        self.graphsWidget.clearSlewPlot()
        self.updateOptimizationActionState()

        # Reset the workflow guide and every plot along with the data
        self.workflowWidget.resetAll()
        self.graphsWidget.clearAll()
        self.profileWidget.clearAll()
        self.kinematicsWidget.clearAll()
        # A full clean must not leave a stale alignment behind on the map
        self.mapWidget.resetMap()
        self.batchResults.clear()
        self.variantDashboardWidget.clearAll()
        self.setEngineStatus(self.translationManager.getLanguage(self.currentLanguage).get("statusNoData", "No data"))
        self.updateStatusChainage(None)
        self.markProjectModified()

    def cleanTTPData(self):
        self.textboxRawTTP.setXmlText("")
        self.tableTTP.setData({})
        self.dataStorage["stationSpeedLimits"] = []
        self.dataStorage["speedLimits"] = []
        self.sourceStack.clearKind(source_stack.TTP_KIND)
        self.plotSpeedLimits()
        self.plotKinematics()
        # The geometry stays, only the speed colouring it fed has to be refreshed
        self.updateMapWithSpeeds()
        self.markProjectModified()

    def cleanLandXMLData(self):
        self.textboxRawLandXML.setXmlText("")
        self.tableLandXML.setData({})
        self.dataStorage["LandXML"] = {}
        self.sourceStack.clearKind(source_stack.LANDXML_KIND)
        self.plotCant()
        self.plotCurvature()
        self.plotProfile()
        # The alignment is gone, so the map must not keep showing it
        self.mapWidget.resetMap()
        self.markProjectModified()

    def cleanCalculatedCants(self):
        lxml = self.dataStorage.setdefault("LandXML", {})

        # Cant and cant-deficiency arrays
        for key in ["stationCantPossible", "cantPossible",
                    "cDef100", "cDef130", "cDef150", "cDefK",
                    "cantDef100", "cantDef130", "cantDef150", "cantDefK"]:
            lxml[key] = []

        # Rate-of-change arrays written by the geometry engine
        # (note: suffix is "100/130/150/K", no leading "I")
        for suffix in ["100", "130", "150", "K"]:
            lxml[f"dDdt{suffix}"] = []
            lxml[f"dIdt{suffix}"] = []

        # Utilisation and limit-reached flags (profile names: I100/I130/I150/K)
        for profile in ["I100", "I130", "I150", "K"]:
            lxml[f"util_D_{profile}"]        = []
            lxml[f"util_I_{profile}"]        = []
            lxml[f"limitReachedD_{profile}"] = []
            lxml[f"limitReachedI_{profile}"] = []

        self.clearOptimizationResults(refresh=False)
        self.reportGeometryWidget.setPlainText("")
        self.plotCant()
        self.plotSpeedLimits()

    def cleanCalculatedSpeeds(self):
        # Geometry-derived speed profiles (all four speed classes)
        for suffix in ["100", "130", "150", "K"]:
            self.dataStorage[f"stationSpeed{suffix}"] = []
            self.dataStorage[f"speedLimits{suffix}"]  = []

        # Per-vehicle kinematics and speed-limit arrays
        for vIdx in range(vehicle_catalog.MAX_VEHICLES):
            self.dataStorage[f"kinematicsStationM_{vIdx}"]        = []
            self.dataStorage[f"kinematicsSpeedM_{vIdx}"]          = []
            self.dataStorage[f"kinematicsTimeS_{vIdx}"]           = []
            self.dataStorage[f"kinematicsAcceleration_{vIdx}"]    = []
            self.dataStorage[f"kinematicsForceTractionKN_{vIdx}"] = []
            self.dataStorage[f"kinematicsForceBrakingKN_{vIdx}"]  = []
            self.dataStorage[f"kinematicsForceResistanceKN_{vIdx}"] = []
            self.dataStorage[f"kinematicsDwellTimesS_{vIdx}"]     = []
            self.dataStorage[f"stationSpeedLimitM_{vIdx}"]        = []
            self.dataStorage[f"speedLimitsM_{vIdx}"]              = []
            self.dataStorage[f"speedLimitsT_{vIdx}"]              = []
            # Warning flag — remove entirely so downstream code gets None / missing key
            self.dataStorage.pop(f"kinematicsWarning_{vIdx}", None)

        # A stale cache would be reprojected onto the flat keys the next time a tier is selected
        self.simulationResultsByProfile = {}
        self.dataStorage.pop("simulatedTrainStops", None)
        self.profileState.refreshAvailability(self.dataStorage)

        self.reportVehicleTable.setData({})
        self.plotSpeedLimits()
        self.plotKinematics()

    # Set visibility
    def toggleCantVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cant", isChecked)

    def toggleCantPossibleVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cantPossible", isChecked)

    def toggleCDef100Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cDef100", isChecked)

    def toggleCDef130Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cDef130", isChecked)

    def toggleCDef150Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cDef150", isChecked)

    def toggleCDefKVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cDefK", isChecked)

    def toggleCantDef100Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cantDef100", isChecked)

    def toggleCantDef130Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cantDef130", isChecked)

    def toggleCantDef150Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cantDef150", isChecked)

    def toggleCantDefKVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "cantDefK", isChecked)

    def toggleCurvatureVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "curvature", isChecked)

    def toggleCurvatureBaselineVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("geometry", "curvatureBaseline", isChecked)

    def toggleSpeedVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("speed", "speedLimits", isChecked)

    def toggleSpeed100Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("speed", "speedLimits100", isChecked)

    def toggleSpeed130Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("speed", "speedLimits130", isChecked)

    def toggleSpeed150Visibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("speed", "speedLimits150", isChecked)

    def toggleSpeedKVisibility(self, isChecked):
        self.graphsWidget.setSeriesVisible("speed", "speedLimitsK", isChecked)

    def toggleProfileVisibility(self, isChecked):
        self.profileWidget.setProfileVisible(isChecked)

    def toggleKinematicsSpeedLimitTrackVisibility(self, isChecked):
        self.kinematicsWidget.setPlotVisible("tachoTrack", isChecked)

    def toggleKinematicsSpeedLimitTimeVisibility(self, isChecked):
        self.kinematicsWidget.setPlotVisible("tachoTime", isChecked)

    def toggleKinematicsDistanceTimeVisibility(self, isChecked):
        self.kinematicsWidget.setPlotVisible("distTime", isChecked)

    def toggleKinematicsForcesVisibility(self, isChecked):
        self.kinematicsWidget.setPlotVisible("forces", isChecked)

    # Map settings
    def openMapSettings(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        dialog = gui_overlay.MapSettingsDialog(self.epsgInput, self.mapWidget.currentBaseMap,
                                               self.mapWidget.drawMode, self.mapWidget.speedProfile,
                                               lan, self, self.mapWidget.cartoApiKey)
        if dialog.exec():
            self.epsgInput, selectedMap, drawMode, speedProfile = dialog.getMapSettings()
            self.storeCartoApiKey(dialog.getBasemapApiKey(), lan)
            self.mapWidget.setBaseMap(selectedMap)
            self.mapWidget.setDrawOptions(drawMode, speedProfile)

    # Keep a changed CARTO key in the credential vault only, an empty field removes it
    def storeCartoApiKey(self, apiKey, lan):
        if apiKey == self.mapWidget.cartoApiKey:
            return
        isStored = basemap_key.saveKey(apiKey) if apiKey else basemap_key.deleteKey()
        if not isStored:
            self.setEngineStatus(lan.get(
                "mapApiKeyVaultFailed",
                "The CARTO key could not be saved securely and applies to this session only"))
        self.mapWidget.setCartoApiKey(apiKey)

    # Custom shortcuts and command aliases
    def openShortcutSettings(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        dialog = ShortcutSettingsDialog(self.shortcutManager.commands,
                                        self.shortcutManager.floatingInputEnabled, lan, self)
        if dialog.exec():
            self.shortcutManager.saveCommands(dialog.getCommands(), dialog.isFloatingInputEnabled())
            self.shortcutManager.applyShortcuts(self)

    # Save every live preference (layout, shortcuts, theme, units, default vehicles) to a portable file
    def exportPresets(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        defaultPath = str(getWritableRoot() / "config" / "presets.json")
        filepath, _ = QFileDialog.getSaveFileName(
            self, lan.get("exportPresets", "Export Presets..."), defaultPath, "JSON Files (*.json)")
        if not filepath:
            return

        try:
            payload = self.presetManager.buildPresetPayload(self)
            with open(filepath, "w", encoding="utf-8") as fileHandle:
                json.dump(payload, fileHandle, indent=2, ensure_ascii=False)
            self.statusBarWidget.showMessage(
                lan.get("statusPresetsExported", "Presets exported"), SERIES_STATUS_TIMEOUT)
        except OSError as exportError:
            QMessageBox.critical(self, lan.get("error", "Error"), str(exportError))

    # Load a portable presets file and confirm before it overwrites the current setup
    def importPresets(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        defaultPath = str(getWritableRoot() / "config" / "presets.json")
        filepath, _ = QFileDialog.getOpenFileName(
            self, lan.get("importPresets", "Import Presets..."), defaultPath, "JSON Files (*.json)")
        if not filepath:
            return

        try:
            with open(filepath, encoding="utf-8") as fileHandle:
                payload = json.load(fileHandle)
        except (OSError, json.JSONDecodeError) as importError:
            QMessageBox.critical(self, lan.get("error", "Error"), str(importError))
            return

        answer = QMessageBox.question(
            self, lan.get("importPresets", "Import Presets..."),
            lan.get("importPresetsConfirm",
                    "This replaces your current layout, shortcuts, theme and units. Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return

        # Rebuilding the dock layout inside the closing dialog crashes the embedded web view
        QTimer.singleShot(0, lambda: self.runPresetImport(payload))

    # Apply an imported presets payload once the confirm dialog has fully closed
    def runPresetImport(self, payload):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        try:
            self.presetManager.applyPresetPayload(self, payload)
            self.statusBarWidget.showMessage(
                lan.get("statusPresetsImported", "Presets imported"), SERIES_STATUS_TIMEOUT)
        except Exception as importError:
            QMessageBox.critical(self, lan.get("error", "Error"), str(importError))

    # Geometry settings
    def openGeometrySettings(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        dialog = gui_overlay.GeometrySettingsDialog(self.dataStorage.get("settingsData", {}), lan, self)
        if dialog.exec():
            self.dataStorage["settingsData"].update(dialog.getSettings())
            self.markProjectModified()

    # Vehicle settings
    def openVehicleSettings(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        dialog = VehicleSettingsDialog(self.dataStorage.get("settingsData", {}), lan,
                                       catalog=self.vehicleCatalog,
                                       isDarkActive=self.themeManager.isDarkActive,
                                       tokens=self.themeManager.currentTokens, parent=self)
        if dialog.exec():
            self.dataStorage["settingsData"].update(dialog.getSettings())
            # A newly added vehicle carries no direction of its own, so the shared one is restamped
            self.applyRunDirectionToVehicles()
            self.profileState.refreshAvailability(self.dataStorage)
            self.rebuildVehicleReportMenus()
            self.markProjectModified()
            # Step 4 of the workflow guide covers the vehicle definition
            self.workflowWidget.markCompleted(3)

    # Vehicle catalog browser, reachable standalone or from within Vehicle Settings
    def openVehicleCatalog(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        dialog = VehicleCatalogDialog(self.vehicleCatalog, lan,
                                      isDarkActive=self.themeManager.isDarkActive,
                                      tokens=self.themeManager.currentTokens, parent=self)
        dialog.exec()

    # Granular purge: segment manager plus optional calculation, stops and complete reset scopes
    def openPurgeDialog(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        dialog = PurgeDataDialog(self.sourceStack, lan, self)
        if dialog.exec():
            self.executePurgeRequest(dialog.getPurgeRequest())

    # Carry out the scopes and segment removals chosen in the purge dialog
    def executePurgeRequest(self, request):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        if request["completeReset"]:
            # Deferred so the closing modal never overlaps a folium rebuild, mirrors resetLayout
            QTimer.singleShot(0, self.performCompleteReset)
            return

        if request["removedSourceIds"]:
            self.applySourceRemovals(request["removedSourceIds"])

        if request["purgeResults"]:
            self.cleanCalculatedCants()
            self.cleanCalculatedSpeeds()

        if request["purgeStops"]:
            self.cleanTTPData()
            self.dataStorage.setdefault("settingsData", {})["trainStops"] = []

        self.refreshStations()
        self.plotKinematics()
        self.refreshTrackStatsDock()
        self.markProjectModified()
        self.statusBarWidget.showMessage(lan.get("purgeDone", "Purge completed"), SERIES_STATUS_TIMEOUT)

    # Wipe the entire project, the deferred complete reset scope of the purge dialog
    def performCompleteReset(self):
        self.cleanData()
        self.sourceStack.clearAll()
        self.mapWidget.clearViewState()
        self.dataStorage["settingsData"] = copy.deepcopy(default_values.defVal)
        self.mapWidget.resetMap()

        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.statusBarWidget.showMessage(lan.get("purgeDone", "Purge completed"), SERIES_STATUS_TIMEOUT)

    # Launch the batch configuration dialog and, once accepted, start the run on the next event loop turn
    def openBatchProcessing(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        if self.batchController.isRunning():
            QMessageBox.warning(self, lan.get("error", "Error"),
                                lan.get("batchAlreadyRunning", "A batch is already running"))
            return

        dialog = BatchProcessingDialog(self.dataStorage.get("settingsData", {}), self.batchConfigStore, lan, self)
        if dialog.exec():
            batchConfigData = dialog.getBatchConfig()
            # Deferred so the closing modal never overlaps building the progress dialog and starting a thread
            QTimer.singleShot(0, lambda: self.startBatchRun(batchConfigData))

    # Parse and merge every LandXML source, then expand the full cross product of variant specs
    def prepareBatchVariants(self, batchConfigData):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        problems = self.batchConfigStore.validateConfig(batchConfigData)
        if problems:
            raise ValueError("; ".join(lan.get(code, code) for code in problems))

        epsgInput = batchConfigData.get("epsgInput", "EPSG:5514")
        parsedList = []
        for source in batchConfigData["trackSources"]:
            fileContent = readfile.ReadFile().Read(source["filePath"])
            if not fileContent or fileContent.startswith("Error"):
                raise ValueError(f"{source.get('fileName', source['filePath'])}: {fileContent}")
            parsed = readfile.ReadFile().ParseLandXML(fileContent, epsgInput, source.get("alignmentIndex", 0))
            if "error" in parsed:
                raise ValueError(f"{source.get('fileName', source['filePath'])}: {parsed['error']}")
            parsedList.append(parsed)

        rebaseChainage = batchConfigData.get("chainageMode", "sequential") != "asImported"
        mergedLandXml, junctions = landxml_merger.concatAlignments(
            parsedList, startChainageKm=batchConfigData.get("startChainageKm", 0.0), rebaseChainage=rebaseChainage)

        warnJunctions = [j for j in junctions if j["gapMeters"] > landxml_merger.JUNCTION_GAP_WARN_M]
        if warnJunctions:
            gapText = ", ".join(f"{j['gapMeters']:.0f} m @ {j['stationKm']:.3f} km" for j in warnJunctions)
            QMessageBox.warning(self, lan.get("merge_gap_warning_title", "Warning"),
                                f"{lan.get('batchJunctionGapWarn', 'Large gap detected')}: {gapText}")

        variantSpecs = batch_config.expandVariantSpecs(batchConfigData)
        return variantSpecs, mergedLandXml, junctions

    # Enable or disable every action that would otherwise race a running batch against dataStorage
    def setBatchActionsEnabled(self, isEnabled):
        for actionName in ("calculateGeometryAction", "calculateGeometryIAction", "calculateTrainSpeedAction",
                          "cleanDataAction", "openPurgeDialogAction", "openBatchProcessingAction",
                          "exportBatchArchiveAction"):
            getattr(self, actionName).setEnabled(isEnabled)

    # Merge the configured LandXML files, expand the variant matrix, and hand it to the batch controller
    def startBatchRun(self, batchConfigData):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        try:
            variantSpecs, mergedLandXml, junctions = self.prepareBatchVariants(batchConfigData)
        except ValueError as exc:
            QMessageBox.critical(self, lan.get("error", "Error"), str(exc))
            return

        self.batchMergedLandXml = mergedLandXml
        self.batchJunctions = junctions
        self.batchResults.setBatchConfig(batchConfigData)

        self.batchProgressDialog = BatchProgressDialog(lan, self)
        self.batchProgressDialog.setVariantCount(len(variantSpecs))
        self.batchProgressDialog.setPhase(lan.get("batchProgressGeometry", "Calculating variants..."))
        self.batchProgressDialog.cancelRequested.connect(self.batchController.cancelBatch)
        self.batchProgressDialog.show()

        self.setBatchActionsEnabled(False)

        baseStorage = {"settingsData": batchConfigData.get("baseSettings", {})}
        self.batchController.startBatch(baseStorage, variantSpecs, mergedLandXml=mergedLandXml)

    # One variant has started, only used for progress feedback
    def onBatchVariantStarted(self, index, label):
        pass

    # One variant has finished, advance the progress dialog
    def onBatchVariantFinished(self, index, result):
        if self.batchProgressDialog is not None:
            self.batchProgressDialog.advance(index, result.get("spec", {}).get("label", result["variantId"]))

    # The whole batch has finished, successfully or partially (cancelled variants included)
    def onBatchFinished(self, results):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.batchResults.setResults(results)
        self.variantDashboardWidget.setResults(self.batchResults)
        self.refreshBatchVariantSelector()
        self.setBatchActionsEnabled(True)

        failedCount = sum(1 for result in results if result["status"] == "failed")
        cancelledCount = sum(1 for result in results if result["status"] == "cancelled")
        summaryText = lan.get("batchCancelled" if cancelledCount else "batchDone", "Batch completed")
        if self.batchProgressDialog is not None:
            self.batchProgressDialog.finish(summaryText)
        self.setEngineStatus(summaryText)
        self.showDashboardView()

        if failedCount:
            QMessageBox.warning(self, lan.get("error", "Error"),
                                f"{failedCount} variant(s) failed, see the batch progress log")

    # The worker thread raised an exception outside of a single variant's own try/except
    def onBatchFailed(self, message):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.setBatchActionsEnabled(True)
        if self.batchProgressDialog is not None:
            self.batchProgressDialog.finish(lan.get("batchFailed", "Batch failed"))
        QMessageBox.critical(self, lan.get("error", "Error"), message)

    # Package the last batch's reports, protocols and comparison data into one ZIP archive
    def exportBatchArchive(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        if self.batchResults.isEmpty():
            QMessageBox.warning(self, lan.get("error", "Error"), lan.get("dashboardNoResults", "No batch results yet"))
            return

        batchConfigData = self.batchResults.batchConfig()
        configName = batchConfigData.get("configName") or "batch"
        defaultName = f"COYPU_batch_{configName}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        zipPath, _ = QFileDialog.getSaveFileName(
            self, lan.get("exportBatchArchive", "Export batch reports to ZIP..."), defaultName, "ZIP Archive (*.zip)")
        if not zipPath:
            return

        exportFormats = batchConfigData.get("exportFormats", {"txt": True, "csv": True})

        progressDialog = BatchProgressDialog(lan, self)
        progressDialog.setVariantCount(len(self.batchResults.results()))
        progressDialog.setPhase(lan.get("batchProgressZip", "Packaging archive..."))
        # A synchronous write cannot be safely interrupted mid-archive
        progressDialog.cancelButton.setEnabled(False)
        progressDialog.show()
        QApplication.processEvents()

        exporter = batch_export.BatchArchiveExporter(self.batchResults, batchConfigData, lan,
                                                      mergedLandXml=self.batchMergedLandXml, junctions=self.batchJunctions)

        def onArchiveProgress(index, total):
            label = self.batchResults.results()[index].get("spec", {}).get("label", "")
            progressDialog.advance(index, label)
            QApplication.processEvents()

        try:
            with tempfile.TemporaryDirectory() as tmpDir:
                plotFormats = {key for key in ("png", "svg") if exportFormats.get(key)}
                plotImagePaths = self.variantDashboardWidget.exportPlotImages(tmpDir, plotFormats) if plotFormats else []
                exporter.exportArchive(zipPath, exportFormats, plotImagePaths, progressCallback=onArchiveProgress)
            progressDialog.finish(lan.get("batchDone", "Batch completed"))
            self.setEngineStatus(f"{lan.get('exportBatchArchive', 'Export batch reports to ZIP...')}: {zipPath}")
        except Exception as exc:
            progressDialog.finish(lan.get("batchFailed", "Batch failed"))
            QMessageBox.critical(self, lan.get("error", "Error"), str(exc))

    # Drop the chosen source stack entries and rebuild the affected datasets from the survivors
    def applySourceRemovals(self, removedSourceIds):
        for sourceId in removedSourceIds:
            self.sourceStack.removeEntry(sourceId)
        self.rebuildLandXMLFromStack()
        self.rebuildTtpFromStack()

    # Stops settings
    def openStopsSettings(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        dialog = gui_overlay.StopsSettingsDialog(self.dataStorage.get("settingsData", {}), lan, self)
        if dialog.exec():
            self.dataStorage["settingsData"].update(dialog.getSettings())
            # Step 3 of the workflow guide covers the scheduled stops
            self.workflowWidget.markCompleted(2)
            # New stops must reach the map and both station aware plots
            self.refreshStations()
            self.plotKinematics()
            self.markProjectModified()

    # Speed settings
    def openSpeedSettings(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        dialog = gui_overlay.SpeedSettingsDialog(self.dataStorage.get("settingsData", {}), lan, self)
        if dialog.exec():
            self.dataStorage["settingsData"].update(dialog.getSettings())
            self.markProjectModified()

    # Design approach settings
    def openDesignApproach(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        dialog = gui_overlay.DesignApproachDialog(self.dataStorage.get("settingsData", {}), lan, self)
        if dialog.exec():
            self.dataStorage["settingsData"]["designApproach"] = dialog.getDesignApproach()
            self.dataStorage["settingsData"]["disableGeometryMaxD"] = dialog.isGeometryMaxDDisabled()
            self.dataStorage["settingsData"]["balanceInflectionCants"] = dialog.isInflectionBalancingEnabled()
            self.markProjectModified()

    # Alignment optimization settings, opens the dialog and triggers the optimizer on accept
    def openAlignmentOptimization(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        dialog = gui_overlay.AlignmentOptimizationDialog(self.dataStorage.get("settingsData", {}), lan, self)
        if not dialog.exec():
            return
        if dialog.isRevertRequested:
            self.revertToBaselineAlignment()
            return

        self.dataStorage["settingsData"]["alignmentOptimization"] = dialog.getOptimizationConfig()
        self.markProjectModified()
        self.runAlignmentOptimization()

    # Help, reveals the documentation dock instead of opening a modal dialog
    def openHelp(self):
        self.dockHelp.show()
        self.dockHelp.raise_()
        self.helpWidget.reloadDocument()

    # Opens the Coypu Feeder companion project in the system default browser
    def openCoypuFeeder(self):
        QDesktopServices.openUrl(QUrl("https://github.com/surovskyjk/Coypu-Feeder"))

    # Reports
    def generateGeometryReport(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        lxml = self.dataStorage.get("LandXML", {})
        if not lxml or "stationCantPossible" not in lxml or len(lxml.get("stationCantPossible", [])) < 2:
            self.lastGeometryReportLines = [lan.get("no_data", "No data available. Calculate values first.")]
            self.reportGeometryWidget.setPlainText(self.lastGeometryReportLines[0])
            self.showReportView()
            return

        stations = lxml["stationCantPossible"]
        geomType = lxml.get("geometryType", [])

        # Localised element-type names used in report headers
        elemTypeNames = {
            "Curve":  lan.get("elemCurve",  "Curve"),
            "Spiral": lan.get("elemSpiral", "Spiral"),
            "Line":   lan.get("elemLine",   "Line"),
        }
        utilDLbl = lan.get("utilD", "Util D")
        utilILbl = lan.get("utilI", "Util I")
        
        if len(geomType) != len(stations):
            self.lastGeometryReportLines = [lan.get("error", "Error") + ": Data lengths do not match. Please recalculate."]
            self.reportGeometryWidget.setPlainText(self.lastGeometryReportLines[0])
            self.showReportView()
            return

        def safeGet(d, key, fallback):
            val = d.get(key)
            if val is None or len(val) != len(stations):
                return fallback
            return val

        cant = safeGet(lxml, "cantPossible", np.zeros_like(stations))
        cDef100 = safeGet(lxml, "cDef100", np.zeros_like(stations))
        cDef130 = safeGet(lxml, "cDef130", np.zeros_like(stations))
        cDef150 = safeGet(lxml, "cDef150", np.zeros_like(stations))
        cDefK = safeGet(lxml, "cDefK", np.zeros_like(stations))

        v100 = safeGet(self.dataStorage, "speedLimits100", np.zeros_like(stations))
        v130 = safeGet(self.dataStorage, "speedLimits130", np.zeros_like(stations))
        v150 = safeGet(self.dataStorage, "speedLimits150", np.zeros_like(stations))
        vK = safeGet(self.dataStorage, "speedLimitsK", np.zeros_like(stations))

        dDdt100 = safeGet(lxml, "dDdt100", np.zeros_like(stations))
        dIdt100 = safeGet(lxml, "dIdt100", np.zeros_like(stations))
        dDdt130 = safeGet(lxml, "dDdt130", np.zeros_like(stations))
        dIdt130 = safeGet(lxml, "dIdt130", np.zeros_like(stations))
        dDdt150 = safeGet(lxml, "dDdt150", np.zeros_like(stations))
        dIdt150 = safeGet(lxml, "dIdt150", np.zeros_like(stations))
        dDdtK = safeGet(lxml, "dDdtK", np.zeros_like(stations))
        dIdtK = safeGet(lxml, "dIdtK", np.zeros_like(stations))

        limD100 = safeGet(lxml, "limitReachedD_I100", np.zeros(len(stations), dtype=bool))
        limI100 = safeGet(lxml, "limitReachedI_I100", np.zeros(len(stations), dtype=bool))
        limD130 = safeGet(lxml, "limitReachedD_I130", np.zeros(len(stations), dtype=bool))
        limI130 = safeGet(lxml, "limitReachedI_I130", np.zeros(len(stations), dtype=bool))
        limD150 = safeGet(lxml, "limitReachedD_I150", np.zeros(len(stations), dtype=bool))
        limI150 = safeGet(lxml, "limitReachedI_I150", np.zeros(len(stations), dtype=bool))
        limDK = safeGet(lxml, "limitReachedD_K", np.zeros(len(stations), dtype=bool))
        limIK = safeGet(lxml, "limitReachedI_K", np.zeros(len(stations), dtype=bool))
        
        radius = safeGet(lxml, "radius", np.full(len(stations), np.inf))
        curvature = safeGet(lxml, "curvature", np.zeros_like(stations))

        utilD100 = safeGet(lxml, "util_D_I100", np.zeros_like(stations))
        utilI100 = safeGet(lxml, "util_I_I100", np.zeros_like(stations))
        utilD130 = safeGet(lxml, "util_D_I130", np.zeros_like(stations))
        utilI130 = safeGet(lxml, "util_I_I130", np.zeros_like(stations))
        utilD150 = safeGet(lxml, "util_D_I150", np.zeros_like(stations))
        utilI150 = safeGet(lxml, "util_I_I150", np.zeros_like(stations))
        utilDK = safeGet(lxml, "util_D_K", np.zeros_like(stations))
        utilIK = safeGet(lxml, "util_I_K", np.zeros_like(stations))

        reportLines = [lan.get("reportGeometryTitle", "=== Geometry Report ==="), ""]

        def calcN(LM, dVal, v):
            if abs(dVal) < 1e-3 or v < 1e-3: return "INF"
            return f"{LM * 1000 / (abs(dVal) * v):.2f}"
            
        def formatR(rVal):
            if np.isinf(rVal) or np.isnan(rVal): return "INF"
            return f"{rVal:.0f}"

        stats = {
            "V100": {"limit_D": 0, "limit_I": 0},
            "V130": {"limit_D": 0, "limit_I": 0},
            "V150": {"limit_D": 0, "limit_I": 0},
            "VK":   {"limit_D": 0, "limit_I": 0}
        }
        profileStats = {
            "V100": {"min_n": float('inf'), "min_nI": float('inf'), "min_nI_all": float('inf'), "min_nI_all_dI": 0.0, "max_dd_dt": 0.0, "max_di_dt": 0.0, "max_D": 0.0, "max_I": 0.0, "max_deltaI": 0.0, "weighted_util_sum_D": 0.0, "weighted_util_sum_I": 0.0, "total_length": 0.0},
            "V130": {"min_n": float('inf'), "min_nI": float('inf'), "min_nI_all": float('inf'), "min_nI_all_dI": 0.0, "max_dd_dt": 0.0, "max_di_dt": 0.0, "max_D": 0.0, "max_I": 0.0, "max_deltaI": 0.0, "weighted_util_sum_D": 0.0, "weighted_util_sum_I": 0.0, "total_length": 0.0},
            "V150": {"min_n": float('inf'), "min_nI": float('inf'), "min_nI_all": float('inf'), "min_nI_all_dI": 0.0, "max_dd_dt": 0.0, "max_di_dt": 0.0, "max_D": 0.0, "max_I": 0.0, "max_deltaI": 0.0, "weighted_util_sum_D": 0.0, "weighted_util_sum_I": 0.0, "total_length": 0.0},
            "VK":   {"min_n": float('inf'), "min_nI": float('inf'), "min_nI_all": float('inf'), "min_nI_all_dI": 0.0, "max_dd_dt": 0.0, "max_di_dt": 0.0, "max_D": 0.0, "max_I": 0.0, "max_deltaI": 0.0, "weighted_util_sum_D": 0.0, "weighted_util_sum_I": 0.0, "total_length": 0.0}
        }
        totalElements = 0
        
        limitsDI = self.dataStorage.get("settingsData", {}).get("dI", [])
        approach = self.dataStorage.get("settingsData", {}).get("designApproach", "standard")
        currAppDI = approach.get("dI", "standard") if isinstance(approach, dict) else approach
        colDI = {"standard": 2, "limit": 3, "minmax": 4}.get(currAppDI, 3)

        def getDeficiencyLimit(v):
            for row in limitsDI:
                if row[0] < v <= row[1]: return row[colDI]
            return limitsDI[-1][colDI] if limitsDI else 0

        for i in range(len(stations) - 1):
            L = (stations[i+1] - stations[i]) * 1000

            profiles = [
                ("V100", v100, cDef100, dDdt100, dIdt100, limD100, limI100, utilD100, utilI100),
                ("V130", v130, cDef130, dDdt130, dIdt130, limD130, limI130, utilD130, utilI130),
                ("V150", v150, cDef150, dDdt150, dIdt150, limD150, limI150, utilD150, utilI150),
                ("VK", vK, cDefK, dDdtK, dIdtK, limDK, limIK, utilDK, utilIK),
            ]

            if L <= 0:
                transitionData = []
                anyDeltaI = False
                dKappa = abs(curvature[i+1] - curvature[i])
                for pName, vArr, iArr, dDArr, dIArr, lDArr, lIArr, utilDArr, utilIArr in profiles:
                    vMin = min(vArr[i], vArr[i+1])
                    # Physical deltaI: D is continuous at L=0 boundary (Stage 3), so D cancels
                    deltaI = 11.8 * vMin**2 * dKappa if vMin > 1e-3 else 0.0
                    dILim = getDeficiencyLimit(vMin)
                    exceeded = deltaI > dILim + 1e-3
                    profileStats[pName]["max_deltaI"] = max(profileStats[pName]["max_deltaI"], deltaI)
                    transitionData.append((pName, deltaI, vMin, dILim, exceeded))
                    if deltaI > 1e-3:
                        anyDeltaI = True
                
                gTypeFrom = geomType[i] if i < len(geomType) else "-"
                gTypeTo = geomType[i+1] if i+1 < len(geomType) else "-"
                if anyDeltaI and gTypeFrom != "Spiral" and gTypeTo != "Spiral":
                    lblFrom = elemTypeNames.get(gTypeFrom, gTypeFrom)
                    lblTo   = elemTypeNames.get(gTypeTo,   gTypeTo)
                    reportLines.append(f"--- {lan.get('reportTransition', 'Transition')} | {lan['station']}: {stations[i]:.3f} | {lblFrom} -> {lblTo} ---")
                    for pName, dIVal, vVal, dILimVal, exceeded in transitionData:
                        flag = " (!)" if exceeded else ""
                        lineStr = f"  [{pName}] V: {vVal:.0f} km/h | deltaI: {dIVal:.0f} mm (limit {dILimVal:.0f} mm){flag}"
                        reportLines.append(lineStr)
                    reportLines.append("")
                continue
            
            gType = geomType[i]
            if gType in ["Curve", "Spiral"]:
                totalElements += 1

            rStart = radius[i] if i < len(radius) else float('inf')
            rEnd = radius[i+1] if i+1 < len(radius) else float('inf')
            
            maxVElem = max(v100[i], v100[i+1], v130[i], v130[i+1], v150[i], v150[i+1], vK[i], vK[i+1])
            xVal = L / maxVElem if maxVElem > 0 else float('inf')
            strX = f"{xVal:.2f}" if maxVElem > 0 else "INF"
            
            gTypeLbl  = elemTypeNames.get(gType, gType)
            headerLine = f"--- {gTypeLbl} | {lan['station']}: {stations[i]:.3f} - {stations[i+1]:.3f} | L = {L:.2f} m ({strX}*V)"
            if gType == "Curve":
                headerLine += f" | R: {formatR(rStart)} m"
            elif gType == "Spiral":
                headerLine += f" | R: {formatR(rStart)} -> {formatR(rEnd)} m"
            headerLine += " ---"
            reportLines.append(headerLine)

            for pName, vArr, iArr, dDArr, dIArr, lDArr, lIArr, utilDArr, utilIArr in profiles:
                vStart, vEnd = vArr[i], vArr[i+1]
                signDStart = np.sign(cant[i]) if cant[i] != 0 else 1.0
                signDEnd = np.sign(cant[i+1]) if cant[i+1] != 0 else 1.0
                dStart = signDStart * np.floor(np.abs(cant[i]))
                dEnd = signDEnd * np.floor(np.abs(cant[i+1]))
                signIStart = np.sign(iArr[i]) if iArr[i] != 0 else 1.0
                signIEnd = np.sign(iArr[i+1]) if iArr[i+1] != 0 else 1.0
                iStart = signIStart * np.ceil(np.abs(iArr[i]))
                iEnd = signIEnd * np.ceil(np.abs(iArr[i+1]))
                ddDt = dDArr[i]
                diDt = dIArr[i]

                profileStats[pName]["max_D"] = max(profileStats[pName]["max_D"], abs(dStart), abs(dEnd))
                profileStats[pName]["max_I"] = max(profileStats[pName]["max_I"], abs(iStart), abs(iEnd))
                profileStats[pName]["max_dd_dt"] = max(profileStats[pName]["max_dd_dt"], abs(ddDt))
                profileStats[pName]["max_di_dt"] = max(profileStats[pName]["max_di_dt"], abs(diDt))

                lineStr = f"  [{pName}] V: {vStart:.0f} -> {vEnd:.0f} km/h"
                if gType == "Curve":
                    lineStr += f" | D: {dStart:.0f} mm | I: {iStart:.0f} mm"
                elif gType == "Spiral":
                    dD = abs(dEnd - dStart)
                    dI = abs(iEnd - iStart)
                    
                    if dD > 1e-3 and vStart > 1e-3:
                        nValF = L * 1000 / (dD * vStart)
                        profileStats[pName]["min_n"] = min(profileStats[pName]["min_n"], nValF)
                    if dI > 1e-3 and vStart > 1e-3:
                        nIValF = L * 1000 / (dI * vStart)
                        if dI > getDeficiencyLimit(vStart):
                            profileStats[pName]["min_nI"] = min(profileStats[pName]["min_nI"], nIValF)
                        if nIValF < profileStats[pName]["min_nI_all"]:
                            profileStats[pName]["min_nI_all"] = nIValF
                            profileStats[pName]["min_nI_all_dI"] = dI
                        
                    nVal = calcN(L, dD, vStart)
                    nIVal = calcN(L, dI, vStart)
                    lineStr += f" | D: {dStart:.0f} -> {dEnd:.0f} mm | I: {iStart:.0f} -> {iEnd:.0f} mm | n: {nVal} | nI: {nIVal} | deltaI: {dI:.0f} mm | dD/dt: {ddDt:.2f} mm/s | dI/dt: {diDt:.2f} mm/s"

                utilDVal = max(utilDArr[i], utilDArr[i+1])
                utilIVal = max(utilIArr[i], utilIArr[i+1])
                lineStr += f" | {utilDLbl}: {utilDVal*100:.1f}% | {utilILbl}: {utilIVal*100:.1f}%"

                if gType in ["Curve", "Spiral"]:
                    profileStats[pName]["weighted_util_sum_D"] += utilDVal * L
                    profileStats[pName]["weighted_util_sum_I"] += utilIVal * L
                    profileStats[pName]["total_length"] += L

                if gType in ["Curve", "Spiral"]:
                    if lDArr[i] or lDArr[i+1]: stats[pName]["limit_D"] += 1
                    if lIArr[i] or lIArr[i+1]: stats[pName]["limit_I"] += 1

                reportLines.append(lineStr)
            reportLines.append("")

        reportLines.append(lan.get("reportStatisticsTitle", "=== Limiting Factors Statistics ==="))
        reportLines.append(f"{lan.get('totalElements', 'Total evaluated elements (Curve/Spiral)')}: {totalElements}")
        reportLines.append("")

        for pName in ["V100", "V130", "V150", "VK"]:
            reportLines.append(f"--- {pName} ---")
            reportLines.append(f"  {lan.get('lim_D', 'D (Cant)')} limit: {stats[pName]['limit_D']}x")
            reportLines.append(f"  {lan.get('lim_I', 'I (Cant Deficiency)')} limit: {stats[pName]['limit_I']}x")
            reportLines.append("")

        reportLines.append(lan.get("reportExtremesTitle", "=== Extremes of Geometric Parameters ==="))
        reportLines.append("")

        for pName in ["V100", "V130", "V150", "VK"]:
            reportLines.append(f"--- {pName} ---")
            pStats = profileStats[pName]
            
            strN = f"{pStats['min_n']:.2f}" if pStats['min_n'] != float('inf') else "-"
            strNI = f"{pStats['min_nI']:.2f}" if pStats['min_nI'] != float('inf') else "-"
            strNIAll = f"{pStats['min_nI_all']:.2f} (deltaI = {pStats['min_nI_all_dI']:.0f} mm)" if pStats['min_nI_all'] != float('inf') else "-"
            
            weightedAvgUtilD = pStats["weighted_util_sum_D"] / pStats["total_length"] if pStats["total_length"] > 0 else 0.0
            weightedAvgUtilI = pStats["weighted_util_sum_I"] / pStats["total_length"] if pStats["total_length"] > 0 else 0.0
            reportLines.append(f"  {lan.get('stat_weighted_avg_util_D', 'Weighted Avg Util D [-]')}: {weightedAvgUtilD*100:.2f}%")
            reportLines.append(f"  {lan.get('stat_weighted_avg_util_I', 'Weighted Avg Util I [-]')}: {weightedAvgUtilI*100:.2f}%")

            reportLines.append(f"  {lan.get('stat_min_n', 'Min n [-]')}: {strN}")
            reportLines.append(f"  {lan.get('stat_min_nI', 'Min nI [-]')}: {strNI}")
            reportLines.append(f"  {lan.get('stat_min_nI_all', 'Min nI (all) [-]')}: {strNIAll}")
            reportLines.append(f"  {lan.get('stat_max_dDdt', 'Max dD/dt [mm/s]')}: {pStats['max_dd_dt']:.2f}")
            reportLines.append(f"  {lan.get('stat_max_dIdt', 'Max dI/dt [mm/s]')}: {pStats['max_di_dt']:.2f}")
            reportLines.append(f"  {lan.get('stat_max_D', 'Max D [mm]')}: {pStats['max_D']:.0f}")
            reportLines.append(f"  {lan.get('stat_max_I', 'Max I [mm]')}: {pStats['max_I']:.0f}")
            reportLines.append(f"  {lan.get('stat_max_deltaI', 'Max deltaI [mm]')}: {pStats['max_deltaI']:.0f}")
            reportLines.append("")

        if self.includeSlewSectionAction.isChecked() and lxml.get("optimizationSummary"):
            reportLines.append("")
            reportLines.extend(slew_report.buildSlewReportLines(self.dataStorage, lan))

        self.lastGeometryReportLines = reportLines
        self.reportGeometryWidget.setPlainText("\n".join(reportLines))
        self.showReportView()

    # Every computed value both the on-screen table and every export format need, gathered once
    def computeVehicleRunMetrics(self, vIdx=0):
        stations = self.dataStorage.get(f"kinematicsStationM_{vIdx}", [])
        metrics = {"hasData": len(stations) > 0}
        if not metrics["hasData"]:
            return metrics

        speeds = self.dataStorage.get(f"kinematicsSpeedM_{vIdx}", np.zeros_like(stations))
        accels = self.dataStorage.get(f"kinematicsAcceleration_{vIdx}", np.zeros_like(stations))
        fTrac = self.dataStorage.get(f"kinematicsForceTractionKN_{vIdx}", np.zeros_like(stations))
        fBrake = self.dataStorage.get(f"kinematicsForceBrakingKN_{vIdx}", np.zeros_like(stations))
        fRes = self.dataStorage.get(f"kinematicsForceResistanceKN_{vIdx}", np.zeros_like(stations))
        times = self.dataStorage.get(f"kinematicsTimeS_{vIdx}", [])
        hasTimes = len(times) == len(stations)

        metrics.update({
            "vehicleName": self.getVehicleName(vIdx),
            "stations": stations, "speeds": speeds, "accels": accels,
            "fTrac": fTrac, "fBrake": fBrake, "fRes": fRes, "times": times, "hasTimes": hasTimes,
        })

        # Every 10th point + always include first and last (V=0 endpoints)
        stepIndices = list(range(0, len(stations), 10))
        if len(stations) - 1 not in stepIndices:
            stepIndices.append(len(stations) - 1)
        metrics["stepIndices"] = stepIndices

        # Travel time, average speed, and maximum speed
        metrics["summary"] = None
        if len(stations) > 1 and len(times) > 1:
            totalDistanceM = abs(stations[-1] - stations[0])
            totalTimeS = times[-1]
            avgSpeedMs = totalDistanceM / totalTimeS if totalTimeS > 0 else 0
            metrics["summary"] = {
                "totalTimeS": totalTimeS,
                "avgSpeedKmh": avgSpeedMs * 3.6,
                "maxSpeedKmh": float(np.max(speeds)) * 3.6 if len(speeds) > 0 else 0.0,
            }

        # Energy calculation (use abs(dx) so reversed vehicles give positive values)
        dx = np.abs(np.diff(stations))
        dx = np.append(dx, 0)
        metrics["energyKwh"] = float(np.sum(fTrac * dx) / 3600.0)
        metrics["brakeEnergyKwh"] = float(np.sum(fBrake * dx) / 3600.0)

        # Train stops matched against the sampled stations
        metrics["stopsRows"] = []
        # Raw stops would miss the projected chainages entirely after an optimization
        trainStops = batch_metrics.orderStopsForRun(batch_metrics.stopsList(self.dataStorage),
                                                    stations)
        if trainStops:
            for stop in trainStops:
                try:
                    sKm = float(stop[0])
                    dwell = float(stop[1])
                    name = str(stop[2]) if len(stop) > 2 else ""
                    sM = sKm * 1000.0
                    idx = np.argmin(np.abs(stations - sM))
                    if np.abs(stations[idx] - sM) < 2.0:
                        depTime = times[idx] if hasTimes else 0.0
                        arrTime = max(0.0, depTime - dwell)
                        metrics["stopsRows"].append({
                            "stationKm": sKm, "name": name,
                            "arrivalS": arrTime, "departureS": depTime, "dwellS": dwell,
                        })
                except Exception:
                    continue

        return metrics

    # Table-dict rows for the shared pg.TableWidget report view
    def buildVehicleReportTableRows(self, metrics, lan):
        kSta   = lan.get("station", "Station [km]")
        kTime  = lan.get("time", "Time [s]")
        kSpd   = lan.get("speed", "Speed [km/h]")
        kAcc   = lan.get("accel", "Accel [m/s²]")
        kTrac  = lan.get("forceTraction", "Tractive Force [kN]")
        kBrake = lan.get("forceBraking", "Braking Force [kN]")
        kRes   = lan.get("forceResistance", "Resistance [kN]")

        tableData = []

        summaryTitle = lan.get('run_summary_title', 'RUN SUMMARY')
        if metrics["vehicleName"]:
            summaryTitle = f"{summaryTitle} — {metrics['vehicleName']}"

        if metrics["summary"]:
            minutes, seconds = divmod(metrics["summary"]["totalTimeS"], 60)
            tableData.append({
                kSta:   f"=== {summaryTitle} ===",
                kTime:  "",
                kSpd:   lan.get('total_travel_time', 'Total travel time:'),
                kAcc:   f"{int(minutes):02d} min {int(seconds):02d} s",
                kTrac:  lan.get('average_speed', 'Average speed:'),
                kBrake: f"{metrics['summary']['avgSpeedKmh']:.2f} km/h",
                kRes:   f"{lan.get('maxSpeed_achieved', 'Max speed:')} {metrics['summary']['maxSpeedKmh']:.0f} km/h"
            })
            tableData.append({k: "---" for k in tableData[0].keys()})

        tableData.append({
            kSta:   f"=== {lan.get('energy_title', 'ENERGY')} ===",
            kTime:  "",
            kSpd:   f"{lan.get('energyTraction', 'Traction [kWh]')}:",
            kAcc:   f"{metrics['energyKwh']:.2f}",
            kTrac:  f"{lan.get('energyBraking', 'Braking [kWh]')}:",
            kBrake: f"{metrics['brakeEnergyKwh']:.2f}",
            kRes:   ""
        })
        tableData.append({k: "---" for k in tableData[0].keys()})

        if metrics["stopsRows"]:
            tableData.append({
                kSta: f"=== {lan.get('stopsHeader', 'STOPS')} ===", kTime: "", kSpd: "",
                kAcc: "", kTrac: "", kBrake: "", kRes: ""
            })
            for stop in metrics["stopsRows"]:
                tableData.append({
                    kSta:   f"{stop['stationKm']:.3f} {stop['name']}",
                    kTime:  "",
                    kSpd:   f"Arr: {stop['arrivalS']:.1f} s",
                    kAcc:   f"Dep: {stop['departureS']:.1f} s",
                    kTrac:  f"Dwell: {stop['dwellS']} s",
                    kBrake: "-",
                    kRes:   "-"
                })
            tableData.append({k: "---" for k in tableData[0].keys()})

        for i in metrics["stepIndices"]:
            sKm = metrics["stations"][i] / 1000.0
            tableData.append({
                kSta:   f"{sKm:.3f}",
                kTime:  f"{metrics['times'][i]:.1f}" if metrics["hasTimes"] else "",
                kSpd:   f"{metrics['speeds'][i]*3.6:.1f}",
                kAcc:   f"{metrics['accels'][i]:.3f}",
                kTrac:  f"{metrics['fTrac'][i]:.1f}",
                kBrake: f"{metrics['fBrake'][i]:.1f}",
                kRes:   f"{metrics['fRes'][i]:.1f}"
            })

        return tableData

    # Flat text lines for txt/pdf/md/tex export, using the "=== TITLE ===" section convention
    def buildVehicleReportLines(self, metrics, lan):
        reportLines = []

        summaryTitle = lan.get('run_summary_title', 'RUN SUMMARY')
        if metrics["vehicleName"]:
            summaryTitle = f"{summaryTitle} — {metrics['vehicleName']}"
        reportLines.append(f"=== {summaryTitle} ===")
        if metrics["summary"]:
            minutes, seconds = divmod(metrics["summary"]["totalTimeS"], 60)
            reportLines.append(f"{lan.get('total_travel_time', 'Total travel time:')} {int(minutes):02d} min {int(seconds):02d} s")
            reportLines.append(f"{lan.get('average_speed', 'Average speed:')} {metrics['summary']['avgSpeedKmh']:.2f} km/h")
            reportLines.append(f"{lan.get('maxSpeed_achieved', 'Max speed:')} {metrics['summary']['maxSpeedKmh']:.0f} km/h")
        reportLines.append("")

        reportLines.append(f"=== {lan.get('energy_title', 'ENERGY')} ===")
        reportLines.append(f"{lan.get('energyTraction', 'Traction [kWh]')}: {metrics['energyKwh']:.2f}")
        reportLines.append(f"{lan.get('energyBraking', 'Braking [kWh]')}: {metrics['brakeEnergyKwh']:.2f}")
        reportLines.append("")

        if metrics["stopsRows"]:
            reportLines.append(f"=== {lan.get('stopsHeader', 'STOPS')} ===")
            for stop in metrics["stopsRows"]:
                reportLines.append(
                    f"{stop['stationKm']:.3f} km  {stop['name']}  "
                    f"Arr: {stop['arrivalS']:.1f}s  Dep: {stop['departureS']:.1f}s  Dwell: {stop['dwellS']:.0f}s")
            reportLines.append("")

        reportLines.append(f"=== {lan.get('dataSectionTitle', 'DATA')} ===")
        reportLines.append(
            f"{lan.get('station', 'Station [km]'):>12} {lan.get('time', 'Time [s]'):>10} "
            f"{lan.get('speed', 'Speed [km/h]'):>10} {lan.get('accel', 'Accel [m/s²]'):>10} "
            f"{lan.get('forceTraction', 'Tractive Force [kN]'):>14} "
            f"{lan.get('forceBraking', 'Braking Force [kN]'):>14} "
            f"{lan.get('forceResistance', 'Resistance [kN]'):>14}")
        for i in metrics["stepIndices"]:
            sKm = metrics["stations"][i] / 1000.0
            timeStr = f"{metrics['times'][i]:.1f}" if metrics["hasTimes"] else ""
            reportLines.append(
                f"{sKm:12.3f} {timeStr:>10} {metrics['speeds'][i]*3.6:10.1f} {metrics['accels'][i]:10.3f} "
                f"{metrics['fTrac'][i]:14.1f} {metrics['fBrake'][i]:14.1f} {metrics['fRes'][i]:14.1f}")

        return reportLines

    def generateVehicleReport(self, vIdx=0):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.lastVehicleReportIndex = vIdx
        metrics = self.computeVehicleRunMetrics(vIdx)
        if not metrics["hasData"]:
            self.reportVehicleTable.setData([{"Info": lan.get("no_data", "No data available. Calculate values first.")}])
            self.showReportView()
            return

        self.reportVehicleTable.setData(self.buildVehicleReportTableRows(metrics, lan))
        self.showReportView()

    def exportGeometryReport(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        content = self.reportGeometryWidget.toPlainText()
        if not content:
            QMessageBox.warning(self, lan.get("error", "Error"), lan.get("no_data", "No data available. Calculate values first."))
            return

        reportFilter = "Text (*.txt);;PDF (*.pdf);;Markdown (*.md);;LaTeX (*.tex);;CSV (*.csv)"
        filepath, _ = QFileDialog.getSaveFileName(
            self, lan.get("exportGeometryReport", "Export Geometry Report"), "", reportFilter)
        if not filepath:
            return

        try:
            titleText = lan.get("reportGeometryTitle", "Geometry Report")
            reportLines = self.lastGeometryReportLines or content.splitlines()
            if filepath.lower().endswith(".csv"):
                report_formats.rowsToCsv(filepath, [titleText], [[line] for line in reportLines])
            else:
                report_formats.writeReportFile(reportLines, filepath, titleText)
        except Exception as e:
            QMessageBox.critical(self, lan.get("error", "Error"), f"{e}")

    def exportVehicleReport(self, vIdx=0):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        metrics = self.computeVehicleRunMetrics(vIdx)
        if not metrics["hasData"]:
            QMessageBox.warning(self, lan.get("error", "Error"), lan.get("no_data", "No data available. Calculate values first."))
            return

        reportFilter = "Text (*.txt);;PDF (*.pdf);;Markdown (*.md);;LaTeX (*.tex);;CSV (*.csv)"
        filepath, _ = QFileDialog.getSaveFileName(
            self, lan.get("exportVehicleReport", "Export Vehicle Report"), "", reportFilter)
        if not filepath:
            return

        try:
            titleText = lan.get("reportVehicleTitle", "Vehicle Report")
            if metrics["vehicleName"]:
                titleText = f"{titleText} — {metrics['vehicleName']}"

            if filepath.lower().endswith(".csv"):
                headerRow = [lan.get("station", "Station [km]"), lan.get("time", "Time [s]"),
                            lan.get("speed", "Speed [km/h]"), "Accel [m/s2]",
                            lan.get("forceTraction", "Tractive Force [kN]"),
                            lan.get("forceBraking", "Braking Force [kN]"),
                            lan.get("forceResistance", "Resistance [kN]")]
                dataRows = [[f"{metrics['stations'][i]/1000.0:.3f}",
                            f"{metrics['times'][i]:.1f}" if metrics["hasTimes"] else "",
                            f"{metrics['speeds'][i]*3.6:.1f}", f"{metrics['accels'][i]:.3f}",
                            f"{metrics['fTrac'][i]:.1f}", f"{metrics['fBrake'][i]:.1f}",
                            f"{metrics['fRes'][i]:.1f}"] for i in range(len(metrics["stations"]))]
                report_formats.rowsToCsv(filepath, headerRow, dataRows)
            else:
                reportLines = self.buildVehicleReportLines(metrics, lan)
                report_formats.writeReportFile(reportLines, filepath, titleText)
        except Exception as e:
            QMessageBox.critical(self, lan.get("error", "Error"), f"{e}")

    # Store the parsed data and defer the table build until the dock is visible
    def updateTableLandXML(self, data):
        self.pendingLandXmlTableData = data
        self.dockLandXmlParsed.requestUpdate()

    # Build the LandXML overview table from the last parsed dataset
    def renderTableLandXML(self):
        data = getattr(self, "pendingLandXmlTableData", None)
        if not data:
            return

        stations = np.concatenate((data["stationCant"], data["stationHorizontal"], data["stationVertical"]))
        uniqueStations = np.unique(stations)
        tableData = []
        lan = self.translationManager.getLanguage(self.currentLanguage)
        for station in uniqueStations:
            cant = data["cant"][np.where(data["stationCant"] == station)]
            horizontalRadius = data["radius"][np.where(data["stationHorizontal"] == station)]
            horizonralCurvature = data["curvature"][np.where(data["stationHorizontal"] == station)]
            vertical = data["elevation"][np.where(data["stationVertical"] == station)]
            tableData.append({
                lan["station"]: station,
                lan["cant"]: cant[0] if len(cant) > 0 else "",
                lan["radius"]: horizontalRadius[0] if len(horizontalRadius) > 0 else "",
                lan["curvature"]: horizonralCurvature[0] if len(horizonralCurvature) > 0 else "",
                lan["elevation"]: vertical[0] if len(vertical) > 0 else "",
            })
        # Plot data in table    
        self.tableLandXML.setData(tableData)

    # Split station array into monotone sections on direction reversal or gap over 20 km
    # Tracks the last non-zero diff so duplicate stations do not mask a later reversal
    def TTPSections(self, stations):
        if len(stations) == 0:
            return []

        sections = []
        startID = 0
        prevNonzeroDiff = 0   # direction of the most recent non-zero step

        for i in range(1, len(stations)):
            diff = stations[i] - stations[i-1]

            isBoundary = abs(diff) > 20

            if not isBoundary and diff != 0:
                if prevNonzeroDiff != 0 and np.sign(diff) != np.sign(prevNonzeroDiff):
                    isBoundary = True
                prevNonzeroDiff = diff   # update only on non-zero steps

            if isBoundary:
                sections.append({
                    "startID": startID,
                    "endID": i - 1,
                    "stationStart": stations[startID],
                    "stationEnd": stations[i - 1]
                })
                startID = i
                # Reset: direction of the new section is unknown until we see its
                # first non-zero step; setting to 0 avoids a false split at i+1.
                prevNonzeroDiff = 0

        # Add the last section
        sections.append({
            "startID": startID,
            "endID": len(stations) - 1,
            "stationStart": stations[startID],
            "stationEnd": stations[len(stations) - 1]
        })

        return sections

    @staticmethod
    # Fix post-step semantics for a descending-order TTP section
    # After ascending sort, getSpeedLimitAt assigns each sign limit one segment too early
    # The fix inserts a synthetic station at stations[0]-1e-6 and appends the last limit
    # so every limit applies to the interval below its sign, and is a no-op when ascending
    def correctReversedTTPSection(secStations, secLimits):
        if len(secStations) <= 1:
            return secStations, secLimits

        # Only transform sections that were originally in descending order
        if secStations[0] <= secStations[-1]:
            return secStations, secLimits

        sortIdx = np.argsort(secStations, kind='stable')
        stAsc = secStations[sortIdx]
        spAsc = secLimits[sortIdx]

        # Prepend a synthetic point 1 µm below the lowest real sign.
        # It carries the lowest sign's own limit so that getSpeedLimitAt(x)
        # for x < st_asc[0] still returns the correct value (sp_asc[0]).
        stationsOut = np.concatenate(([stAsc[0] - 1e-6], stAsc))
        # Each sign's limit now applies from just-below its own km up to the
        # next sign's km (the shift gives post-step semantics in ascending order).
        limitsOut = np.append(spAsc, spAsc[-1])
        return stationsOut, limitsOut

    # Profiles whose descent ran out of its iteration or time budget, so their D, I and
    # speeds were designed for a trial speed the solver never actually reached
    def unconvergedProfiles(self):
        lxml = self.dataStorage.get("LandXML", {})
        return [profile for profile in ("I100", "I130", "I150", "K")
                if lxml.get(f"converged_{profile}") is False]

    # Tell the user when the published cant design is provisional rather than converged
    def reportConvergenceWarnings(self):
        unconverged = self.unconvergedProfiles()
        if not unconverged:
            return
        lan = self.translationManager.getLanguage(self.currentLanguage)
        template = lan.get("geometryNotConverged",
                           "The cant design did not converge for {profiles}. The reported cant "
                           "and speeds are provisional; raise the iteration step or lower the "
                           "initial speed and run it again.")
        QMessageBox.warning(self, lan.get("error", "Error"),
                            template.format(profiles=", ".join(unconverged)))

    # One guarded entry point for both cant design modes. setLoopsData zeroes every result
    # array before it computes anything, so an engine error escaping here used to leave a
    # corridor of zeroes on the plots looking exactly like a finished calculation.
    def runCantDesign(self, isAsBuilt):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        calculate = geometry_engine.GeometryCalculator(self.dataStorage)
        try:
            if isAsBuilt:
                calculate.runCalculationLoopI()
            else:
                calculate.runCalculationLoop()
        except Exception as exc:
            self.cleanCalculatedCants()
            self.cleanCalculatedSpeeds()
            self.setEngineStatus(lan.get("geometryFailed", "Cant design failed"))
            QMessageBox.critical(self, lan.get("error", "Error"), str(exc))
            return False
        return True

    def calculateGeometry(self):

        if "alignmentCoordinates" not in self.dataStorage.get("LandXML",{}):
            return
        
        self.lastCalculationMode = "design"
        if not self.runCantDesign(isAsBuilt=False):
            return

        self.updateMapWithSpeeds()
        self.plotCant()
        self.plotSpeedLimits()
        self.geometryCalculationFinished.emit()

        # Step 6 of the workflow guide covers the cant design
        self.workflowWidget.markCompleted(5)
        self.setEngineStatus(self.translationManager.getLanguage(self.currentLanguage).get("statusGeometryDone", "Geometry calculated"))
        self.markProjectModified()
        self.reportConvergenceWarnings()

    def calculateGeometryI(self):

        if "alignmentCoordinates" not in self.dataStorage.get("LandXML",{}):
            return
        
        self.lastCalculationMode = "asBuilt"
        if not self.runCantDesign(isAsBuilt=True):
            return

        self.updateMapWithSpeeds()
        self.plotCant()
        self.plotSpeedLimits()
        self.geometryCalculationFinished.emit()

        # Step 6 of the workflow guide covers the cant design
        self.workflowWidget.markCompleted(5)
        self.setEngineStatus(self.translationManager.getLanguage(self.currentLanguage).get("statusGeometryDone", "Geometry calculated"))
        self.markProjectModified()
        self.reportConvergenceWarnings()

    # Launches the parametric slew/spiral optimizer on a worker thread, additive to the baseline
    def runAlignmentOptimization(self):
        lxml = self.dataStorage.get("LandXML", {})
        if "alignmentCoordinates" not in lxml:
            return
        if self.optimizationController.isRunning():
            return

        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.captureBaselineAlignment()
        # Every run is measured against the imported alignment, never against a previous optimization
        self.restoreBaselineAlignmentData()
        self.clearOptimizationResults(refresh=False)
        self.publishBaselineComparison()

        config = self.dataStorage.get("settingsData", {}).get("alignmentOptimization", {})
        self.alignmentOptimizationAction.setEnabled(False)
        self.setEngineStatus(lan.get("statusOptimizationRunning", "Optimizing alignment..."))
        # Phase 2 reshapes geometry only, the cant and speed design stays an explicit separate step
        self.optimizationController.startOptimization(self.dataStorage, config,
                                                      self.lastCalculationMode, self.epsgInput,
                                                      isGeometryOnly=True)

    # One immutable deepcopy of the untouched baseline, taken before the first optimization run
    def captureBaselineAlignment(self):
        if self.baselineAlignmentCache is not None:
            return
        cache = {"LandXML": copy.deepcopy(self.dataStorage.get("LandXML", {}))}
        # Imported TTP chainages are projected onto the optimized axis, so the baseline copy has
        # to come back before another run, otherwise the projection would be applied twice
        for storageKey in ("stationSpeedLimits", "speedLimits"):
            if self.dataStorage.get(storageKey) is not None:
                cache[storageKey] = copy.deepcopy(self.dataStorage[storageKey])
        for profileSuffix in OPTIMIZED_PROFILE_SUFFIXES:
            for storageKey in (f"speedLimits{profileSuffix}", f"stationSpeed{profileSuffix}"):
                if self.dataStorage.get(storageKey) is not None:
                    cache[storageKey] = copy.deepcopy(self.dataStorage[storageKey])

        # The travel time delta needs the run the baseline geometry produced, not just its limits
        for resultKey in optimization_runner.KINEMATICS_RESULT_KEYS:
            baselineValues = self.dataStorage.get(f"{resultKey}_0")
            if baselineValues is not None:
                cache[f"{resultKey}_0"] = copy.deepcopy(baselineValues)

        # The cached baseline run belongs to one set of vehicles and one timetable. Comparing a
        # new run against it after either changed would report a delta between two journeys.
        cache["runSignature"] = self.baselineRunSignature()
        self.baselineAlignmentCache = cache

    # Everything the cached baseline kinematics depended on, so a vehicle or timetable edit
    # invalidates it instead of being compared against a journey that no longer exists
    def baselineRunSignature(self):
        settingsData = self.dataStorage.get("settingsData", {})
        return json.dumps({"vehicles": settingsData.get("vehicles"),
                           "trainStops": settingsData.get("trainStops"),
                           "runReversed": settingsData.get("runReversed")},
                          sort_keys=True, default=str)

    # Puts the imported geometry back into the active keys, leaving every view refresh to the caller
    def restoreBaselineAlignmentData(self):
        if self.baselineAlignmentCache is None:
            return
        self.dataStorage["LandXML"] = copy.deepcopy(self.baselineAlignmentCache["LandXML"])
        for storageKey, values in self.baselineAlignmentCache.items():
            if storageKey not in ("LandXML", "runSignature"):
                self.dataStorage[storageKey] = copy.deepcopy(values)

    # The curvature plot and the map keep a muted baseline to compare the active geometry against
    def publishBaselineComparison(self):
        baselineLxml = (self.baselineAlignmentCache or {}).get("LandXML", {})
        lxml = self.dataStorage.setdefault("LandXML", {})
        for baseKey in BASELINE_COMPARISON_KEYS:
            values = baselineLxml.get(baseKey)
            if values is not None:
                lxml[baseKey + BASELINE_KEY_SUFFIX] = copy.deepcopy(values)

    # A geometry change invalidates every cant, speed and kinematics result computed before it
    def clearCalculatedResults(self):
        lxml = self.dataStorage.setdefault("LandXML", {})
        # The optimizer's own output describes the geometry, so a cant rerun must not erase it
        for storageKey in [key for key in lxml
                           if project_file.isCalculatedLandXmlKey(key)
                           and not key.endswith(BASELINE_KEY_SUFFIX)
                           and key not in OPTIMIZATION_STATE_KEYS]:
            lxml.pop(storageKey, None)

        for profileSuffix in OPTIMIZED_PROFILE_SUFFIXES:
            self.dataStorage.pop(f"speedLimits{profileSuffix}", None)
            self.dataStorage.pop(f"stationSpeed{profileSuffix}", None)

        for storageKey in [key for key in self.dataStorage if key.startswith("kinematics")]:
            self.dataStorage.pop(storageKey, None)

        self.lastGeometryReportLines = []

    # Worker finished: promote the optimized geometry and refresh the views, no speeds are touched
    def onOptimizationFinished(self, payload):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.alignmentOptimizationAction.setEnabled(True)

        summary = payload.get("summary") or {}
        lxml = self.dataStorage.setdefault("LandXML", {})
        lxml["optimizationSummary"] = summary
        lxml["slewProfileStationKm"] = summary.get("slewProfileStationKm", [])
        lxml["slewProfileOffsetMm"] = summary.get("slewProfileOffsetMm", [])

        if not payload.get("hasOptimizedGeometry"):
            self.updateMapWithSpeeds()
            self.plotCant()
            self.updateOptimizationActionState()
            self.markProjectModified()
            self.setEngineStatus(lan.get("optNoGroups", "No optimizable element groups found"))
            self.showOptimizationOutcome(summary, lan)
            return

        self.harvestOptimizedResults(payload)

        self.toggleSlewPlotAction.setChecked(True)
        self.updateMapWithSpeeds()
        self.plotCant()
        self.plotSpeedLimits()
        self.plotKinematics()
        self.refreshStations()
        self.updateOptimizationActionState()
        self.refreshSlewReportWindow()
        self.markProjectModified()

        # The cant design is a separate phase, so the run ends by naming the next step rather than
        # silently recomputing speeds on geometry the user has not accepted yet
        timingText = self.buildOptimizationTimingText(summary, lan)
        nextStepText = lan.get("statusOptimizationNeedsCantRun",
                               "Alignment optimized - run the cant design to update speeds")
        self.setEngineStatus(f"{self.buildOptimizationSummaryText(summary, lan)} | {nextStepText} | {timingText}")
        self.showOptimizationOutcome(summary, lan)

    # Worker reports one finished curve group at a time, keeping the status bar alive on long corridors
    def onOptimizationProgress(self, completedGroups, totalGroups):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        template = lan.get("statusOptimizationProgress", "Optimizing alignment... {done}/{total} curve groups")
        self.setEngineStatus(template.format(done=completedGroups, total=totalGroups))

    # Micro benchmark line naming where the run actually spent its time
    def buildOptimizationTimingText(self, summary, lan):
        timing = summary.get("timingMs") or {}
        template = lan.get("optTimingSummary",
                           "Alignment optimization completed in {total} ms "
                           "(Curve solving: {solve} ms | Sampling: {sample} ms | Speed evaluation: {speed} ms)")
        return template.format(
            total=f"{timing.get('totalMs', 0.0):.2f}",
            solve=f"{timing.get('curveSolvingMs', 0.0):.2f}",
            sample=f"{timing.get('samplingMs', 0.0):.2f}",
            speed=f"{timing.get('speedEvaluationMs', 0.0):.2f}")

    def onOptimizationFailed(self, message):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.alignmentOptimizationAction.setEnabled(True)
        self.setEngineStatus(lan.get("optFailed", "Alignment optimization failed"))
        QMessageBox.critical(self, lan.get("error", "Error"), f"{message}")

    # Promote the worker's geometry onto the active keys, the baseline survives in its own copies
    def harvestOptimizedResults(self, payload):
        lxml = self.dataStorage.setdefault("LandXML", {})
        for activeKey, payloadKey in (("stationHorizontal", "stationHorizontalNew"),
                                      ("geometryType", "geometryTypeNew"),
                                      ("curvature", "curvatureNew"),
                                      ("curvatureSign", "curvatureSignNew"),
                                      ("radius", "radiusNew"),
                                      ("alignmentCoordinates", "alignmentCoordinatesNew"),
                                      ("denseAlignment", "denseAlignmentNew")):
            if payload.get(payloadKey) is not None:
                lxml[activeKey] = payload[payloadKey]

        for chainageKey in optimization_runner.CHAINAGE_MAP_KEYS:
            if payload.get(chainageKey) is not None:
                lxml[chainageKey] = payload[chainageKey]

        # Element coordinates follow the geometry, otherwise a LandXML export would carry the
        # imported points under the optimized stationing and lengths
        geometry_engine.promoteOptimizedElements(lxml, payload.get("elementArraysNew"))

        # Measured cant, the gradient profile and the imported TTP signs were all recorded
        # against the imported chainage, so they follow the alignment onto its new stationing
        geometry_engine.projectChainageArrays(lxml)
        ttpStations = self.dataStorage.get("stationSpeedLimits")
        if ttpStations is not None and len(ttpStations) > 0:
            self.dataStorage["stationSpeedLimits"] = np.array(
                [geometry_engine.projectChainageKm(lxml, float(station)) for station in ttpStations],
                dtype=float)

        # Cant was designed for the old geometry, so it cannot describe the new one
        self.clearCalculatedResults()

    # Speeds only exist once phase 3 has run, so the slew report gains its impact columns then
    def refreshOptimizationImpact(self):
        summary = self.dataStorage.get("LandXML", {}).get("optimizationSummary")
        if not summary:
            return
        self.annotateGroupSpeedImpact(summary)
        summary["travelTimeDeltaS"] = self.computeTravelTimeDelta()
        self.refreshSlewReportWindow()

    # Two native D+I passes are expensive, so an unchanged summary is annotated only once
    def optimizationImpactSignature(self, summary):
        settingsData = self.dataStorage.get("settingsData", {})
        # The two impact passes run the cant design, so every input that design reads belongs in
        # the signature. Without the norm tables and the speed inputs an edited limit left the
        # cached speed deltas on screen describing a design that no longer existed.
        designInputs = json.dumps({key: settingsData.get(key)
                                   for key in ("I", "dI", "nLin", "nILin", "vInit", "maxD",
                                               "designApproach", "disableGeometryMaxD",
                                               "balanceInflectionCants")},
                                  sort_keys=True, default=str)
        return (id(summary), summary.get("optimizedGroupCount"),
                self.dataStorage.get("defaultProfile"), designInputs,
                len(self.dataStorage.get("LandXML", {}).get("stationHorizontal", [])))

    # Per curve group speed impact, evaluated on the fly against the imported alignment
    def annotateGroupSpeedImpact(self, summary):
        signature = self.optimizationImpactSignature(summary)
        if signature == self.optimizationImpactSignatureCache:
            return

        baselineLandXml = self.baselineLandXmlForImpact()
        optimization_runner.evaluateGroupSpeeds(self.dataStorage, baselineLandXml, summary)
        self.optimizationImpactSignatureCache = signature

    # Imported geometry the baseline pass runs on, from the live cache or the published comparison
    def baselineLandXmlForImpact(self):
        cachedLandXml = (self.baselineAlignmentCache or {}).get("LandXML")
        if cachedLandXml:
            return cachedLandXml

        # A reloaded project has no cache, so the pass is rebuilt from the persisted baseline arrays
        lxml = self.dataStorage.get("LandXML", {})
        if lxml.get("stationHorizontalBaseline") is None:
            return None
        rebuilt = dict(lxml)
        for comparisonKey in BASELINE_COMPARISON_KEYS:
            baselineValues = lxml.get(comparisonKey + BASELINE_KEY_SUFFIX)
            if baselineValues is not None:
                rebuilt[comparisonKey] = baselineValues
        return rebuilt

    # Active minus baseline total run time of the first vehicle, in seconds
    def computeTravelTimeDelta(self):
        cache = self.baselineAlignmentCache or {}
        # A delta is only meaningful between two runs of the same train over the same timetable
        if cache.get("runSignature") != self.baselineRunSignature():
            return None

        baselineView = {"settingsData": self.dataStorage.get("settingsData", {})}
        for resultKey in optimization_runner.KINEMATICS_RESULT_KEYS:
            baselineValues = (self.baselineAlignmentCache or {}).get(f"{resultKey}_0")
            if baselineValues is not None:
                baselineView[f"{resultKey}_0"] = baselineValues

        baselineTime, _, _ = batch_metrics.computeTravelTimeSections(baselineView, 0)
        activeTime, _, _ = batch_metrics.computeTravelTimeSections(self.dataStorage, 0)
        if baselineTime is None or activeTime is None:
            return None
        return float(activeTime - baselineTime)

    # Status bar caption naming what the optimizer actually changed
    def buildOptimizationSummaryText(self, summary, lan):
        template = lan.get("optSummaryApplied",
                           "Optimization applied: {count} elements modified | "
                           "Max slew: {maxSlew} mm at km {station} | Average slew: {meanSlew} mm")
        return template.format(
            count=summary.get("optimizedGroupCount", 0),
            maxSlew=f"{(summary.get('maxSlewM') or 0.0) * 1000.0:.1f}",
            station=f"{summary.get('maxSlewStationKm') or 0.0:.3f}",
            meanSlew=f"{(summary.get('meanSlewCurvedM') or 0.0) * 1000.0:.1f}")

    # A dialog either confirming the run or naming the constraints that blocked every group
    def showOptimizationOutcome(self, summary, lan):
        if summary.get("optimizedGroupCount", 0) > 0:
            QMessageBox.information(self, lan.get("alignmentOptimization", "Alignment Optimization"),
                                    self.buildOptimizationSummaryText(summary, lan))
            return

        reasonCounts = {}
        for group in summary.get("groups", []):
            reasonCounts[group.get("status", "")] = reasonCounts.get(group.get("status", ""), 0) + 1

        messageLines = [lan.get("optSummaryNoChange", "No element was modified.")]
        for reasonCode, count in sorted(reasonCounts.items(), key=lambda item: -item[1]):
            messageLines.append(f"  {count}x  {lan.get(reasonCode, reasonCode)}")
        QMessageBox.warning(self, lan.get("alignmentOptimization", "Alignment Optimization"),
                            "\n".join(messageLines))

    # Restores the cached baseline and drops every optimizer output, wired to the Clear action
    def revertToBaselineAlignment(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)

        self.restoreBaselineAlignmentData()
        self.clearOptimizationResults(refresh=False)
        self.graphsWidget.clearSlewPlot()
        self.toggleSlewPlotAction.setChecked(False)
        if self.slewReportWindow is not None:
            self.slewReportWindow.close()
            self.slewReportWindow = None

        self.updateMapWithSpeeds()
        self.plotCant()
        self.plotSpeedLimits()
        self.plotKinematics()
        self.refreshStations()
        self.updateOptimizationActionState()
        self.markProjectModified()
        self.setEngineStatus(lan.get("statusOptimizationCleared",
                                     "Alignment optimization cleared - baseline restored"))

    # Drops every optimizer output, reverting the map/plots to the baseline-only view
    def clearOptimizationResults(self, refresh=True):
        lxml = self.dataStorage.setdefault("LandXML", {})
        self.optimizationImpactSignatureCache = None
        for key in OPTIMIZATION_STATE_KEYS:
            lxml.pop(key, None)

        for baseKey in BASELINE_COMPARISON_KEYS:
            lxml.pop(baseKey + BASELINE_KEY_SUFFIX, None)

        if refresh:
            self.updateMapWithSpeeds()
            self.plotCant()
            self.updateOptimizationActionState()
            self.markProjectModified()

    # Rebuild the variant list from the most recent batch, disabling it while there is nothing to show
    def refreshBatchVariantSelector(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        successfulResults = self.batchResults.successfulResults() if self.batchResults else []

        self.batchVariantCombo.blockSignals(True)
        self.batchVariantCombo.clear()
        if not successfulResults:
            self.batchVariantCombo.addItem(lan.get("batchNoVariantLoaded", "No batch variant loaded"), None)
        for result in successfulResults:
            self.batchVariantCombo.addItem(result["spec"].get("label", result["variantId"]),
                                           result["variantId"])
        self.batchVariantCombo.blockSignals(False)

        self.batchVariantCombo.setEnabled(bool(successfulResults))
        self.loadBatchVariantAction.setEnabled(bool(successfulResults))

    def loadSelectedBatchVariant(self):
        variantId = self.batchVariantCombo.currentData()
        if variantId:
            self.loadBatchVariantIntoViewport(variantId)

    # Copy one batch variant into the live data storage so every standard view can inspect it
    def loadBatchVariantIntoViewport(self, variantId):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        result = self.batchResults.resultById(variantId)
        if result is None or result.get("status") != "ok":
            return

        # The live project is the baseline the user returns to, reusing the optimizer's own cache
        self.captureBaselineAlignment()

        variantStorage = copy.deepcopy(result["dataStorage"])
        variantLxml = variantStorage.get("LandXML", {})

        # Batch variants are stored lean, so the map polylines are derived here rather than per run
        if "alignmentCoordinates" not in variantLxml:
            try:
                readfile.ReadFile().alignmentCoordinates(variantLxml, self.epsgInput, "EPSG:4326")
            except (KeyError, IndexError, ValueError):
                variantLxml["alignmentCoordinates"] = []
                variantLxml["denseAlignment"] = []

        self.dataStorage["LandXML"] = variantLxml
        for storageKey, values in variantStorage.items():
            if storageKey not in ("LandXML", "settingsData"):
                self.dataStorage[storageKey] = values

        self.loadedBatchVariantId = variantId
        self.updateMapWithSpeeds()
        self.plotCant()
        self.plotSpeedLimits()
        self.plotKinematics()
        self.refreshStations()
        self.updateOptimizationActionState()
        self.geometryCalculationFinished.emit()
        self.showMapView()

        label = result["spec"].get("label", variantId)
        template = lan.get("statusBatchVariantLoaded", "Batch variant loaded: {label}")
        self.setEngineStatus(template.format(label=label))

    # Optimization dependent commands stay disabled until a summary actually exists
    def updateOptimizationActionState(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        hasOptimization = bool(self.dataStorage.get("LandXML", {}).get("optimizationSummary"))
        self.clearOptimizationAction.setEnabled(hasOptimization)
        self.slewReportAction.setEnabled(hasOptimization)
        self.toggleSlewPlotAction.setEnabled(hasOptimization)
        if not hasOptimization:
            self.toggleSlewPlotAction.setChecked(False)

        # Measured cant belongs to the imported geometry, so as-built has no meaning on a moved axis
        self.calculateGeometryIAction.setEnabled(not hasOptimization)
        self.calculateGeometryIAction.setToolTip(
            lan.get("asBuiltUnavailableOnOptimized",
                    "As-built mode is unavailable on modified alignment geometry because installed "
                    "cant is physically invalidated.")
            if hasOptimization else lan.get("calculate_geometry_I", "Calculate I and respective speeds"))

    # Opens the non-modal lateral slew analysis table, reusing the window if it already exists
    def openSlewReport(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        if self.slewReportWindow is None:
            self.slewReportWindow = slew_report.SlewReportWindow(self.dataStorage, lan, self)
        else:
            self.slewReportWindow.updateData(self.dataStorage)
        self.slewReportWindow.show()
        self.slewReportWindow.raise_()

    def refreshSlewReportWindow(self):
        if self.slewReportWindow is not None:
            self.slewReportWindow.updateData(self.dataStorage)

    def onSlewPlotToggled(self, isChecked):
        self.graphsWidget.setSlewPlotVisible(isChecked)
        if isChecked:
            self.dockGraphs.show()
            self.dockGraphs.raise_()

    # Push the shared direction down onto every vehicle, which is where the engine still reads it
    def applyRunDirectionToVehicles(self):
        settingsData = self.dataStorage.setdefault("settingsData", {})
        simulation_runner.applyRunDirection(settingsData,
                                            self.reverseDirectionAction.isChecked())

    # The ribbon toggle owns the travel direction, so a cached run is no longer valid for it
    def onRunDirectionToggled(self, isChecked):
        self.applyRunDirectionToVehicles()
        self.markProjectModified()
        # Re-running keeps the plots, the statistics and the cache describing the same journey
        if self.simulationResultsByProfile and not self.simulationController.isRunning():
            self.calculateTrainSpeed()

    # Mirror the stored direction into the ribbon toggle without echoing a project modification back
    def applyStoredRunDirection(self):
        isReversed = simulation_runner.isRunReversed(self.dataStorage)
        self.reverseDirectionAction.blockSignals(True)
        self.reverseDirectionAction.setChecked(isReversed)
        self.reverseDirectionAction.blockSignals(False)
        self.applyRunDirectionToVehicles()

    # Evaluate every drivable speed profile tier in one click, on a worker thread
    def calculateTrainSpeed(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        if self.simulationController.isRunning():
            return

        vehicles = profile_state.vehicleSettingsList(self.dataStorage)
        profileKeys = simulation_runner.evaluableProfileKeys(self.dataStorage, vehicles)
        if not profileKeys:
            headline = lan.get("statusSimulationNoProfile",
                               "No speed profile is available to simulate")
            self.setEngineStatus(headline)
            # A status bar line alone hid the reason, which is usually a certification ceiling
            reasonTexts = self.buildProfileBlockedTexts()
            blockedLines = [f"{profile_state.profileShortName(profileKey)}: {reasonTexts[profileKey]}"
                            for profileKey in profile_state.PROFILE_KEYS
                            if reasonTexts.get(profileKey)]
            QMessageBox.warning(self, lan.get("error", "Error"),
                                "\n".join([headline] + blockedLines))
            return

        self.setBatchActionsEnabled(False)
        self.statusSimulationProgress.setMaximum(len(profileKeys))
        self.statusSimulationProgress.setValue(0)
        self.statusSimulationProgress.show()
        # Stops are projected here on the GUI thread, only the worker's own copy ever carries them
        self.simulationController.startSimulation(self.dataStorage, profileKeys,
                                                  self.projectedTrainStops())

    # One tier finished, the status bar advances without ever blocking the event loop
    def onSimulationProgress(self, completedCount, totalCount):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.statusSimulationProgress.setMaximum(max(totalCount, 1))
        self.statusSimulationProgress.setValue(completedCount)
        template = lan.get("statusSimulationProfiles", "Simulating profile {index} of {count}")
        self.setEngineStatus(template.format(index=min(completedCount + 1, totalCount),
                                             count=totalCount))

    # Harvest the worker's cache, project the active tier onto the flat keys and refresh everything
    def onSimulationFinished(self, payload):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.setBatchActionsEnabled(True)
        self.statusSimulationProgress.hide()

        self.simulationResultsByProfile = payload.get("resultsByProfile", {})
        # Travel times must be read on exactly the stationing the engine ran against
        self.dataStorage["simulatedTrainStops"] = payload.get("projectedTrainStops", [])
        self.profileState.refreshAvailability(self.dataStorage)
        self.applyActiveProfileResults()
        self.rebuildVehicleReportMenus()
        self.vehicleCalculationFinished.emit()
        self.reportSimulationWarnings()

        # Step 7 of the workflow guide covers the running simulation
        self.workflowWidget.markCompleted(6)
        evaluatedKeys = payload.get("evaluatedProfileKeys", [])
        if not evaluatedKeys:
            self.setEngineStatus(lan.get("statusSimulationNoResults",
                                         "Simulation produced no results"))
        else:
            doneText = lan.get("statusSimulationDone", "Simulation finished")
            self.setEngineStatus(f"{doneText} ({', '.join(evaluatedKeys)})")
        self.markProjectModified()

    def onSimulationFailed(self, message):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        self.setBatchActionsEnabled(True)
        self.statusSimulationProgress.hide()
        self.setEngineStatus(lan.get("simulationFailed", "Simulation failed"))
        QMessageBox.critical(self, lan.get("error", "Error"), str(message))

    # Every vehicle the active tier could not fully simulate, paired with its warning key
    def collectSimulationWarnings(self):
        warnings = []
        for vehicleIndex in range(vehicle_catalog.MAX_VEHICLES):
            warningKey = self.dataStorage.get(f"kinematicsWarning_{vehicleIndex}")
            if warningKey:
                warnings.append((vehicleIndex, warningKey))
        return warnings

    # Collapse every vehicle warning of the active tier into a single message box
    def reportSimulationWarnings(self):
        warnings = self.collectSimulationWarnings()
        if not warnings:
            return

        lan = self.translationManager.getLanguage(self.currentLanguage)
        warningTexts = {
            "train_too_long": lan.get("train_too_long", "Train is longer than the section"),
            "noTrackData": lan.get("simulationNoTrackData",
                                   "No alignment or speed profile data to simulate against"),
            vehicle_engine.WARNING_ZERO_SPEED_SECTION: lan.get(
                "zeroSpeedSection",
                "The selected design profile permits no speed on part of the line, so no run "
                "could be simulated. Check the cant design for elements limited to 0 km/h."),
            simulation_runner.WARNING_NOT_CERTIFIED: lan.get(
                "profileNotCertified", "Vehicle is not certified for the active speed profile"),
        }
        warningLines = []
        for vehicleIndex, warningKey in warnings:
            caption = f'{lan.get("vehicle", "Vehicle")} {vehicleIndex + 1}'
            warningLines.append(f"{caption}: {warningTexts.get(warningKey, warningKey)}")
        QMessageBox.warning(self, lan.get("error", "Error"), "\n".join(warningLines))

    # Copy the active tier's cached arrays onto the flat kinematics keys every consumer already reads
    def applyActiveProfileResults(self):
        # With nothing cached there is nothing to project, so a loaded project keeps its own arrays
        if not self.simulationResultsByProfile:
            return

        profileResults = self.simulationResultsByProfile.get(
            self.profileState.activeProfileKey) or {}

        for vehicleIndex in range(vehicle_catalog.MAX_VEHICLES):
            vehicleResults = profileResults.get(str(vehicleIndex)) or {}
            for resultKey in simulation_runner.PROFILE_RESULT_KEYS:
                # A missing entry writes an empty array, so the previous tier can never linger
                values = vehicleResults.get(resultKey)
                self.dataStorage[f"{resultKey}_{vehicleIndex}"] = [] if values is None else values
            warningKey = vehicleResults.get("kinematicsWarning")
            if warningKey:
                self.dataStorage[f"kinematicsWarning_{vehicleIndex}"] = warningKey
            else:
                self.dataStorage.pop(f"kinematicsWarning_{vehicleIndex}", None)

        self.dataStorage["num_vehicles"] = len(profile_state.vehicleSettingsList(self.dataStorage))
        self.plotKinematics()

    # Rebuild a single tier cache entry from the flat arrays a loaded project restored
    def seedProfileCacheFromStorage(self):
        self.profileState.refreshAvailability(self.dataStorage)
        activeProfileKey = self.dataStorage.get("activeProfileKey",
                                                self.profileState.activeProfileKey)

        resultsByVehicle = {}
        hasAnyResult = False
        for vehicleIndex in range(vehicle_catalog.MAX_VEHICLES):
            vehicleResults = {}
            for resultKey in simulation_runner.PROFILE_RESULT_KEYS:
                values = self.dataStorage.get(f"{resultKey}_{vehicleIndex}")
                vehicleResults[resultKey] = values
                hasAnyResult = hasAnyResult or (values is not None and len(values) > 0)
            vehicleResults["kinematicsWarning"] = self.dataStorage.get(
                f"kinematicsWarning_{vehicleIndex}")
            resultsByVehicle[str(vehicleIndex)] = vehicleResults

        # Only the saved tier can be restored, the others need a fresh Simulate to be populated
        self.simulationResultsByProfile = {activeProfileKey: resultsByVehicle} if hasAnyResult else {}
        self.profileState.setActiveProfile(activeProfileKey)

    # Every synchronised profile selector, so one loop keeps the ribbon and both docks in step
    def profileSelectors(self):
        return (self.ribbonProfileSelector, self.graphsProfileSelector,
                self.trackStatsWidget.profileSelector)

    # Connect every profile selector to the shared state and seed the initial availability
    def connectProfileSignals(self):
        for selector in self.profileSelectors():
            selector.profileSelectionRequested.connect(self.onProfileSelectionRequested)
        self.profileState.refreshAvailability(self.dataStorage)

    # A selector asked for a tier, the shared state decides whether it is actually allowed
    def onProfileSelectionRequested(self, profileKey):
        self.profileState.setActiveProfile(profileKey)

    # Shared active tier changed, mirror it into every selector and reproject the cached results
    def onActiveProfileChanged(self, profileKey):
        self.dataStorage["activeProfileKey"] = profileKey
        for selector in self.profileSelectors():
            selector.applyActiveProfile(profileKey)
        self.graphsWidget.setActiveProfileKey(profileKey)
        self.applyActiveProfileResults()
        self.refreshTrackStatsDock()
        self.dockGraphs.requestUpdate()

    # Permitted tier set changed, repaint every selector's enabled rows and blocked tooltips
    def onAvailableProfilesChanged(self):
        reasonTexts = self.buildProfileBlockedTexts()
        for selector in self.profileSelectors():
            selector.applyAvailability(self.profileState.permittedProfileKeys, reasonTexts)

    # Explain, per tier, why it cannot currently be selected
    def buildProfileBlockedTexts(self):
        lan = self.translationManager.getLanguage(self.currentLanguage)
        vehicles = profile_state.vehicleSettingsList(self.dataStorage)
        reasonTexts = {}

        for profileKey in profile_state.PROFILE_KEYS:
            if not profile_state.hasProfileData(self.dataStorage, profileKey):
                reasonTexts[profileKey] = lan.get(
                    "profileBlockedNoData", "This profile has no calculated speed limits yet")
                continue
            blockingNumbers = profile_state.blockingVehicleNumbers(profileKey, vehicles)
            if not blockingNumbers:
                continue
            template = lan.get(
                "profileBlockedCantDeficiency",
                "Profile {profile} unavailable: active vehicle certified up to I = {limit} mm")
            blockedVehicle = vehicles[blockingNumbers[0] - 1]
            reasonTexts[profileKey] = template.format(
                profile=profile_state.profileShortName(profileKey),
                limit=f"{profile_state.vehicleMaxCantDeficiency(blockedVehicle):g}")
        return reasonTexts

    def updateMapWithSpeeds(self):
        lxml = self.dataStorage.get("LandXML", {})
        if not lxml:
            # Nothing left to draw, so the previous alignment must not survive on the map
            self.mapWidget.resetMap()
            return

        # Geometry profiles (V100 / V130 / V150 / VK)
        for profile in ["100", "130", "150", "K"]:
            lxml[f"speedLimits{profile}"] = self.dataStorage.get(f"speedLimits{profile}")
            lxml[f"stationSpeed{profile}"] = self.dataStorage.get(f"stationSpeed{profile}")

        # TTP raw speed limits – nearest-station extrapolation is handled in map_viewer
        lxml["speedLimitsTTP"]  = np.asarray(self.dataStorage.get("speedLimits",      []))
        lxml["stationSpeedTTP"] = np.asarray(self.dataStorage.get("stationSpeedLimits", []))

        self.mapWidget.drawAlignment(lxml.get("alignmentCoordinates", []), lxml)
        