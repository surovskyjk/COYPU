# Isolated execution of the alignment optimization pipeline on a QThread worker for the main window
import copy
import time

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

import geometry_engine
import readfile
import simulation_runner
import vehicle_engine

# Display only arrays rebuilt from the optimized elements, never worth deepcopying into the worker
DISPLAY_LANDXML_KEYS = ("alignmentCoordinates", "alignmentCoordsOriginal", "denseAlignment")

# Baseline geometry keys the optimizer mirrors into a New suffixed twin
PROMOTED_GEOMETRY_KEYS = ("stationHorizontal", "geometryType", "curvature", "curvatureSign")

# Baseline to active chainage mapping the optimizer emits, used to reproject stops and markers
CHAINAGE_MAP_KEYS = ("chainageMapBaselineKm", "chainageMapActiveKm")

# Design speed profiles the geometry engine derives on every run
SPEED_PROFILE_SUFFIXES = ("100", "130", "150", "K")

# Per vehicle kinematics arrays harvested back into the main data storage, owned by the engine
KINEMATICS_RESULT_KEYS = vehicle_engine.KINEMATICS_RESULT_KEYS


# Deepcopy only what the optimizer and both engines actually read, built on the GUI thread
def buildOptimizationStorage(dataStorage):
    sourceLandXml = dataStorage.get("LandXML", {})
    workerLandXml = {key: copy.deepcopy(value) for key, value in sourceLandXml.items()
                     if key not in DISPLAY_LANDXML_KEYS}
    workerStorage = {
        "settingsData": copy.deepcopy(dataStorage.get("settingsData", {})),
        "defaultProfile": dataStorage.get("defaultProfile", "I150"),
        "LandXML": workerLandXml,
    }
    for passthroughKey in ("stationSpeedLimits", "speedLimits"):
        if dataStorage.get(passthroughKey) is not None:
            workerStorage[passthroughKey] = copy.deepcopy(dataStorage[passthroughKey])
    return workerStorage


# One native design pass on an isolated copy, returning the per element permissible speed array
def evaluateElementSpeeds(dataStorage, landXml):
    if not landXml:
        return None

    evaluationStorage = buildOptimizationStorage(dataStorage)
    evaluationStorage["LandXML"] = {key: copy.deepcopy(value) for key, value in landXml.items()
                                    if key not in DISPLAY_LANDXML_KEYS}
    try:
        # Design mode only, measured cant describes the imported axis and not a displaced one
        geometry_engine.GeometryCalculator(evaluationStorage).runCalculationLoop()
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        # A failure here only costs the two impact columns, but letting it escape would abort
        # the whole refresh from inside a Qt slot
        return None

    profileSuffix = resolveProfileSuffix(dataStorage.get("defaultProfile", "I150"))
    speeds = evaluationStorage.get(f"speedLimits{profileSuffix}")
    return np.asarray(speeds, dtype=float) if speeds is not None else None


# Storage key suffix of a design profile, kept here so the report does not reach into batch_runner
def resolveProfileSuffix(designProfile):
    designProfile = designProfile or "I150"
    return designProfile[1:] if designProfile.startswith("I") else designProfile


# Slowest permissible speed over one curve group, addressed by element index rather than by chainage
def groupSpeedFrom(speeds, group):
    startIndex = group.get("startElemIndex")
    endIndex = group.get("endElemIndex")
    if speeds is None or startIndex is None or endIndex is None:
        return None

    # Every element owns two entries of the speed array, its start and its end station
    low, high = 2 * int(startIndex), 2 * int(endIndex)
    if low < 0 or high > speeds.size or high <= low:
        return None

    window = speeds[low:high]
    window = window[np.isfinite(window) & (window > 0)]
    return float(np.min(window)) if window.size else None


# Per group speed impact from two native D+I passes, one on each alignment, mapped by element index
def evaluateGroupSpeeds(dataStorage, baselineLandXml, summary):
    if not summary:
        return

    baselineSpeeds = evaluateElementSpeeds(dataStorage, baselineLandXml)
    optimizedSpeeds = evaluateElementSpeeds(dataStorage, dataStorage.get("LandXML", {}))

    for group in summary.get("groups", []):
        group["speedOldKmh"] = groupSpeedFrom(baselineSpeeds, group)
        group["speedNewKmh"] = groupSpeedFrom(optimizedSpeeds, group)
        if group["speedOldKmh"] is None or group["speedNewKmh"] is None:
            group["speedDeltaKmh"] = None
        else:
            group["speedDeltaKmh"] = group["speedNewKmh"] - group["speedOldKmh"]


# Copy the optimizer's New suffixed geometry over the baseline keys of the isolated copy only
def promoteOptimizedGeometry(workerLandXml):
    for baseKey in PROMOTED_GEOMETRY_KEYS:
        newKey = baseKey + "New"
        if newKey in workerLandXml:
            workerLandXml[baseKey] = workerLandXml[newKey]
    # Measured cant and the gradient profile were surveyed against the imported chainage, so
    # they move with it. Without this the as built loop interpolates baseline stations onto a
    # re-chained axis and the vertical profile is read at the wrong place.
    geometry_engine.projectChainageArrays(workerLandXml)


# Collect every engine output the main window mirrors into its own New suffixed keys
def collectPipelineResults(workerStorage):
    workerLandXml = workerStorage.get("LandXML", {})
    results = {
        "stationCantPossible": workerLandXml.get("stationCantPossible", []),
        "cantPossible": workerLandXml.get("cantPossible", []),
        "speedProfiles": {},
        "kinematics": {},
        "vehicleCount": int(workerStorage.get("num_vehicles", 0)),
    }
    for profileSuffix in SPEED_PROFILE_SUFFIXES:
        results[f"cDef{profileSuffix}"] = workerLandXml.get(f"cDef{profileSuffix}", [])
        results["speedProfiles"][profileSuffix] = {
            "stationSpeed": workerStorage.get(f"stationSpeed{profileSuffix}", []),
            "speedLimits": workerStorage.get(f"speedLimits{profileSuffix}", []),
        }
    for vehicleIndex in range(results["vehicleCount"]):
        vehicleResults = {}
        for resultKey in KINEMATICS_RESULT_KEYS:
            vehicleResults[resultKey] = workerStorage.get(f"{resultKey}_{vehicleIndex}")
        results["kinematics"][vehicleIndex] = vehicleResults
    return results


# Optimizer, geometry engine and kinematics chained on one isolated storage, safe to call off the GUI thread
def runOptimizedPipeline(workerStorage, config, calculationMode, epsgInput, progressCallback=None,
                         isGeometryOnly=False):
    pipelineStarted = time.perf_counter()
    workerLandXml = workerStorage["LandXML"]
    optimizer = geometry_engine.AlignmentOptimizer(workerLandXml, config, progressCallback)
    summary, optimizedElements = optimizer.run()

    payload = {"summary": summary, "hasOptimizedGeometry": optimizedElements is not None}
    if optimizedElements is None:
        summary["timingMs"]["speedEvaluationMs"] = 0.0
        summary["timingMs"]["totalMs"] = (time.perf_counter() - pipelineStarted) * 1000.0
        return payload

    # Lat/lon polylines for the map overlay, harvested exactly the way the baseline import does
    readfile.ReadFile().alignmentCoordinates(optimizedElements, epsgInput, "EPSG:4326")
    payload["alignmentCoordinatesNew"] = optimizedElements.get("alignmentCoordinates", [])
    payload["denseAlignmentNew"] = optimizedElements.get("denseAlignment", [])
    payload["radiusNew"] = workerLandXml.get("radiusNew")
    # The per element coordinate arrays describe the elements themselves. Only the stations and
    # curvature used to be handed back, so the export kept writing the imported coordinates.
    payload["elementArraysNew"] = {key: optimizedElements[key]
                                   for key in geometry_engine.OPTIMIZER_INPUT_KEYS
                                   if key in optimizedElements}
    for geometryKey in PROMOTED_GEOMETRY_KEYS:
        payload[geometryKey + "New"] = workerLandXml.get(geometryKey + "New")
    for chainageKey in CHAINAGE_MAP_KEYS:
        payload[chainageKey] = workerLandXml.get(chainageKey)

    # Phase 2 of the workflow only reshapes geometry, the cant and speed design stays a separate step
    if isGeometryOnly:
        summary["timingMs"]["speedEvaluationMs"] = 0.0
        summary["timingMs"]["totalMs"] = (time.perf_counter() - pipelineStarted) * 1000.0
        return payload

    # Both engines run untouched against the optimized geometry of the isolated copy
    speedStarted = time.perf_counter()
    promoteOptimizedGeometry(workerLandXml)
    geometryCalculator = geometry_engine.GeometryCalculator(workerStorage)
    if calculationMode == "asBuilt":
        geometryCalculator.runCalculationLoopI()
    else:
        geometryCalculator.runCalculationLoop()

    vehicleCalculator = vehicle_engine.VehicleCalculator(workerStorage)
    vehicleCalculator.calculateKinematics()
    vehicleCalculator.speedLimitsToTime()
    simulation_runner.dropUncertifiedVehicles(
        workerStorage, resolveProfileSuffix(workerStorage.get("defaultProfile", "I150")))

    summary["timingMs"]["speedEvaluationMs"] = (time.perf_counter() - speedStarted) * 1000.0
    summary["timingMs"]["totalMs"] = (time.perf_counter() - pipelineStarted) * 1000.0

    payload["results"] = collectPipelineResults(workerStorage)
    return payload


class OptimizationWorker(QObject):
    optimizationFinished = Signal(dict)
    optimizationFailed = Signal(str)
    progressChanged = Signal(int, int)

    def __init__(self, workerStorage, config, calculationMode, epsgInput, isGeometryOnly=False):
        super().__init__()
        self.workerStorage = workerStorage
        self.config = config
        self.calculationMode = calculationMode
        self.epsgInput = epsgInput
        self.isGeometryOnly = isGeometryOnly

    # Slot invoked once the owning QThread starts
    def runOptimization(self):
        try:
            # No explicit yielding here, an interpreter switch interval already interleaves the threads
            payload = runOptimizedPipeline(self.workerStorage, self.config,
                                           self.calculationMode, self.epsgInput,
                                           self.progressChanged.emit, self.isGeometryOnly)
            self.optimizationFinished.emit(payload)
        except Exception as exc:
            self.optimizationFailed.emit(str(exc))


class OptimizationController(QObject):
    # Owned by MainWindow and connected to exactly once at startup, so callers never race a fast worker
    optimizationFinished = Signal(dict)
    optimizationFailed = Signal(str)
    progressChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        # Flips to False the instant the run is logically over, independent of QThread teardown timing
        self.isOptimizationActive = False

    def isRunning(self):
        return self.isOptimizationActive

    # Build the isolated copy on the GUI thread, then hand the worker sole ownership of it
    def startOptimization(self, dataStorage, config, calculationMode, epsgInput, isGeometryOnly=False):
        if self.isOptimizationActive:
            raise RuntimeError("an optimization is already running")

        self.isOptimizationActive = True
        workerStorage = buildOptimizationStorage(dataStorage)
        self.thread = QThread()
        self.worker = OptimizationWorker(workerStorage, config, calculationMode, epsgInput, isGeometryOnly)
        self.worker.moveToThread(self.thread)

        # Forwarding is wired before the thread starts, so the controller's own signals never miss an emit
        self.worker.optimizationFinished.connect(self.onWorkerFinished)
        self.worker.optimizationFailed.connect(self.onWorkerFailed)
        self.worker.progressChanged.connect(self.progressChanged)

        self.thread.started.connect(self.worker.runOptimization)
        self.worker.optimizationFinished.connect(self.thread.quit)
        self.worker.optimizationFailed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.onThreadFinished)

        self.thread.start()

    # Clear the running flag before forwarding, so a handler may start a new run right away
    def onWorkerFinished(self, payload):
        self.isOptimizationActive = False
        self.optimizationFinished.emit(payload)

    def onWorkerFailed(self, message):
        self.isOptimizationActive = False
        self.optimizationFailed.emit(message)

    # Drop our references once the thread has fully wound down, so a new run can start afterward
    def onThreadFinished(self):
        # finished() fires just before the OS thread actually exits, so join to close that gap
        finishedThread = self.sender()
        if finishedThread is not None:
            finishedThread.wait()
        # A newer startOptimization() call may already have replaced self.thread, so only clear our own generation
        if self.thread is finishedThread:
            self.thread = None
            self.worker = None

    # Block briefly for the thread to actually wind down, used only when the application is closing
    def waitForFinish(self, timeoutMs=5000):
        if self.thread is not None:
            self.thread.wait(timeoutMs)
