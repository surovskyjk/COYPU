# Headless scheduled travel time rules: recovery margins, one time rounding and the leg split
import copy
import math

import batch_metrics
import stops_model

# Rounding modes of the scheduled origin to destination time
ROUNDING_MODES = ("nearest", "up", "down")

# Default rounding step in minutes and the default mode
DEFAULT_ROUNDING_STEP_MIN = 0.5
DEFAULT_ROUNDING_MODE = "nearest"

# Default recovery margin of every stopping pattern
DEFAULT_MARGIN = {"percent": 5.0, "minutesPer100Km": 0.0, "fixedMinutes": 0.0}

# Tolerance that keeps float noise from moving a value across a rounding boundary
EPSILON = 1e-9


# The schedule settings a fresh project starts with
def defaultScheduleSettings():
    return {
        "recoveryMargins": {patternKey: dict(DEFAULT_MARGIN) for patternKey in stops_model.PATTERN_KEYS},
        "roundingStepMin": DEFAULT_ROUNDING_STEP_MIN,
        "roundingMode": DEFAULT_ROUNDING_MODE,
    }


# Non negative float from any stored value, the default when it is unreadable
def nonNegativeFloat(value, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if number >= 0.0 and math.isfinite(number) else float(default)


# Complete and validated schedule settings merged over the defaults
def normalizeScheduleSettings(rawSettings):
    normalized = defaultScheduleSettings()
    rawSettings = rawSettings if isinstance(rawSettings, dict) else {}
    rawMargins = rawSettings.get("recoveryMargins")
    rawMargins = rawMargins if isinstance(rawMargins, dict) else {}

    for patternKey in stops_model.PATTERN_KEYS:
        rawMargin = rawMargins.get(patternKey)
        rawMargin = rawMargin if isinstance(rawMargin, dict) else {}
        for fieldKey, defaultValue in DEFAULT_MARGIN.items():
            normalized["recoveryMargins"][patternKey][fieldKey] = nonNegativeFloat(
                rawMargin.get(fieldKey, defaultValue), defaultValue)

    stepMin = nonNegativeFloat(rawSettings.get("roundingStepMin"), DEFAULT_ROUNDING_STEP_MIN)
    normalized["roundingStepMin"] = stepMin if stepMin > 0.0 else DEFAULT_ROUNDING_STEP_MIN
    roundingMode = rawSettings.get("roundingMode")
    normalized["roundingMode"] = roundingMode if roundingMode in ROUNDING_MODES else DEFAULT_ROUNDING_MODE
    return normalized


# Value quantised to the step once, nearest rounds half up rather than to the even neighbour
def quantizeSeconds(valueS, stepS, roundingMode=DEFAULT_ROUNDING_MODE):
    if stepS <= 0.0:
        return float(valueS)
    ratio = float(valueS) / stepS
    if roundingMode == "up":
        steps = math.ceil(ratio - EPSILON)
    elif roundingMode == "down":
        steps = math.floor(ratio + EPSILON)
    else:
        steps = math.floor(ratio + 0.5 + EPSILON)
    return steps * stepS


# Whole steps of the running time split over the legs by weight, none below its own minimum
def apportionSteps(totalSteps, weights, minSteps=None):
    legCount = len(weights)
    minimums = list(minSteps) if minSteps is not None else [0] * legCount
    # Rounding cannot honour every leg minimum, computeScheduledTimes raises the total so this never happens there
    if sum(minimums) > totalSteps:
        return None, None

    shares = [totalSteps * weight for weight in weights]
    steps = [max(minimums[index], math.floor(shares[index] + EPSILON)) for index in range(legCount)]

    # Only legs above their minimum give a step back, the one with the smallest remainder first
    excess = sum(steps) - totalSteps
    while excess > 0:
        reducible = [index for index in range(legCount) if steps[index] > minimums[index]]
        giveBack = min(reducible, key=lambda index: (shares[index] - steps[index], -index))
        steps[giveBack] -= 1
        excess -= 1

    remainders = [share - count for share, count in zip(shares, steps)]
    # Ties go to the earlier leg so the split is deterministic
    ranking = sorted(range(legCount), key=lambda index: (-remainders[index], index))
    for position in range(max(totalSteps - sum(steps), 0)):
        steps[ranking[position % legCount]] += 1
    return steps, ranking


# Smallest whole steps that keep the timetable at or above the raw run: every leg rounded up, every dwell rounded
# down where the next leg still keeps each stretch from a departure to a later arrival at or above its raw time,
# otherwise rounded up
def scheduleDwellSteps(legTimesS, dwellsS, stepS):
    legSteps = [math.ceil(runTimeS / stepS - EPSILON) for runTimeS in legTimesS]
    dwellSteps = []
    # Scheduled minus raw time at the current event, and the largest such slack at any departure so far
    slackS = 0.0
    maxDepartureSlackS = 0.0
    for index, dwellS in enumerate(dwellsS):
        slackS += legSteps[index] * stepS - legTimesS[index]
        downSteps = math.floor(dwellS / stepS + EPSILON)
        nextLegSlackS = legSteps[index + 1] * stepS - legTimesS[index + 1]
        if slackS - (dwellS - downSteps * stepS) + nextLegSlackS >= maxDepartureSlackS - EPSILON:
            steps = downSteps
        else:
            steps = math.ceil(dwellS / stepS - EPSILON)
        slackS += steps * stepS - dwellS
        maxDepartureSlackS = max(maxDepartureSlackS, slackS)
        dwellSteps.append(steps)
    return legSteps, dwellSteps


# Scheduled origin to destination time, the legs between stops and the intermediate dwells for one cell: the run
# with its margins rounded once, raised only when that would leave a leg or a stretch of legs below its raw time
def computeScheduledTimes(legRunTimesS, intermediateDwellS, lengthKm, margin,
                          roundingStepMin=DEFAULT_ROUNDING_STEP_MIN,
                          roundingMode=DEFAULT_ROUNDING_MODE, intermediateDwellsS=None):
    legTimes = [max(float(runTimeS), 0.0) for runTimeS in legRunTimesS]
    if not legTimes:
        return {"scheduledOriginDestS": None, "scheduledLegsS": [], "scheduledDwellsS": [],
                "scheduledRunningS": None, "isLegRoundingRelaxed": False}

    runningS = sum(legTimes)
    dwellS = max(float(intermediateDwellS), 0.0)
    stepS = max(float(roundingStepMin), EPSILON) * 60.0

    # Percentage applies to the running time only, dwell passes through unchanged
    unroundedS = (runningS * (1.0 + float(margin.get("percent", 0.0)) / 100.0)
                  + 60.0 * (float(margin.get("minutesPer100Km", 0.0)) * float(lengthKm) / 100.0
                            + float(margin.get("fixedMinutes", 0.0)))
                  + dwellS)
    roundedS = quantizeSeconds(unroundedS, stepS, roundingMode)
    roundedS = max(roundedS, quantizeSeconds(dwellS, stepS, "up"))

    if runningS > 0.0:
        weights = [runTimeS / runningS for runTimeS in legTimes]
    else:
        weights = [1.0 / len(legTimes)] * len(legTimes)

    # Without the dwell of every stop the whole dwell is taken at the first intermediate stop
    if intermediateDwellsS is not None:
        dwellsS = [max(float(value), 0.0) for value in intermediateDwellsS]
    else:
        dwellsS = ([dwellS] + [0.0] * (len(legTimes) - 2)) if len(legTimes) > 1 else []
    legSteps, dwellSteps = scheduleDwellSteps(legTimes, dwellsS, stepS)
    roundedSteps = int(round(roundedS / stepS))
    minimalSteps = sum(legSteps) + sum(dwellSteps)
    totalSteps = max(roundedSteps, minimalSteps)

    # Steps the rounded run has beyond the minimum go to the legs by their raw time
    legTotalSteps = totalSteps - sum(dwellSteps)
    steps, _ = apportionSteps(legTotalSteps, weights, legSteps)

    return {
        "scheduledOriginDestS": totalSteps * stepS,
        "scheduledLegsS": [count * stepS for count in steps],
        "scheduledDwellsS": [count * stepS for count in dwellSteps],
        "scheduledRunningS": legTotalSteps * stepS,
        # The once rounded run was too short to keep every leg at or above its raw time, so it was raised
        "isLegRoundingRelaxed": minimalSteps > roundedSteps,
    }


# Scheduled values of one scenario matrix cell, None when the cell has no usable legs
def scheduleCell(cell, scheduleSettings):
    sections = cell.get("sections") or []
    if cell.get("status") != "ok" or not sections:
        return None
    if any(section.get("rawRunS") is None for section in sections):
        return None

    settings = normalizeScheduleSettings(scheduleSettings)
    margin = settings["recoveryMargins"][stops_model.normalizePatternKey(cell.get("patternKey"))]
    intermediateDwellsS = [float(section.get("dwellAtToS") or 0.0) for section in sections[:-1]]
    lengthKm = sum(float(section.get("lengthKm") or 0.0) for section in sections)
    return computeScheduledTimes([section["rawRunS"] for section in sections], sum(intermediateDwellsS),
                                 lengthKm, margin, settings["roundingStepMin"],
                                 settings["roundingMode"], intermediateDwellsS)


# Independent copy of schedule settings, safe to edit in a dialog
def copyScheduleSettings(scheduleSettings):
    return copy.deepcopy(normalizeScheduleSettings(scheduleSettings))


# Scheduled values of the active pattern for one vehicle of the flat kinematics keys, None without legs
def scheduleFromStorage(dataStorage, vehicleIndex):
    settingsData = (dataStorage or {}).get("settingsData", {}) or {}
    stationsM = dataStorage.get(f"kinematicsStationM_{vehicleIndex}")
    timesS = dataStorage.get(f"kinematicsTimeS_{vehicleIndex}")
    orderedStops = batch_metrics.orderStopsForRun(batch_metrics.stopsList(dataStorage), stationsM)
    legs = batch_metrics.computeTravelTimeSectionDetails(stationsM, timesS, orderedStops)["legs"]
    if not legs or any(leg["runTimeS"] is None for leg in legs):
        return None

    settings = normalizeScheduleSettings(settingsData.get("scheduleSettings"))
    margin = settings["recoveryMargins"][stops_model.normalizePatternKey(
        settingsData.get("activeStopPattern"))]
    intermediateDwellsS = [leg["dwellAtToS"] for leg in legs[:-1]]
    return computeScheduledTimes(
        [leg["runTimeS"] for leg in legs], sum(intermediateDwellsS),
        sum(leg["lengthKm"] for leg in legs), margin, settings["roundingStepMin"],
        settings["roundingMode"], intermediateDwellsS)
