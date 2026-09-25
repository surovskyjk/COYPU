# Headless metric helpers shared by TrackStatisticsWidget and the batch runner, no Qt involved
import numpy as np

# Placeholder used when no explicit no-data text is supplied
NO_DATA_PLACEHOLDER = "--:--"

# Chainage window a stop may miss the nearest simulated sample by, matching the vehicle report lookup
STOP_MATCH_TOLERANCE_M = 2.0

# Chainages the last simulation actually ran against, already projected onto the active alignment
SIMULATED_STOPS_KEY = "simulatedTrainStops"


# Guard used before touching any optional array
def hasData(values):
    return values is not None and len(values) > 0


# Render a duration in seconds as MM:SS, or a placeholder when the value is missing
def formatDuration(seconds, noDataText=NO_DATA_PLACEHOLDER):
    if seconds is None:
        return noDataText
    minutes, secs = divmod(max(0.0, seconds), 60)
    return f"{int(minutes):02d}:{int(secs):02d}"


# Scheduled stops in the order they were imported, never sorted by chainage
def stopsList(dataStorage):
    stops = []
    # The simulated list wins because travel times must be read on the stationing the engine used
    sourceStops = dataStorage.get(SIMULATED_STOPS_KEY)
    if not sourceStops:
        sourceStops = (dataStorage.get("settingsData", {}) or {}).get("trainStops", [])
    for stop in sourceStops:
        try:
            stationKm = float(stop[0])
            dwell = float(stop[1])
            name = str(stop[2]) if len(stop) > 2 else ""
        except (IndexError, ValueError, TypeError):
            continue
        stops.append((stationKm, dwell, name))
    return stops


# Sign of the run along the chainage axis, negative when the train drives against the stationing
def runDirectionSign(stationsM):
    if not hasData(stationsM) or len(stationsM) < 2:
        return 1.0
    return -1.0 if float(stationsM[-1]) < float(stationsM[0]) else 1.0


# Stops in the order the run actually reaches them, whatever order the timetable listed them in
def orderStopsForRun(stops, stationsM):
    directionSign = runDirectionSign(stationsM)
    # A stable sort keeps two stops sharing a chainage in the order the timetable listed them
    return sorted(stops, key=lambda stop: directionSign * float(stop[0]))


# Track length in kilometres derived from the parsed alignment chainage
def computeTrackLengthKm(dataStorage):
    stationHorizontal = dataStorage.get("LandXML", {}).get("stationHorizontal")
    if not hasData(stationHorizontal):
        return None
    stationHorizontal = np.asarray(stationHorizontal, dtype=float)
    return float(np.max(stationHorizontal) - np.min(stationHorizontal))


# Cumulative time at the chainage nearest to a stop, None when the stop lies outside the simulated range
def lookupTimeAtStation(stationsM, timesS, stationKm, toleranceM=STOP_MATCH_TOLERANCE_M):
    if not hasData(stationsM) or not hasData(timesS):
        return None
    stationsM = np.asarray(stationsM, dtype=float)
    index = int(np.argmin(np.abs(stationsM - stationKm * 1000.0)))
    # Without this an out of range stop would snap to an endpoint and fake a zero length section
    if abs(float(stationsM[index]) - stationKm * 1000.0) > toleranceM:
        return None
    return float(timesS[index])


# Arrival (before dwelling) and departure (after dwelling) time at one stop
def stopTiming(stationsM, timesS, stationKm, dwellSeconds):
    depTime = lookupTimeAtStation(stationsM, timesS, stationKm)
    if depTime is None:
        return None, None
    return max(0.0, depTime - dwellSeconds), depTime


# Total, origin-to-destination and inter-station travel times for one vehicle
def computeTravelTimeSections(dataStorage, vehicleIndex):
    stationsM = dataStorage.get(f"kinematicsStationM_{vehicleIndex}")
    timesS = dataStorage.get(f"kinematicsTimeS_{vehicleIndex}")
    totalTime = float(timesS[-1]) if hasData(timesS) else None

    # Ordering by the direction of travel is what keeps a reversed run from reporting negative legs
    stops = orderStopsForRun(stopsList(dataStorage), stationsM)
    originDestTime = None
    interstationRows = []

    if hasData(stationsM) and hasData(timesS) and len(stops) >= 2:
        _, depFirst = stopTiming(stationsM, timesS, stops[0][0], stops[0][1])
        arrLast, _ = stopTiming(stationsM, timesS, stops[-1][0], stops[-1][1])
        if depFirst is not None and arrLast is not None:
            originDestTime = arrLast - depFirst

        for legIndex in range(len(stops) - 1):
            kmA, dwellA, nameA = stops[legIndex]
            kmB, dwellB, nameB = stops[legIndex + 1]
            _, depA = stopTiming(stationsM, timesS, kmA, dwellA)
            arrB, _ = stopTiming(stationsM, timesS, kmB, dwellB)
            label = f"{nameA or f'{kmA:.3f}'} → {nameB or f'{kmB:.3f}'}"
            # A leg the run never covered keeps its row, so the gap reads as no data instead of vanishing
            legTime = None if depA is None or arrB is None else arrB - depA
            interstationRows.append((label, legTime))

    return totalTime, originDestTime, interstationRows


# Linear-interpolate a station-indexed series onto a common chainage grid, NaN outside its range
def resampleSeries(stationsKm, values, gridKm):
    stationsKm = np.asarray(stationsKm, dtype=float)
    values = np.asarray(values, dtype=float)
    gridKm = np.asarray(gridKm, dtype=float)
    if len(stationsKm) == 0:
        return np.full(len(gridKm), np.nan)
    order = np.argsort(stationsKm)
    return np.interp(gridKm, stationsKm[order], values[order], left=np.nan, right=np.nan)


# Slew and radius/spiral-length deltas from the alignment optimizer, all None when no scenario ran
def computeOptimizationMetrics(lxml):
    summary = lxml.get("optimizationSummary")
    if not summary:
        return {"optimizedGroupCount": None, "skippedGroupCount": None, "maxSlewM": None, "meanSlewM": None,
                "minRadiusOldM": None, "minRadiusNewM": None, "spiralLengthGainM": None}

    optimizedGroups = [g for g in summary.get("groups", []) if g.get("status") == "optOk"]
    radiiOld = [g["radiusOldM"] for g in optimizedGroups]
    radiiNew = [g["radiusNewM"] for g in optimizedGroups]
    spiralGain = sum((g["spiralLengthsNewM"][0] - g["spiralLengthsOldM"][0]) +
                      (g["spiralLengthsNewM"][1] - g["spiralLengthsOldM"][1]) for g in optimizedGroups)

    return {
        "optimizedGroupCount": summary.get("optimizedGroupCount"),
        "skippedGroupCount": summary.get("skippedGroupCount"),
        "maxSlewM": summary.get("maxSlewM"),
        "meanSlewM": summary.get("meanSlewM"),
        "minRadiusOldM": min(radiiOld) if radiiOld else None,
        "minRadiusNewM": min(radiiNew) if radiiNew else None,
        "spiralLengthGainM": spiralGain if optimizedGroups else None,
    }


# Largest real cant deficiency of a corridor, ignoring elements that sit in cant excess.
# cDef carries the curve direction in its sign, so the curvature sign is stripped off first.
def maxCantDeficiency(cantDefValues, curvature):
    if not hasData(cantDefValues):
        return None
    values = np.asarray(cantDefValues, dtype=float)
    if hasData(curvature) and len(curvature) == len(values):
        signKappa = np.sign(np.asarray(curvature, dtype=float))
        values = np.where(signKappa == 0.0, values, signKappa * values)
    else:
        values = np.abs(values)
    return float(max(0.0, float(np.max(values))))


# Every scalar and table metric the dashboard and the ZIP exporter need for one variant result
def computeVariantMetrics(dataStorage, vehicleIndex=0, designProfileSuffix="150"):
    lxml = dataStorage.get("LandXML", {}) or {}

    designSpeeds = dataStorage.get(f"speedLimits{designProfileSuffix}")
    maxSpeedDesignKmh = float(np.max(designSpeeds)) if hasData(designSpeeds) else None

    actualSpeedsMs = dataStorage.get(f"kinematicsSpeedM_{vehicleIndex}")
    maxSpeedActualKmh = float(np.max(actualSpeedsMs) * 3.6) if hasData(actualSpeedsMs) else None
    meanSpeedActualKmh = float(np.mean(actualSpeedsMs) * 3.6) if hasData(actualSpeedsMs) else None

    totalTimeS, originDestTimeS, interstationRows = computeTravelTimeSections(dataStorage, vehicleIndex)

    cantDefValues = lxml.get(f"cDef{designProfileSuffix}")
    maxCantDefMm = maxCantDeficiency(cantDefValues, lxml.get("curvature"))

    cantValues = lxml.get("cantPossible")
    maxCantMm = float(np.max(np.abs(cantValues))) if hasData(cantValues) else None

    utilD = lxml.get(f"util_D_{designProfileSuffix}")
    utilI = lxml.get(f"util_I_{designProfileSuffix}")
    meanUtilD = float(np.mean(utilD)) if hasData(utilD) else None
    meanUtilI = float(np.mean(utilI)) if hasData(utilI) else None

    limitD = lxml.get(f"limitReachedD_{designProfileSuffix}")
    limitI = lxml.get(f"limitReachedI_{designProfileSuffix}")
    limitCountD = int(np.sum(limitD)) if hasData(limitD) else None
    limitCountI = int(np.sum(limitI)) if hasData(limitI) else None

    metrics = {
        "trackLengthKm": computeTrackLengthKm(dataStorage),
        "maxSpeedDesignKmh": maxSpeedDesignKmh,
        "maxSpeedActualKmh": maxSpeedActualKmh,
        "meanSpeedActualKmh": meanSpeedActualKmh,
        "totalTimeS": totalTimeS,
        "originDestTimeS": originDestTimeS,
        "interstationRows": interstationRows,
        "maxCantMm": maxCantMm,
        "maxCantDefMm": maxCantDefMm,
        "meanUtilD": meanUtilD,
        "meanUtilI": meanUtilI,
        "limitCountD": limitCountD,
        "limitCountI": limitCountI,
    }
    metrics.update(computeOptimizationMetrics(lxml))
    return metrics
