# Native .coypu project archive: a ZIP wrapping project.json plus the raw imported assets
import base64
import copy
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QByteArray

import app_version
import basemap_key
import default_values
import karto_export
import project_metadata
import readfile
import schedule_rules
import source_stack
import stops_model
import theme_manager
from resource_paths import getWritableRoot

# File name suffixes owned by the native project format
PROJECT_EXTENSION = ".coypu"
RECOVERY_SUFFIX = ".bak"

# Schema version stamped into every archive so future readers can migrate old files
PROJECT_FORMAT_VERSION = 2

# Oldest schema version this build still reads, older files are migrated in memory
OLDEST_SUPPORTED_FORMAT_VERSION = 1

# Settings keys schema version 2 added, an older file is topped up from the defaults
V2_SETTINGS_KEYS = ("baselineVehicleNames", "stopRecords", "activeStopPattern",
                    "spPopulationThreshold", "isSpThresholdAuto", "scheduleSettings")

# Entry names used inside the ZIP container
PROJECT_JSON_NAME = "project.json"
ASSET_DIRECTORY = "assets"

# Application identity written into both the project header and the LandXML export
APPLICATION_NAME = "COYPU"
APPLICATION_VERSION = app_version.__version__
APPLICATION_MANUFACTURER = "COYPU Team"

# Marker wrapping a numpy array so shape and dtype survive the JSON round trip
NDARRAY_MARKER = "__ndarray__"

# Top level dataStorage keys holding imported source data rather than calculated results
RAW_DATA_STORAGE_KEYS = ("settingsData", "LandXML", "stationSpeedLimits", "speedLimits")

# LandXML sub-dictionary key prefixes produced by the geometry engine, cached separately
CALCULATED_LANDXML_PREFIXES = ("stationCantPossible", "cantPossible", "cDef", "cantDef",
                               "dDdt", "dIdt", "util_D_", "util_I_", "limitReachedD_",
                               "limitReachedI_", "speedLimits", "stationSpeed",
                               "stationHorizontalBaseline", "curvatureBaseline",
                               "alignmentCoordinatesBaseline", "geometryTypeBaseline",
                               "curvatureSignBaseline", "chainageMap",
                               "optimizationSummary", "slewProfile")

# How many recently opened projects the File menu keeps
MAX_RECENT_PROJECTS = 5

# QSettings keys backing the recent project list and the crash recovery marker
RECENT_PROJECTS_SETTING = "project/recentProjects"
RECOVERY_PATH_SETTING = "project/recoveryPath"

# Recovery snapshot used while the project has never been saved to a real path
UNTITLED_RECOVERY_NAME = "untitled.coypu.bak"

# How often the background recovery snapshot is written, in milliseconds
AUTO_SAVE_INTERVAL_MS = 5 * 60 * 1000


# True when a LandXML sub-key was produced by the geometry engine instead of the parser
def isCalculatedLandXmlKey(keyName):
    return any(keyName.startswith(prefix) for prefix in CALCULATED_LANDXML_PREFIXES)


# Keys only an optimizer run writes into the active LandXML dictionary
OPTIMIZED_LANDXML_MARKERS = ("optimizationSummary", "chainageMapActiveKm")


# The map polylines and the dense chainage list are derived from the element arrays, and a saved
# copy only reflects the sampling of the version that wrote it. Projects saved before arcs carried
# their own chainage reopened with every arc sample on one station, so the copy is rebuilt.
def rebuildDisplayGeometry(landXmlData, epsgInput):
    if not isinstance(landXmlData, dict) or len(landXmlData.get("stationHorizontal", [])) == 0:
        return
    try:
        readfile.ReadFile().alignmentCoordinates(landXmlData, epsgInput, "EPSG:4326")
    except (KeyError, IndexError, ValueError, TypeError):
        # A payload too lean to rebuild keeps what it was saved with
        pass


# Turn numpy arrays, tuples and scalars into structures the JSON encoder accepts
def encodeValue(value):
    if isinstance(value, np.ndarray):
        return {NDARRAY_MARKER: True, "dtype": str(value.dtype), "values": value.tolist()}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): encodeValue(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encodeValue(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    return value


# Rebuild numpy arrays from their marker dictionaries, leaving every other value untouched
def decodeValue(value):
    if isinstance(value, dict):
        if value.get(NDARRAY_MARKER):
            return np.array(value.get("values", []), dtype=np.dtype(value.get("dtype", "float64")))
        return {key: decodeValue(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decodeValue(item) for item in value]
    return value


# Turn an imported file name into a safe ZIP entry name
def sanitizeAssetName(fileName):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", fileName or "").strip("_")
    return cleaned or "source.xml"


# Split a merged LandXML dictionary into its parsed geometry and its calculated results
def splitLandXmlData(landXmlData):
    parsedGeometry = {}
    calculatedResults = {}
    for keyName, value in (landXmlData or {}).items():
        target = calculatedResults if isCalculatedLandXmlKey(keyName) else parsedGeometry
        target[keyName] = value
    return parsedGeometry, calculatedResults


# Top up a settings dictionary with every key schema version 2 added, in place
def upgradeSettingsData(settingsData):
    if not isinstance(settingsData, dict):
        return settingsData
    for keyName in V2_SETTINGS_KEYS:
        if keyName not in settingsData:
            settingsData[keyName] = copy.deepcopy(default_values.defVal[keyName])
    settingsData["scheduleSettings"] = schedule_rules.normalizeScheduleSettings(
        settingsData.get("scheduleSettings"))
    for vehicleSettings in settingsData.get("vehicles") or []:
        if isinstance(vehicleSettings, dict):
            vehicleSettings["directionLabels"] = stops_model.normalizeDirectionLabels(
                vehicleSettings.get("directionLabels"))
    stops_model.ensureStopSettings(settingsData)
    return settingsData


# Payload of an older schema upgraded in memory to the current one, the input is left untouched
def migrateProjectPayload(payload):
    migrated = dict(payload or {})
    migrated["projectMetadata"] = project_metadata.normalizeMetadata(
        migrated.get("projectMetadata", {}))

    stopsData = dict(migrated.get("stopsData") or {})
    if "stopRecords" not in stopsData:
        legacyStops = decodeValue(stopsData.get("trainStops", []))
        stopsData["stopRecords"] = stops_model.recordsFromLegacyStops(legacyStops)
        stopsData.setdefault("activeStopPattern", stops_model.DEFAULT_ACTIVE_PATTERN)
        stopsData.setdefault("spPopulationThreshold", stops_model.DEFAULT_SP_POPULATION_THRESHOLD)
        stopsData.setdefault("isSpThresholdAuto", True)
    migrated["stopsData"] = stopsData
    migrated["formatVersion"] = PROJECT_FORMAT_VERSION
    return migrated


class RecentProjectsStore:
    def __init__(self, appSettings):
        self.appSettings = appSettings

    # Existing recent project paths, newest first, silently dropping deleted files
    def recentProjects(self):
        rawValue = self.appSettings.value(RECENT_PROJECTS_SETTING, "")
        try:
            storedPaths = json.loads(rawValue) if rawValue else []
        except (TypeError, ValueError):
            storedPaths = []
        return [path for path in storedPaths if isinstance(path, str) and Path(path).is_file()]

    # Promote one project to the top of the list and trim it to the configured length
    def rememberProject(self, projectPath):
        normalizedPath = str(Path(projectPath).resolve())
        storedPaths = [path for path in self.recentProjects()
                       if str(Path(path).resolve()) != normalizedPath]
        storedPaths.insert(0, normalizedPath)
        self.appSettings.setValue(RECENT_PROJECTS_SETTING,
                                  json.dumps(storedPaths[:MAX_RECENT_PROJECTS]))

    # Forget every remembered project, used when the list points at moved files
    def clearProjects(self):
        self.appSettings.setValue(RECENT_PROJECTS_SETTING, json.dumps([]))


class ProjectFileManager:
    # Collect every live piece of project state into one serializable payload
    def buildProjectPayload(self, mainWindow):
        return {
            "formatVersion": PROJECT_FORMAT_VERSION,
            "application": {
                "name": APPLICATION_NAME,
                "version": APPLICATION_VERSION,
                "manufacturer": APPLICATION_MANUFACTURER,
            },
            "savedAt": datetime.now().isoformat(timespec="seconds"),
            "projectMetadata": project_metadata.normalizeMetadata(mainWindow.projectMetadata),
            "alignmentsData": self.collectAlignmentsData(mainWindow),
            "stopsData": self.collectStopsData(mainWindow),
            "vehicleConfiguration": self.collectVehicleConfiguration(mainWindow),
            "calculationCache": self.collectCalculationCache(mainWindow),
            "viewportState": self.collectViewportState(mainWindow),
        }

    # Point the payload at the Karto entry, called only once the dataset was actually built
    def attachKartoPointer(self, payload):
        payload["kartoDataset"] = {
            "entryName": karto_export.KARTO_ENTRY_NAME,
            "schemaVersion": karto_export.KARTO_SCHEMA_VERSION,
        }
        return payload

    # Parsed horizontal and vertical geometry plus the provenance of every merged segment
    def collectAlignmentsData(self, mainWindow):
        parsedGeometry, _ = splitLandXmlData(mainWindow.dataStorage.get("LandXML", {}))
        return {
            "landXml": encodeValue(parsedGeometry),
            "sourceSegments": self.collectSourceSegments(mainWindow),
        }

    # One serialized descriptor per imported segment, keeping the selective purge working after a reload
    def collectSourceSegments(self, mainWindow):
        segments = []
        for entry in mainWindow.sourceStack.entries:
            segments.append({
                "sourceId": entry.sourceId,
                "kind": entry.kind,
                "fileName": entry.fileName,
                "stationStart": float(entry.stationStart),
                "stationEnd": float(entry.stationEnd),
                "assetName": self.assetNameForEntry(entry),
                "payload": encodeValue(entry.payload),
            })
        return segments

    # ZIP entry name a segment's raw import text is stored under, empty when nothing was kept
    def assetNameForEntry(self, entry):
        if not getattr(entry, "rawText", ""):
            return ""
        return f"{ASSET_DIRECTORY}/{entry.sourceId:03d}_{sanitizeAssetName(entry.fileName)}"

    # Scheduled stops, dwell times and the merged TTP speed limit arrays
    def collectStopsData(self, mainWindow):
        settingsData = mainWindow.dataStorage.get("settingsData", {})
        return {
            "trainStops": encodeValue(settingsData.get("trainStops", [])),
            "stopRecords": encodeValue(settingsData.get("stopRecords", [])),
            "activeStopPattern": settingsData.get("activeStopPattern",
                                                  stops_model.DEFAULT_ACTIVE_PATTERN),
            "spPopulationThreshold": settingsData.get("spPopulationThreshold",
                                                      stops_model.DEFAULT_SP_POPULATION_THRESHOLD),
            "isSpThresholdAuto": bool(settingsData.get("isSpThresholdAuto", True)),
            "defaultDwellTime": settingsData.get("defaultDwellTime", 30.0),
            "stationSpeedLimits": encodeValue(mainWindow.dataStorage.get("stationSpeedLimits", [])),
            "speedLimits": encodeValue(mainWindow.dataStorage.get("speedLimits", [])),
        }

    # Active vehicle profiles and every other geometry or simulation setting
    def collectVehicleConfiguration(self, mainWindow):
        settingsData = mainWindow.dataStorage.get("settingsData", {})
        vehicles = settingsData.get("vehicles", [])
        # A basemap key never travels with a project, a shared file would share the key with it
        savedSettings = {keyName: value for keyName, value in settingsData.items()
                         if keyName != basemap_key.LEGACY_SETTINGS_KEY}
        return {
            "vehicleCount": len(vehicles) or 1,
            "settingsData": encodeValue(savedSettings),
        }

    # Saved GPK speed profiles, cant deficiency arrays and kinematics so plots reopen instantly
    def collectCalculationCache(self, mainWindow):
        _, calculatedResults = splitLandXmlData(mainWindow.dataStorage.get("LandXML", {}))
        cachedStorage = {keyName: value for keyName, value in mainWindow.dataStorage.items()
                         if keyName not in RAW_DATA_STORAGE_KEYS}
        return {
            "landXmlDerived": encodeValue(calculatedResults),
            "dataStorage": encodeValue(cachedStorage),
            "geometryReportLines": list(mainWindow.lastGeometryReportLines),
        }

    # Window layout, theme, units, central view and the map camera
    def collectViewportState(self, mainWindow):
        mapCenterLat, mapCenterLon, mapZoom = mainWindow.mapWidget.getViewState()
        return {
            "layoutGeometry": self.encodeBytes(mainWindow.saveGeometry()),
            "layoutState": self.encodeBytes(mainWindow.saveState()),
            "themeMode": mainWindow.themeManager.currentMode,
            "languageCode": mainWindow.currentLanguage,
            "unitsKmh": bool(mainWindow.toggleUnitsAction.isChecked()),
            "activeViewIndex": mainWindow.centralStack.currentIndex(),
            "epsgInput": mainWindow.epsgInput,
            "mapBaseMap": mainWindow.mapWidget.currentBaseMap,
            "mapDrawMode": mainWindow.mapWidget.drawMode,
            "mapSpeedProfile": mainWindow.mapWidget.speedProfile,
            "mapRailOverlay": bool(mainWindow.mapWidget.railOverlayEnabled),
            "mapRailOpacity": float(mainWindow.mapWidget.railOverlayOpacity),
            "mapStationsVisible": bool(mainWindow.mapWidget.showStations),
            "mapElementDetails": bool(mainWindow.mapWidget.showElementDetails),
            "mapCenterLat": mapCenterLat,
            "mapCenterLon": mapCenterLon,
            "mapZoom": mapZoom,
        }

    def encodeBytes(self, byteData):
        return base64.b64encode(bytes(byteData)).decode("ascii")

    def decodeBytes(self, encodedText):
        return QByteArray(base64.b64decode(encodedText.encode("ascii")))

    # Raw text of every imported file, keyed by the ZIP entry name it is stored under
    def collectRawAssets(self, mainWindow):
        assets = {}
        for entry in mainWindow.sourceStack.entries:
            assetName = self.assetNameForEntry(entry)
            if assetName:
                assets[assetName] = entry.rawText
        return assets

    # Compact JSON text of the Karto dataset, None when building it fails so a save is never blocked
    def collectKartoDataset(self, mainWindow):
        try:
            dataset = karto_export.buildKartoDataset(
                mainWindow.dataStorage, mainWindow.projectMetadata, mainWindow.epsgInput)
            return karto_export.serializeKartoDataset(dataset)
        except Exception:
            return None

    # Write one compressed .coypu archive holding the payload, every raw asset and the Karto dataset
    def writeProjectArchive(self, filePath, payload, rawAssets, kartoDataset=None):
        targetPath = Path(filePath)
        targetPath.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(targetPath, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(PROJECT_JSON_NAME,
                             json.dumps(payload, indent=2, ensure_ascii=False))
            for assetName, assetText in (rawAssets or {}).items():
                archive.writestr(assetName, assetText or "")
            if kartoDataset:
                archive.writestr(karto_export.KARTO_ENTRY_NAME, kartoDataset)

    # Read a .coypu archive back into its payload dictionary and raw asset texts, karto/ is never read
    def readProjectArchive(self, filePath):
        with zipfile.ZipFile(Path(filePath), "r") as archive:
            payload = json.loads(archive.read(PROJECT_JSON_NAME).decode("utf-8"))
            rawAssets = {}
            for entryName in archive.namelist():
                if entryName.startswith(f"{ASSET_DIRECTORY}/"):
                    rawAssets[entryName] = archive.read(entryName).decode("utf-8", errors="replace")
        return payload, rawAssets

    # Reject archives written by a newer schema before any state is touched
    def validatePayload(self, payload):
        formatVersion = (payload or {}).get("formatVersion", 0)
        isInteger = isinstance(formatVersion, int) and not isinstance(formatVersion, bool)
        if not isInteger or formatVersion < OLDEST_SUPPORTED_FORMAT_VERSION:
            raise ValueError("not a COYPU project file")
        if formatVersion > PROJECT_FORMAT_VERSION:
            raise ValueError(f"project format version {formatVersion} is newer than supported "
                             f"version {PROJECT_FORMAT_VERSION}")

    # Restore every section of a previously saved project into the live main window
    def applyProjectPayload(self, mainWindow, payload, rawAssets):
        self.validatePayload(payload)
        payload = migrateProjectPayload(payload)

        mainWindow.projectMetadata = project_metadata.normalizeMetadata(
            payload.get("projectMetadata", {}))

        self.applyVehicleConfiguration(mainWindow, payload.get("vehicleConfiguration", {}))
        self.applyAlignmentsData(mainWindow, payload.get("alignmentsData", {}), rawAssets)
        self.applyStopsData(mainWindow, payload.get("stopsData", {}))
        self.applyCalculationCache(mainWindow, payload.get("calculationCache", {}))
        epsgInput = payload.get("viewportState", {}).get("epsgInput", mainWindow.epsgInput)
        self.rebuildAlignmentDisplay(mainWindow, epsgInput)
        self.applyViewportState(mainWindow, payload.get("viewportState", {}))

    # Every imported segment is a plain parse, so its map data always rebuilds exactly. The active
    # alignment is rebuilt only while it is still the import: an optimized axis saved before its
    # element coordinates were promoted carries imported coordinates under optimized stations.
    def rebuildAlignmentDisplay(self, mainWindow, epsgInput):
        for entry in mainWindow.sourceStack.entriesForKind(source_stack.LANDXML_KIND):
            rebuildDisplayGeometry(entry.payload, epsgInput)

        landXmlData = mainWindow.dataStorage.get("LandXML", {})
        if not any(landXmlData.get(key) is not None for key in OPTIMIZED_LANDXML_MARKERS):
            rebuildDisplayGeometry(landXmlData, epsgInput)

    # Vehicles, geometry limits and every other persisted setting replace the defaults wholesale
    def applyVehicleConfiguration(self, mainWindow, vehicleConfiguration):
        settingsData = decodeValue(vehicleConfiguration.get("settingsData", {}))
        # Older versions saved the author's basemap key here, it must never be used by someone else
        if isinstance(settingsData, dict):
            settingsData.pop(basemap_key.LEGACY_SETTINGS_KEY, None)
        if settingsData:
            mainWindow.dataStorage["settingsData"] = upgradeSettingsData(settingsData)

    # Parsed geometry and the source stack behind it, assets reattached to their segments
    def applyAlignmentsData(self, mainWindow, alignmentsData, rawAssets):
        mainWindow.dataStorage["LandXML"] = decodeValue(alignmentsData.get("landXml", {}))

        mainWindow.sourceStack.clearAll()
        highestSourceId = 0
        for segment in alignmentsData.get("sourceSegments", []):
            payload = decodeValue(segment.get("payload"))
            if segment.get("kind") == source_stack.TTP_KIND and isinstance(payload, list):
                payload = tuple(payload)
            entry = mainWindow.sourceStack.addEntry(
                segment.get("kind", source_stack.LANDXML_KIND),
                segment.get("fileName", ""), payload,
                float(segment.get("stationStart", 0.0)), float(segment.get("stationEnd", 0.0)))
            entry.sourceId = int(segment.get("sourceId", entry.sourceId))
            entry.rawText = (rawAssets or {}).get(segment.get("assetName", ""), "")
            highestSourceId = max(highestSourceId, entry.sourceId)
        mainWindow.sourceStack.nextId = highestSourceId + 1

    # Stops, dwell times and the merged TTP speed limits
    def applyStopsData(self, mainWindow, stopsData):
        settingsData = mainWindow.dataStorage.setdefault("settingsData", {})
        settingsData["trainStops"] = decodeValue(stopsData.get("trainStops", []))
        settingsData["defaultDwellTime"] = stopsData.get("defaultDwellTime", 30.0)
        if "stopRecords" in stopsData:
            settingsData["stopRecords"] = decodeValue(stopsData["stopRecords"])
            settingsData["activeStopPattern"] = stopsData.get("activeStopPattern",
                                                              stops_model.DEFAULT_ACTIVE_PATTERN)
            settingsData["spPopulationThreshold"] = stopsData.get(
                "spPopulationThreshold", stops_model.DEFAULT_SP_POPULATION_THRESHOLD)
            settingsData["isSpThresholdAuto"] = bool(stopsData.get("isSpThresholdAuto", True))
        stops_model.ensureStopSettings(settingsData)
        mainWindow.dataStorage["stationSpeedLimits"] = decodeValue(
            stopsData.get("stationSpeedLimits", []))
        mainWindow.dataStorage["speedLimits"] = decodeValue(stopsData.get("speedLimits", []))

    # Cached GPK profiles, cant deficiency arrays and kinematics merged back over the raw data
    def applyCalculationCache(self, mainWindow, calculationCache):
        cachedStorage = decodeValue(calculationCache.get("dataStorage", {}))
        for keyName, value in cachedStorage.items():
            if keyName not in RAW_DATA_STORAGE_KEYS:
                mainWindow.dataStorage[keyName] = value

        landXmlDerived = decodeValue(calculationCache.get("landXmlDerived", {}))
        mainWindow.dataStorage.setdefault("LandXML", {}).update(landXmlDerived)

        mainWindow.lastGeometryReportLines = list(calculationCache.get("geometryReportLines", []))

    # Window layout, theme, units, central view and map camera captured at save time
    def applyViewportState(self, mainWindow, viewportState):
        layoutGeometry = viewportState.get("layoutGeometry")
        if layoutGeometry:
            mainWindow.restoreGeometry(self.decodeBytes(layoutGeometry))

        layoutState = viewportState.get("layoutState")
        if layoutState:
            mainWindow.restoreState(self.decodeBytes(layoutState))

        themeMode = viewportState.get("themeMode", theme_manager.MODE_AUTO)
        if themeMode not in (theme_manager.MODE_AUTO, theme_manager.MODE_LIGHT,
                             theme_manager.MODE_DARK):
            themeMode = theme_manager.MODE_AUTO
        for action in mainWindow.themeGroup.actions():
            action.setChecked(action.data() == themeMode)
        mainWindow.themeManager.applyTheme(themeMode)

        languageCode = viewportState.get("languageCode", mainWindow.currentLanguage)
        if languageCode in mainWindow.translationManager.availableLanguageCodes():
            mainWindow.currentLanguage = languageCode

        mainWindow.toggleUnitsAction.setChecked(bool(viewportState.get("unitsKmh", False)))
        mainWindow.epsgInput = viewportState.get("epsgInput", mainWindow.epsgInput)

        mainWindow.mapWidget.railOverlayEnabled = bool(viewportState.get("mapRailOverlay", False))
        mainWindow.mapWidget.railOverlayOpacity = float(viewportState.get("mapRailOpacity", 0.7))
        mainWindow.mapWidget.showStations = bool(viewportState.get("mapStationsVisible", True))
        mainWindow.mapWidget.showElementDetails = bool(
            viewportState.get("mapElementDetails", True))
        mainWindow.mapWidget.currentBaseMap = viewportState.get("mapBaseMap", "positron")
        mainWindow.mapWidget.drawMode = viewportState.get("mapDrawMode", "single")
        mainWindow.mapWidget.speedProfile = viewportState.get("mapSpeedProfile", "150")
        mainWindow.mapWidget.setViewState(viewportState.get("mapCenterLat"),
                                          viewportState.get("mapCenterLon"),
                                          viewportState.get("mapZoom"))
        mainWindow.mapWidget.syncControlsPanel()

        activeViewIndex = viewportState.get("activeViewIndex", 0)
        if isinstance(activeViewIndex, int):
            mainWindow.restoreCentralView(activeViewIndex)


# Path of the recovery snapshot belonging to a project, or the shared untitled one
def recoveryPathFor(projectPath):
    if projectPath:
        return Path(str(projectPath) + RECOVERY_SUFFIX)
    return getWritableRoot() / "config" / UNTITLED_RECOVERY_NAME
