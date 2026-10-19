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
    # Rounding cannot honour every leg minimum, the caller falls back to the unrounded split
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


# Scheduled origin to destination time and the legs between stops for one cell
def computeScheduledTimes(legRunTimesS, intermediateDwellS, lengthKm, margin,
                          roundingStepMin=DEFAULT_ROUNDING_STEP_MIN,
                          roundingMode=DEFAULT_ROUNDING_MODE):
    legTimes = [max(float(runTimeS), 0.0) for runTimeS in legRunTimesS]
    if not legTimes:
        return {"scheduledOriginDestS": None, "scheduledLegsS": [], "scheduledRunningS": None,
                "isLegRoundingRelaxed": False}

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

    availableS = roundedS - dwellS
    if runningS > 0.0:
        weights = [runTimeS / runningS for runTimeS in legTimes]
    else:
        weights = [1.0 / len(legTimes)] * len(legTimes)

    totalSteps = max(math.floor(availableS / stepS + EPSILON), 0)
    # A leg must never be scheduled shorter than the train needs for it
    minSteps = [math.ceil(runTimeS / stepS - EPSILON) for runTimeS in legTimes]
    steps, ranking = apportionSteps(totalSteps, weights, minSteps)

    if steps is None:
        # The proportional split is exact but not on the step grid, and the cell says so
        scheduledLegs = [availableS * weight for weight in weights]
        isRelaxed = True
    else:
        scheduledLegs = [count * stepS for count in steps]
        # A dwell that is not a multiple of the step leaves a fraction below one step for one leg
        leftoverS = availableS - totalSteps * stepS
        scheduledLegs[ranking[0]] += max(leftoverS, 0.0)
        isRelaxed = False

    return {
        "scheduledOriginDestS": roundedS,
        "scheduledLegsS": scheduledLegs,
        "scheduledRunningS": availableS,
        "isLegRoundingRelaxed": isRelaxed,
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
    intermediateDwellS = sum(float(section.get("dwellAtToS") or 0.0) for section in sections[:-1])
    lengthKm = sum(float(section.get("lengthKm") or 0.0) for section in sections)
    return computeScheduledTimes([section["rawRunS"] for section in sections], intermediateDwellS,
                                 lengthKm, margin, settings["roundingStepMin"],
                                 settings["roundingMode"])


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
    return computeScheduledTimes(
        [leg["runTimeS"] for leg in legs], sum(leg["dwellAtToS"] for leg in legs[:-1]),
        sum(leg["lengthKm"] for leg in legs), margin, settings["roundingStepMin"],
        settings["roundingMode"])
