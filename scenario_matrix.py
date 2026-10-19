# Scenario matrix: raw theoretical travel times over pattern, tier, vehicle and direction, on a worker thread
import copy
import csv
import hashlib
import io
import json
from datetime import datetime

import numpy as np
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal

import batch_metrics
import geometry_engine
import profile_state
import simulation_runner
import stops_model
import vehicle_engine

# dataStorage key the finished matrix is stored under and persisted through the calculation cache
MATRIX_STORAGE_KEY = "scenarioMatrix"

# Outcome of one matrix cell
STATUS_OK = "ok"
STATUS_NOT_CERTIFIED = "notCertified"
STATUS_ZERO_SPEED_SECTION = "zeroSpeedSection"
STATUS_NO_TRACK_DATA = "noTrackData"
STATUS_TOO_FEW_STOPS = "tooFewStops"
STATUS_TRAIN_TOO_LONG = "trainTooLong"

# Vehicle warning the engine records when there is no alignment or speed profile to run against
ENGINE_WARNING_NO_TRACK_DATA = "noTrackData"

# Vehicle warning the engine records when the train is longer than the simulated section
ENGINE_WARNING_TRAIN_TOO_LONG = "train_too_long"

# Per vehicle storage keys that make up a vehicle's physics in the input signature
VEHICLE_SIGNATURE_KEYS = ("trainParam", "trainRes", "trainTrac", "trainMaxSpeed", "trainBrakeDecel",
                          "maxCantDeficiencyMm", "trainInitialSpeed", "trainFinalSpeed",
                          "speedLimitPlot")


# Engine passes a request needs, every pattern and tier runs once per direction
def countEnginePasses(patternCount, profileCount):
    return int(patternCount) * int(profileCount) * len(simulation_runner.DIRECTION_KEYS)


# Vehicle settings the engine would use, a project without a vehicle list runs on its legacy keys
def matrixVehicles(settingsData):
    vehicles = (settingsData or {}).get("vehicles") or []
    if vehicles:
        return list(vehicles)
    settingsData = settingsData or {}
    return [{
        "trainInitialSpeed": settingsData.get("trainInitialSpeed", 0.0),
        "trainFinalSpeed": settingsData.get("trainFinalSpeed", 0.0),
        "trainMaxSpeed": settingsData.get("trainMaxSpeed", settingsData.get("vInit", [120])[0]),
        "trainBrakeDecel": settingsData.get("trainBrakeDecel", 0.45),
        "trainRes": settingsData.get("trainRes", []),
        "trainTrac": settingsData.get("trainTrac", []),
        "trainParam": settingsData.get("trainParam", []),
        "maxCantDeficiencyMm": settingsData.get("maxCantDeficiencyMm", 150.0),
        "speedLimitPlot": settingsData.get("speedLimitPlot", profile_state.storageKeysFor("150")),
        "runReversed": False,
    }]


# Display name of one vehicle from its parameter row, empty when it has none
def vehicleDisplayName(vehicleSettings):
    try:
        return str(vehicleSettings["trainParam"][0][0]).strip()
    except (IndexError, KeyError, TypeError):
        return ""


# Stops of one pattern projected onto the active alignment, as (km, dwell, name, stopId) tuples
def projectPatternStops(lxml, records, patternKey):
    projectedStops = []
    for record in stops_model.patternRecords(records, patternKey):
        try:
            activeKm = geometry_engine.projectChainageKm(lxml, float(record["stationingKm"]))
        except (IndexError, ValueError, TypeError):
            continue
        projectedStops.append((activeKm, float(record["dwellTimeS"]), str(record["stopName"]),
                               str(record["stopId"])))
    return projectedStops


# Bytes of any stored value in a stable form, numeric arrays and lists alike by their raw buffer
def signatureBytes(value):
    if isinstance(value, (np.ndarray, list, tuple)):
        try:
            array = np.ascontiguousarray(np.asarray(value, dtype=float))
            return str(array.shape).encode("utf-8") + array.tobytes()
        except (TypeError, ValueError):
            pass
    return json.dumps(value, sort_keys=True, default=lambda item: np.asarray(item).tolist()).encode("utf-8")


# Stop fields that change a simulated journey: id, stationing, dwell and the members of each pattern
def stopSignatureRows(records, patternKeys):
    rows = {}
    for patternKey in patternKeys:
        rows[patternKey] = [[record["stopId"], record["stationingKm"], record["dwellTimeS"]]
                            for record in stops_model.patternRecords(records, patternKey)]
    return rows


# SHA-1 over what the given tiers, vehicles and patterns depend on, None means all, metadata never counts
def computeInputSignature(dataStorage, profileKeys=None, vehicleIndices=None, patternKeys=None):
    digest = hashlib.sha1()
    settingsData = (dataStorage or {}).get("settingsData", {}) or {}
    records = stops_model.normalizeStopRecords(settingsData.get("stopRecords"))
    vehicles = matrixVehicles(settingsData)

    patternKeys = list(patternKeys) if patternKeys is not None else list(stops_model.PATTERN_KEYS)
    vehicleIndices = list(vehicleIndices) if vehicleIndices is not None else list(range(len(vehicles)))
    profileKeys = list(profileKeys) if profileKeys is not None else list(profile_state.PROFILE_KEYS)

    digest.update(signatureBytes(stopSignatureRows(records, patternKeys)))
    for vehicleIndex in vehicleIndices:
        if 0 <= vehicleIndex < len(vehicles):
            digest.update(signatureBytes({key: vehicles[vehicleIndex].get(key)
                                          for key in VEHICLE_SIGNATURE_KEYS}))
    digest.update(signatureBytes(settingsData.get("manualSpeedLimits", [])))
    for profileKey in profileKeys:
        for storageKey in profile_state.storageKeysFor(profileKey):
            values = (dataStorage or {}).get(storageKey)
            digest.update(storageKey.encode("utf-8"))
            digest.update(signatureBytes(values if values is not None else []))
    # Every alignment array the engine reads, not only the stationing
    lxml = (dataStorage or {}).get("LandXML", {}) or {}
    for landXmlKey in simulation_runner.SIMULATION_LANDXML_KEYS:
        values = lxml.get(landXmlKey)
        digest.update(landXmlKey.encode("utf-8"))
        digest.update(signatureBytes(values if values is not None else []))
    return digest.hexdigest()


# True when a stored matrix no longer matches the current inputs of its own tiers, vehicles and patterns
def isMatrixStale(dataStorage):
    matrix = (dataStorage or {}).get(MATRIX_STORAGE_KEY)
    if not matrix:
        return False
    currentSignature = computeInputSignature(dataStorage, matrix.get("profileKeys"),
                                             matrix.get("vehicleIndices"), matrix.get("patternKeys"))
    return matrix.get("inputSignature") != currentSignature


# True when the stored alignment came out of an optimizer run
def isOptimizedAlignment(dataStorage):
    lxml = (dataStorage or {}).get("LandXML", {}) or {}
    return any(lxml.get(markerKey) is not None for markerKey in ("optimizationSummary", "chainageMapActiveKm"))


# Everything the worker needs, built on the GUI thread so the worker owns isolated copies
def buildMatrixJob(dataStorage, profileKeys, vehicleIndices, patternKeys, calculationMode="design"):
    settingsData = (dataStorage or {}).get("settingsData", {}) or {}
    records = stops_model.normalizeStopRecords(settingsData.get("stopRecords"))
    lxml = (dataStorage or {}).get("LandXML", {}) or {}

    allVehicles = matrixVehicles(settingsData)
    selectedIndices = [index for index in vehicleIndices if 0 <= index < len(allVehicles)]
    baseStorage = simulation_runner.buildSimulationStorage(dataStorage, [])
    baseStorage["settingsData"]["vehicles"] = [copy.deepcopy(allVehicles[index])
                                               for index in selectedIndices]

    return {
        "baseStorage": baseStorage,
        "patternStops": {patternKey: projectPatternStops(lxml, records, patternKey)
                         for patternKey in patternKeys},
        "profileKeys": list(profileKeys),
        "vehicleIndices": selectedIndices,
        "patternKeys": list(patternKeys),
        "inputSignature": computeInputSignature(dataStorage, profileKeys, selectedIndices, patternKeys),
        "designContext": {
            "designApproach": settingsData.get("designApproach"),
            "maxDmm": copy.deepcopy(settingsData.get("maxD")),
            "calculationMode": calculationMode,
            "isOptimizedAlignment": isOptimizedAlignment(dataStorage),
        },
    }


# One summary cell with every field present, filled in by the caller as far as the run allows
def emptyCell(profileKey, vehicleIndex, vehicleName, patternKey, directionKey, status):
    return {
        "profileKey": profileKey,
        "vehicleIndex": vehicleIndex,
        "vehicleName": vehicleName,
        "patternKey": patternKey,
        "direction": directionKey,
        "status": status,
        "rawTotalRunS": None,
        "rawOriginDestS": None,
        "rawRunningS": None,
        "dwellTotalS": None,
        "originStopId": None,
        "destinationStopId": None,
        "sections": [],
    }


# Summary of one vehicle's finished run, trajectories are dropped to keep the matrix small
def summarizeCell(profileStorage, localIndex, vehicleSettings, profileKey, patternKey, directionKey,
                  stops, vehicleIndex):
    cell = emptyCell(profileKey, vehicleIndex, vehicleDisplayName(vehicleSettings), patternKey,
                     directionKey, STATUS_OK)

    if not profile_state.isProfilePermitted(profileKey, vehicleSettings):
        cell["status"] = STATUS_NOT_CERTIFIED
        return cell

    warningKey = profileStorage.get(f"kinematicsWarning_{localIndex}")
    if warningKey == vehicle_engine.WARNING_ZERO_SPEED_SECTION:
        cell["status"] = STATUS_ZERO_SPEED_SECTION
        return cell
    if warningKey == ENGINE_WARNING_TRAIN_TOO_LONG:
        cell["status"] = STATUS_TRAIN_TOO_LONG
        return cell

    stationsM = profileStorage.get(f"kinematicsStationM_{localIndex}")
    timesS = profileStorage.get(f"kinematicsTimeS_{localIndex}")
    if warningKey == ENGINE_WARNING_NO_TRACK_DATA or not (batch_metrics.hasData(stationsM)
                                                          and batch_metrics.hasData(timesS)):
        cell["status"] = STATUS_NO_TRACK_DATA
        return cell

    cell["rawTotalRunS"] = float(timesS[-1])

    # A stop the run never reaches cannot anchor a section, so it leaves the pattern for this cell
    orderedStops = batch_metrics.orderStopsForRun(stops, stationsM)
    reachableStops = [stop for stop in orderedStops
                      if batch_metrics.lookupTimeAtStation(stationsM, timesS, stop[0]) is not None]
    if len(reachableStops) < 2:
        cell["status"] = STATUS_TOO_FEW_STOPS
        return cell

    details = batch_metrics.computeTravelTimeSectionDetails(stationsM, timesS, reachableStops)
    sections = []
    for leg in details["legs"]:
        sections.append({
            "fromStopId": leg["fromStop"][3],
            "toStopId": leg["toStop"][3],
            "fromStationingKm": leg["fromStationKm"],
            "toStationingKm": leg["toStationKm"],
            "lengthKm": leg["lengthKm"],
            "rawRunS": leg["runTimeS"],
            "dwellAtToS": leg["dwellAtToS"],
        })

    cell["originStopId"] = reachableStops[0][3]
    cell["destinationStopId"] = reachableStops[-1][3]
    cell["rawOriginDestS"] = details["originDestTimeS"]
    cell["rawRunningS"] = sum(section["rawRunS"] for section in sections
                              if section["rawRunS"] is not None)
    cell["dwellTotalS"] = sum(section["dwellAtToS"] for section in sections[:-1])
    cell["sections"] = sections
    return cell


# Every pattern, tier and direction evaluated in turn, summaries only
def runScenarioMatrix(job, progressCallback=None, cancelCallback=None):
    baseStorage = job["baseStorage"]
    vehicles = baseStorage["settingsData"]["vehicles"]
    vehicleIndices = job["vehicleIndices"]
    totalPasses = countEnginePasses(len(job["patternKeys"]), len(job["profileKeys"]))
    completedPasses = 0
    cells = []
    wasCancelled = False

    for patternKey in job["patternKeys"]:
        stops = job["patternStops"].get(patternKey, [])
        patternBase = dict(baseStorage)
        patternBase["settingsData"] = dict(baseStorage["settingsData"])
        patternBase["settingsData"]["trainStops"] = [list(stop) for stop in stops]

        for profileKey in job["profileKeys"]:
            for directionKey in simulation_runner.DIRECTION_KEYS:
                if cancelCallback is not None and cancelCallback():
                    wasCancelled = True
                    break
                if progressCallback is not None:
                    progressCallback(completedPasses, totalPasses)
                profileStorage = simulation_runner.runProfileEvaluation(
                    patternBase, profileKey, simulation_runner.isDirectionReversed(directionKey))
                for localIndex, vehicleSettings in enumerate(vehicles):
                    cells.append(summarizeCell(profileStorage, localIndex, vehicleSettings,
                                               profileKey, patternKey, directionKey, stops,
                                               vehicleIndices[localIndex]))
                completedPasses += 1
            if wasCancelled:
                break
        if wasCancelled:
            break

    if progressCallback is not None:
        progressCallback(completedPasses, totalPasses)

    return {
        "evaluatedAt": datetime.now().isoformat(timespec="seconds"),
        "inputSignature": job["inputSignature"],
        "profileKeys": list(job["profileKeys"]),
        "patternKeys": list(job["patternKeys"]),
        "vehicleIndices": list(vehicleIndices),
        "designContext": job["designContext"],
        "cells": cells,
        "wasCancelled": wasCancelled,
    }


class ScenarioMatrixWorker(QObject):
    matrixFinished = Signal(dict)
    matrixFailed = Signal(str)
    progressChanged = Signal(int, int)

    def __init__(self, job):
        super().__init__()
        self.job = job
        self.cancelMutex = QMutex()
        self.isCancelRequested = False

    # Asked from the GUI thread, the run stops between engine passes because a pass cannot be interrupted
    def requestCancel(self):
        with QMutexLocker(self.cancelMutex):
            self.isCancelRequested = True

    def checkCancelRequested(self):
        with QMutexLocker(self.cancelMutex):
            return self.isCancelRequested

    # Slot invoked once the owning QThread starts
    def runMatrix(self):
        try:
            payload = runScenarioMatrix(self.job, self.progressChanged.emit,
                                        self.checkCancelRequested)
            self.matrixFinished.emit(payload)
        except Exception as exc:
            self.matrixFailed.emit(str(exc))


class ScenarioMatrixController(QObject):
    # Owned by MainWindow and connected to exactly once at startup, so callers never race a fast worker
    matrixFinished = Signal(dict)
    matrixFailed = Signal(str)
    progressChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        # Flips to False the instant the run is logically over, independent of QThread teardown timing
        self.isMatrixActive = False

    def isRunning(self):
        return self.isMatrixActive

    # Build the isolated job on the GUI thread, then hand the worker sole ownership of it
    def startMatrix(self, dataStorage, profileKeys, vehicleIndices, patternKeys,
                    calculationMode="design"):
        if self.isMatrixActive:
            raise RuntimeError("a scenario matrix is already running")

        # The job is built first, so a failure here can never leave the controller marked as running
        job = buildMatrixJob(dataStorage, profileKeys, vehicleIndices, patternKeys, calculationMode)
        self.isMatrixActive = True
        self.thread = QThread()
        self.worker = ScenarioMatrixWorker(job)
        self.worker.moveToThread(self.thread)

        self.worker.matrixFinished.connect(self.onWorkerFinished)
        self.worker.matrixFailed.connect(self.onWorkerFailed)
        self.worker.progressChanged.connect(self.progressChanged)

        self.thread.started.connect(self.worker.runMatrix)
        self.worker.matrixFinished.connect(self.thread.quit)
        self.worker.matrixFailed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.onThreadFinished)

        self.thread.start()

    # Cooperative cancel, the current engine pass still finishes
    def cancelMatrix(self):
        if self.worker is not None:
            self.worker.requestCancel()

    # Clear the running flag before forwarding, so a handler may start a new run right away
    def onWorkerFinished(self, payload):
        self.isMatrixActive = False
        self.matrixFinished.emit(payload)

    def onWorkerFailed(self, message):
        self.isMatrixActive = False
        self.matrixFailed.emit(message)

    # Drop our references once the thread has fully wound down, so a new run can start afterward
    def onThreadFinished(self):
        finishedThread = self.sender()
        if finishedThread is not None:
            finishedThread.wait()
        if self.thread is finishedThread:
            self.thread = None
            self.worker = None

    # Block briefly for the thread to actually wind down, used only when the application is closing
    def waitForFinish(self, timeoutMs=5000):
        if self.thread is not None:
            self.thread.wait(timeoutMs)


# Columns of the flat scenario CSV, one row per leg and a single row for a cell without legs
CSV_COLUMNS = ("scenarioId", "profileKey", "vehicleIndex", "vehicleName", "patternKey", "direction",
               "directionLabel", "status", "rawTotalRunS", "rawOriginDestS", "rawRunningS",
               "dwellTotalS", "scheduledOriginDestS", "fromStopId", "toStopId", "fromStationingKm",
               "toStationingKm", "lengthKm", "rawRunS", "scheduledRunS", "dwellAtToS")


# Flat CSV text of exported scenario entries, as built by karto_export.buildTravelTimes
def scenariosToCsv(scenarios):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    cellColumns = CSV_COLUMNS[:CSV_COLUMNS.index("fromStopId")]
    sectionColumns = CSV_COLUMNS[CSV_COLUMNS.index("fromStopId"):]
    for scenario in scenarios or []:
        cellValues = ["" if scenario.get(column) is None else scenario.get(column)
                      for column in cellColumns]
        sections = scenario.get("sections") or [{}]
        for section in sections:
            writer.writerow(cellValues + ["" if section.get(column) is None else section.get(column)
                                          for column in sectionColumns])
    return buffer.getvalue()
