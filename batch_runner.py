# Isolated execution of one or many track variants, on a QThread worker for the batch dialog
import copy
import time
import numpy as np
from PySide6.QtCore import QObject, QThread, QMutex, QMutexLocker, Signal

import batch_config
import batch_metrics
import geometry_engine
import simulation_runner
import vehicle_engine

# LandXML keys the two engines actually read, everything else (coordinates, key points) is dead weight per variant
LEAN_LANDXML_KEYS = ("stationHorizontal", "geometryType", "curvature", "curvatureSign",
                       "cant", "stationCant", "stationVertical", "slope") + geometry_engine.OPTIMIZER_INPUT_KEYS


# Strip a dataStorage down to only what GeometryCalculator and VehicleCalculator read, deepcopied once
def buildLeanBaseStorage(dataStorage, mergedLandXml=None):
    sourceLandXml = mergedLandXml if mergedLandXml is not None else dataStorage.get("LandXML", {})
    leanLandXml = {key: sourceLandXml[key] for key in LEAN_LANDXML_KEYS if key in sourceLandXml}
    leanStorage = {
        "settingsData": copy.deepcopy(dataStorage.get("settingsData", {})),
        "LandXML": leanLandXml,
    }
    for passthroughKey in ("stationSpeedLimits", "speedLimits"):
        if dataStorage.get(passthroughKey) is not None:
            leanStorage[passthroughKey] = dataStorage[passthroughKey]
    return leanStorage


# The "I150" style design profile name maps to the "150" speed/cant-deficiency key suffix used by the engines
def resolveProfileSuffix(designProfile):
    designProfile = designProfile or "I150"
    return designProfile[1:] if designProfile.startswith("I") else designProfile


# Small, plot-ready, copied-out arrays for one variant, safe to keep around after dataStorage is discarded
def extractSeriesForPlot(dataStorage, profileSuffix):
    lxml = dataStorage.get("LandXML", {})
    stationSource = lxml.get("stationCantPossible", lxml.get("stationHorizontal", []))
    stationKm = np.array(stationSource, dtype=float, copy=True)
    speedProfile = np.array(dataStorage.get(f"speedLimits{profileSuffix}", []), dtype=float, copy=True)
    cantDeficiency = np.array(lxml.get(f"cDef{profileSuffix}", []), dtype=float, copy=True)

    actualStationM = dataStorage.get("kinematicsStationM_0")
    actualSpeedMs = dataStorage.get("kinematicsSpeedM_0")
    actualSpeedKm = np.array(actualStationM, dtype=float, copy=True) / 1000.0 if batch_metrics.hasData(actualStationM) else np.array([])
    actualSpeedKmh = np.array(actualSpeedMs, dtype=float, copy=True) * 3.6 if batch_metrics.hasData(actualSpeedMs) else np.array([])

    return {
        "stationKm": stationKm,
        "speedProfile": speedProfile,
        "cantDeficiency": cantDeficiency,
        "actualSpeedKm": actualSpeedKm,
        "actualSpeedKmh": actualSpeedKmh,
    }


# Run one variant on its own isolated deepcopy of the lean base storage, never touching the caller's dict
def runSingleVariant(leanBaseStorage, spec):
    startTime = time.perf_counter()
    variantStorage = copy.deepcopy(leanBaseStorage)

    try:
        settingsData = variantStorage["settingsData"]
        settingsData["trainStops"] = spec.get("trainStops", settingsData.get("trainStops", []))
        settingsData["designApproach"] = spec.get("designApproach", settingsData.get("designApproach", "standard"))

        if spec.get("sweepParamKey"):
            batch_config.applySweepValue(settingsData, spec["sweepParamKey"], spec["sweepValue"],
                                         approachDict=settingsData["designApproach"])

        variantStorage["defaultProfile"] = spec.get("designProfile", "I150")

        scenario = spec.get("optimizationScenario")
        if scenario:
            variantLxml = variantStorage["LandXML"]
            _, optimizedElements = geometry_engine.AlignmentOptimizer(variantLxml, scenario).run()
            for baseKey in ("stationHorizontal", "geometryType", "curvature", "curvatureSign"):
                newKey = baseKey + "New"
                if newKey in variantLxml:
                    variantLxml[baseKey] = variantLxml[newKey]
            # The element dict used to be discarded, so a loaded variant drew its map from the
            # imported coordinates while every station around them had already moved
            geometry_engine.promoteOptimizedElements(variantLxml, optimizedElements)
            geometry_engine.projectChainageArrays(variantLxml)

        geometryCalc = geometry_engine.GeometryCalculator(variantStorage)
        if spec.get("calculationMode") == "asBuilt":
            geometryCalc.runCalculationLoopI()
        else:
            geometryCalc.runCalculationLoop()

        if spec.get("runVehicles", True):
            vehicleCalc = vehicle_engine.VehicleCalculator(variantStorage)
            vehicleCalc.calculateKinematics()
            vehicleCalc.speedLimitsToTime()
            simulation_runner.dropUncertifiedVehicles(
                variantStorage, resolveProfileSuffix(spec.get("designProfile")))

        profileSuffix = resolveProfileSuffix(spec.get("designProfile"))
        metrics = batch_metrics.computeVariantMetrics(variantStorage, vehicleIndex=0, designProfileSuffix=profileSuffix)
        seriesForPlot = extractSeriesForPlot(variantStorage, profileSuffix)

        return {
            "variantId": spec["variantId"], "variantIndex": spec["variantIndex"], "spec": spec,
            "status": "ok", "errorText": "", "durationS": time.perf_counter() - startTime,
            "dataStorage": variantStorage, "metrics": metrics, "seriesForPlot": seriesForPlot,
        }
    except Exception as exc:
        return {
            "variantId": spec["variantId"], "variantIndex": spec["variantIndex"], "spec": spec,
            "status": "failed", "errorText": str(exc), "durationS": time.perf_counter() - startTime,
            "dataStorage": None, "metrics": {}, "seriesForPlot": {},
        }


class BatchWorker(QObject):
    variantStarted = Signal(int, str)
    variantFinished = Signal(int, dict)
    batchFinished = Signal(list)
    batchFailed = Signal(str)

    def __init__(self, leanBaseStorage, variantSpecs):
        super().__init__()
        self.leanBaseStorage = leanBaseStorage
        self.variantSpecs = variantSpecs
        self.cancelMutex = QMutex()
        self.isCancelRequested = False

    # Called from the GUI thread, immediately visible to the worker thread via the mutex
    def requestCancel(self):
        with QMutexLocker(self.cancelMutex):
            self.isCancelRequested = True

    def checkCancelRequested(self):
        with QMutexLocker(self.cancelMutex):
            return self.isCancelRequested

    # Slot invoked once the owning QThread starts, runs every variant sequentially
    def runBatch(self):
        try:
            results = []
            for spec in self.variantSpecs:
                if self.checkCancelRequested():
                    results.append({
                        "variantId": spec["variantId"], "variantIndex": spec["variantIndex"], "spec": spec,
                        "status": "cancelled", "errorText": "", "durationS": 0.0,
                        "dataStorage": None, "metrics": {}, "seriesForPlot": {},
                    })
                    continue
                self.variantStarted.emit(spec["variantIndex"], spec.get("label", spec["variantId"]))
                result = runSingleVariant(self.leanBaseStorage, spec)
                self.variantFinished.emit(spec["variantIndex"], result)
                results.append(result)
            self.batchFinished.emit(results)
        except Exception as exc:
            self.batchFailed.emit(str(exc))


class BatchController(QObject):
    # Owned by MainWindow and connected to exactly once at startup, so callers never race a fast worker
    # that could otherwise emit before a per-call connection to the worker itself gets established
    variantStarted = Signal(int, str)
    variantFinished = Signal(int, dict)
    batchFinished = Signal(list)
    batchFailed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        # Flips to False the instant the batch is logically over, independent of QThread teardown timing
        self.isBatchActive = False

    def isRunning(self):
        return self.isBatchActive

    # Build the lean base once on the GUI thread, then hand the worker its own isolated copy of everything
    # Never call this synchronously from inside a batchFinished/batchFailed handler, defer with QTimer.singleShot(0, ...) instead
    def startBatch(self, baseDataStorage, variantSpecs, mergedLandXml=None):
        if self.isBatchActive:
            raise RuntimeError("a batch is already running")

        self.isBatchActive = True
        leanBaseStorage = buildLeanBaseStorage(baseDataStorage, mergedLandXml)
        self.thread = QThread()
        self.worker = BatchWorker(leanBaseStorage, variantSpecs)
        self.worker.moveToThread(self.thread)

        # Forwarding is wired before the thread starts, so the controller's own signals never miss an emit
        self.worker.variantStarted.connect(self.variantStarted)
        self.worker.variantFinished.connect(self.variantFinished)
        self.worker.batchFinished.connect(self.onWorkerBatchFinished)
        self.worker.batchFailed.connect(self.onWorkerBatchFailed)

        self.thread.started.connect(self.worker.runBatch)
        self.worker.batchFinished.connect(self.thread.quit)
        self.worker.batchFailed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.onThreadFinished)

        self.thread.start()

    # Clear the running flag before forwarding, so a handler that starts a new batch right away sees isRunning() == False
    def onWorkerBatchFinished(self, results):
        self.isBatchActive = False
        self.batchFinished.emit(results)

    def onWorkerBatchFailed(self, message):
        self.isBatchActive = False
        self.batchFailed.emit(message)

    # Drop our references once the thread has fully wound down, so a new batch can start afterward
    def onThreadFinished(self):
        # finished() fires just before the OS thread actually exits, so join to close that gap
        finishedThread = self.sender()
        if finishedThread is not None:
            finishedThread.wait()
        # A newer startBatch() call may already have replaced self.thread, so only clear our own generation
        if self.thread is finishedThread:
            self.thread = None
            self.worker = None

    # Ask the running worker to stop after the variant currently in progress
    def cancelBatch(self):
        if self.worker is not None:
            self.worker.requestCancel()

    # Block briefly for the thread to actually wind down, used only when the application is closing
    def waitForFinish(self, timeoutMs=5000):
        if self.thread is not None:
            self.thread.wait(timeoutMs)
