# Isolated multi profile kinematics evaluation on a QThread worker for the main window
import copy

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Signal

import profile_state
import vehicle_engine

# LandXML arrays the vehicle engine reads, the geometry engine never runs on this pipeline
SIMULATION_LANDXML_KEYS = ("stationHorizontal", "curvature", "stationVertical", "slope")

# Speed limit arrays speedLimitsToTime writes alongside the kinematics results
SPEED_LIMIT_RESULT_KEYS = ("stationSpeedLimitM", "speedLimitsM", "speedLimitsT")

# Every per vehicle array one finished profile run contributes to the cache
PROFILE_RESULT_KEYS = vehicle_engine.KINEMATICS_RESULT_KEYS + SPEED_LIMIT_RESULT_KEYS

# Warning recorded against a vehicle the active tier exceeds its certified cant deficiency
WARNING_NOT_CERTIFIED = "profileNotCertified"

# Project level travel direction, it describes the run rather than any one vehicle
RUN_REVERSED_KEY = "runReversed"


# True when the project drives against the stationing, so the run starts at the highest chainage
def isRunReversed(dataStorage):
    settingsData = (dataStorage or {}).get("settingsData", {}) or {}
    return bool(settingsData.get(RUN_REVERSED_KEY, False))


# Stamp the one shared direction onto every vehicle, which is where the engine still reads it
def applyRunDirection(settingsData, isReversed):
    settingsData[RUN_REVERSED_KEY] = bool(isReversed)
    for vehicleSettings in settingsData.get("vehicles", []) or []:
        vehicleSettings[RUN_REVERSED_KEY] = bool(isReversed)


# Deepcopy only what the vehicle engine reads, built on the GUI thread with the projected stops baked in
def buildSimulationStorage(dataStorage, projectedTrainStops):
    sourceLandXml = (dataStorage or {}).get("LandXML", {}) or {}
    workerStorage = {
        "settingsData": copy.deepcopy((dataStorage or {}).get("settingsData", {})),
        "LandXML": {key: copy.deepcopy(sourceLandXml[key])
                    for key in SIMULATION_LANDXML_KEYS if key in sourceLandXml},
    }

    # The engine matches stops by absolute chainage, so the worker owns them already projected
    workerStorage["settingsData"]["trainStops"] = copy.deepcopy(list(projectedTrainStops or []))

    # The shared direction wins over whatever a vehicle carried from an older project file
    applyRunDirection(workerStorage["settingsData"], isRunReversed(workerStorage))

    for profileKey in profile_state.PROFILE_KEYS:
        for storageKey in profile_state.storageKeysFor(profileKey):
            if (dataStorage or {}).get(storageKey) is not None:
                workerStorage[storageKey] = copy.deepcopy(dataStorage[storageKey])
    return workerStorage


# Drop the trajectory of every vehicle the given tier is not certified for. The tier ceiling is
# a vehicle certification limit rather than a preference, so an uncertified train must contribute
# no run at all instead of a plausible looking one. collectProfileResults already does this for
# the multi profile pipeline; the batch and optimized pipelines call the engines directly.
def dropUncertifiedVehicles(storage, profileKey):
    for vehicleIndex, vehicleSettings in enumerate(profile_state.vehicleSettingsList(storage)):
        if profile_state.isProfilePermitted(profileKey, vehicleSettings):
            continue
        for resultKey in PROFILE_RESULT_KEYS:
            storage.pop(f"{resultKey}_{vehicleIndex}", None)
        storage[f"kinematicsWarning_{vehicleIndex}"] = WARNING_NOT_CERTIFIED


# Tiers worth evaluating, an absent array would silently fall back to the vehicle's own top speed
def evaluableProfileKeys(dataStorage, vehicles):
    return [profileKey for profileKey in profile_state.PROFILE_KEYS
            if profile_state.hasProfileData(dataStorage, profileKey)
            and any(profile_state.isProfilePermitted(profileKey, vehicleSettings)
                    for vehicleSettings in vehicles)]


# One tier's run over every vehicle, on a fresh copy so the caller's own speedLimitPlot is never touched
def runProfileEvaluation(baseStorage, profileKey):
    profileStorage = copy.deepcopy(baseStorage)
    for vehicleSettings in profileStorage.get("settingsData", {}).get("vehicles", []):
        # A vehicle pinned to manual or unlimited limits keeps its own profile across every tier
        if profile_state.isVehicleOverridden(vehicleSettings):
            continue
        vehicleSettings["speedLimitPlot"] = profile_state.storageKeysFor(profileKey)

    calculator = vehicle_engine.VehicleCalculator(profileStorage)
    calculator.calculateKinematics()
    calculator.speedLimitsToTime()
    return profileStorage


# Plot ready arrays of one finished run, keyed by vehicle index as a string so JSON round trips survive
def collectProfileResults(profileStorage, profileKey, vehicles):
    resultsByVehicle = {}
    for vehicleIndex, vehicleSettings in enumerate(vehicles):
        vehicleResults = {}
        isCertified = profile_state.isProfilePermitted(profileKey, vehicleSettings)
        for resultKey in PROFILE_RESULT_KEYS:
            # An uncertified vehicle must contribute no trajectory at all, never a plausible looking one
            vehicleResults[resultKey] = (profileStorage.get(f"{resultKey}_{vehicleIndex}")
                                         if isCertified else None)
        vehicleResults["kinematicsWarning"] = (
            profileStorage.get(f"kinematicsWarning_{vehicleIndex}") if isCertified
            else WARNING_NOT_CERTIFIED)
        resultsByVehicle[str(vehicleIndex)] = vehicleResults
    return resultsByVehicle


# Every requested tier evaluated in turn, returning the cache the main window projects from
def runMultiProfilePipeline(baseStorage, profileKeys, progressCallback=None, cancelCallback=None):
    vehicles = profile_state.vehicleSettingsList(baseStorage)
    resultsByProfile = {}
    evaluatedKeys = []

    for profileIndex, profileKey in enumerate(profileKeys):
        if cancelCallback is not None and cancelCallback():
            break
        if progressCallback is not None:
            progressCallback(profileIndex, len(profileKeys))
        profileStorage = runProfileEvaluation(baseStorage, profileKey)
        resultsByProfile[profileKey] = collectProfileResults(profileStorage, profileKey, vehicles)
        evaluatedKeys.append(profileKey)

    if progressCallback is not None:
        progressCallback(len(evaluatedKeys), len(profileKeys))

    return {
        "resultsByProfile": resultsByProfile,
        "evaluatedProfileKeys": evaluatedKeys,
        "projectedTrainStops": list(baseStorage.get("settingsData", {}).get("trainStops", [])),
        "vehicleCount": len(vehicles),
    }


class SimulationWorker(QObject):
    simulationFinished = Signal(dict)
    simulationFailed = Signal(str)
    progressChanged = Signal(int, int)

    def __init__(self, workerStorage, profileKeys):
        super().__init__()
        self.workerStorage = workerStorage
        self.profileKeys = list(profileKeys)
        self.cancelMutex = QMutex()
        self.isCancelRequested = False

    # Asked from the GUI thread, the run stops between tiers because an engine pass cannot be interrupted
    def requestCancel(self):
        with QMutexLocker(self.cancelMutex):
            self.isCancelRequested = True

    def checkCancelRequested(self):
        with QMutexLocker(self.cancelMutex):
            return self.isCancelRequested

    # Slot invoked once the owning QThread starts
    def runSimulation(self):
        try:
            payload = runMultiProfilePipeline(self.workerStorage, self.profileKeys,
                                              self.progressChanged.emit,
                                              self.checkCancelRequested)
            payload["wasCancelled"] = self.checkCancelRequested()
            self.simulationFinished.emit(payload)
        except Exception as exc:
            self.simulationFailed.emit(str(exc))


class SimulationController(QObject):
    # Owned by MainWindow and connected to exactly once at startup, so callers never race a fast worker
    simulationFinished = Signal(dict)
    simulationFailed = Signal(str)
    progressChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        # Flips to False the instant the run is logically over, independent of QThread teardown timing
        self.isSimulationActive = False

    def isRunning(self):
        return self.isSimulationActive

    # Build the isolated copy on the GUI thread, then hand the worker sole ownership of it
    def startSimulation(self, dataStorage, profileKeys, projectedTrainStops):
        if self.isSimulationActive:
            raise RuntimeError("a simulation is already running")

        self.isSimulationActive = True
        workerStorage = buildSimulationStorage(dataStorage, projectedTrainStops)
        self.thread = QThread()
        self.worker = SimulationWorker(workerStorage, profileKeys)
        self.worker.moveToThread(self.thread)

        # Forwarding is wired before the thread starts, so the controller's own signals never miss an emit
        self.worker.simulationFinished.connect(self.onWorkerFinished)
        self.worker.simulationFailed.connect(self.onWorkerFailed)
        self.worker.progressChanged.connect(self.progressChanged)

        self.thread.started.connect(self.worker.runSimulation)
        self.worker.simulationFinished.connect(self.thread.quit)
        self.worker.simulationFailed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.onThreadFinished)

        self.thread.start()

    # Cooperative cancel, the current tier still finishes because the engine has no interruption point
    def cancelSimulation(self):
        if self.worker is not None:
            self.worker.requestCancel()

    # Clear the running flag before forwarding, so a handler may start a new run right away
    def onWorkerFinished(self, payload):
        self.isSimulationActive = False
        self.simulationFinished.emit(payload)

    def onWorkerFailed(self, message):
        self.isSimulationActive = False
        self.simulationFailed.emit(message)

    # Drop our references once the thread has fully wound down, so a new run can start afterward
    def onThreadFinished(self):
        # finished() fires just before the OS thread actually exits, so join to close that gap
        finishedThread = self.sender()
        if finishedThread is not None:
            finishedThread.wait()
        # A newer startSimulation() call may already have replaced self.thread, so only clear our own
        if self.thread is finishedThread:
            self.thread = None
            self.worker = None

    # Block briefly for the thread to actually wind down, used only when the application is closing
    def waitForFinish(self, timeoutMs=5000):
        if self.thread is not None:
            self.thread.wait(timeoutMs)
