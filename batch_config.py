# Batch configuration schema, JSON preset persistence and variant cross-product expansion
import json

import geometry_engine

BATCH_CONFIG_VERSION = 1

# Column selection mirrors GeometryCalculator.getNormLimit exactly, keyed by design approach level
NLIN_APPROACH_COLUMNS = {"standard": 2, "limit": 4, "minmax": 6}
DEFAULT_APPROACH_COLUMNS = {"standard": 2, "limit": 3, "minmax": 4}

# Every sweepable parameter and how applySweepValue must write it into settingsData
SWEEP_PARAMETERS = {
    "maxD": {"applyMode": "scalarList", "labelKey": "sweepParamMaxD", "unitKey": "unitMm"},
    "vInit": {"applyMode": "scalarList", "labelKey": "sweepParamVInit", "unitKey": "unitKmh"},
    "iterationStep": {"applyMode": "scalar", "labelKey": "sweepParamIterationStep", "unitKey": "unitKmh"},
    "trainBrakeDecel": {"applyMode": "perVehicle", "labelKey": "sweepParamBrakeDecel", "unitKey": "unitMs2"},
    "trainMaxSpeed": {"applyMode": "perVehicle", "labelKey": "sweepParamMaxSpeed", "unitKey": "unitKmh"},
    "iLimit": {"applyMode": "normTableColumn", "tableKey": "I", "labelKey": "sweepParamILimit", "unitKey": "unitMm"},
    "nLinGradient": {"applyMode": "normTableColumn", "tableKey": "nLin", "labelKey": "sweepParamNLin", "unitKey": "unitPermille"},
    "nILinRate": {"applyMode": "normTableColumn", "tableKey": "nILin", "labelKey": "sweepParamNILin", "unitKey": "unitPermille"},
}

APPROACH_PARAMETERS = ("I", "dI", "nLin", "nILin")
APPROACH_LEVELS = ("standard", "limit", "minmax")


# Pick the norm table column for one parameter and approach level, same rule as geometry_engine.getNormLimit
def normTableColumn(tableKey, approachDict):
    level = approachDict.get(tableKey, "standard") if isinstance(approachDict, dict) else (approachDict or "standard")
    columnMap = NLIN_APPROACH_COLUMNS if tableKey == "nLin" else DEFAULT_APPROACH_COLUMNS
    return columnMap.get(level, columnMap["standard"])


# Write one swept parameter value into a settingsData copy according to its declared apply mode
def applySweepValue(settingsData, paramKey, value, approachDict=None):
    config = SWEEP_PARAMETERS.get(paramKey)
    if config is None:
        raise ValueError(f"unknown sweep parameter: {paramKey}")
    applyMode = config["applyMode"]

    if applyMode == "scalarList":
        settingsData[paramKey] = [value]
    elif applyMode == "scalar":
        settingsData[paramKey] = value
    elif applyMode == "perVehicle":
        for vehicleSettings in settingsData.get("vehicles", []):
            vehicleSettings[paramKey] = value
        settingsData[paramKey] = value
    elif applyMode == "normTableColumn":
        tableKey = config["tableKey"]
        column = normTableColumn(tableKey, approachDict)
        for row in settingsData.get(tableKey, []):
            if column < len(row):
                row[column] = value
    else:
        raise ValueError(f"unsupported apply mode: {applyMode}")


# Inclusive list of sweep values from min to max in step increments, empty when the sweep is disabled
def sweepValues(sweepConfig):
    if not sweepConfig or not sweepConfig.get("isEnabled"):
        return []
    minValue = float(sweepConfig["minValue"])
    maxValue = float(sweepConfig["maxValue"])
    stepValue = float(sweepConfig["stepValue"])
    if stepValue <= 0:
        raise ValueError("sweep stepValue must be positive")
    if maxValue < minValue:
        raise ValueError("sweep maxValue must not be lower than minValue")
    stepCount = int(round((maxValue - minValue) / stepValue))
    return [round(minValue + index * stepValue, 6) for index in range(stepCount + 1)]


# Human readable label built from a variant spec, used by the dialog preview and the dashboard legend
def buildVariantLabel(spec):
    parts = [spec.get("stopsProfileLabel", ""), spec.get("approachLabel", "")]
    if spec.get("sweepParamKey"):
        parts.append(f"{spec['sweepParamKey']}={spec['sweepValue']}")
    if spec.get("scenarioLabel"):
        parts.append(spec["scenarioLabel"])
    return " | ".join(part for part in parts if part)


# Baseline (None) plus every enabled optimization scenario, baseline first unless explicitly excluded
def enabledOptimizationScenarios(configData):
    scenarios = [s for s in (configData.get("optimizationScenarios") or []) if s.get("isEnabled", True)]
    includeBaseline = configData.get("includeBaselineScenario", True)
    if includeBaseline or not scenarios:
        return [None] + scenarios
    return scenarios


# Expand a batch config into the full cross product of variant specs, stopsProfiles outer, scenario inner
def expandVariantSpecs(configData):
    stopsProfiles = configData.get("stopsProfiles") or [{"stopsProfileId": "default", "label": "", "trainStops": []}]
    defaultApproach = {"approachId": "default", "label": "", "approach": {key: "standard" for key in APPROACH_PARAMETERS}}
    designApproaches = configData.get("designApproaches") or [defaultApproach]
    sweepConfig = configData.get("sweep", {})
    values = sweepValues(sweepConfig)
    sweepParamKey = sweepConfig.get("paramKey") if sweepConfig.get("isEnabled") else None
    valuesOrNone = values if values else [None]
    scenarios = enabledOptimizationScenarios(configData)

    specs = []
    variantIndex = 0
    for stopsProfile in stopsProfiles:
        for designApproach in designApproaches:
            for sweepValue in valuesOrNone:
                for scenario in scenarios:
                    settingsOverrides = {
                        "trainStops": stopsProfile.get("trainStops", []),
                        "designApproach": designApproach.get("approach", {}),
                    }
                    spec = {
                        "variantId": f"v{variantIndex + 1:03d}",
                        "variantIndex": variantIndex,
                        "stopsProfileId": stopsProfile.get("stopsProfileId"),
                        "stopsProfileLabel": stopsProfile.get("label", ""),
                        "trainStops": stopsProfile.get("trainStops", []),
                        "approachId": designApproach.get("approachId"),
                        "approachLabel": designApproach.get("label", ""),
                        "designApproach": designApproach.get("approach", {}),
                        "sweepParamKey": sweepParamKey if sweepValue is not None else None,
                        "sweepValue": sweepValue,
                        "scenarioId": scenario.get("scenarioId") if scenario else None,
                        "scenarioLabel": scenario.get("label", "") if scenario else "",
                        "optimizationScenario": scenario,
                        "calculationMode": configData.get("calculationMode", "design"),
                        "designProfile": configData.get("designProfile", "I150"),
                        "runVehicles": configData.get("runVehicles", True),
                        "settingsOverrides": settingsOverrides,
                    }
                    spec["label"] = buildVariantLabel(spec)
                    specs.append(spec)
                    variantIndex += 1
    return specs


class BatchConfigStore:
    # A fresh batch config with every section present but empty
    def defaultConfig(self):
        return {
            "configVersion": BATCH_CONFIG_VERSION,
            "configName": "",
            "epsgInput": "EPSG:5514",
            "trackSources": [],
            "chainageMode": "sequential",
            "startChainageKm": 0.0,
            "stopsProfiles": [],
            "designApproaches": [],
            "sweep": {"isEnabled": False, "paramKey": "", "minValue": 0.0, "maxValue": 0.0, "stepValue": 1.0},
            "optimizationScenarios": [],
            "includeBaselineScenario": True,
            "calculationMode": "design",
            "designProfile": "I150",
            "runVehicles": True,
            "baseSettings": {},
            "exportFormats": {"txt": True, "csv": True, "md": False, "pdf": True,
                              "tex": False, "png": True, "svg": False},
        }

    # Load a batch config preset from a JSON file
    def loadConfig(self, filePath):
        with open(filePath, encoding="utf-8") as fileHandle:
            return json.load(fileHandle)

    # Persist a batch config preset to a JSON file
    def saveConfig(self, filePath, configData):
        with open(filePath, "w", encoding="utf-8") as fileHandle:
            json.dump(configData, fileHandle, indent=2, ensure_ascii=False)

    # Translation-key style problem codes, empty when the config is runnable
    def validateConfig(self, configData):
        problems = []
        if not configData.get("trackSources"):
            problems.append("batchProblemNoTrackSources")
        if not configData.get("stopsProfiles"):
            problems.append("batchProblemNoStopsProfiles")
        if not configData.get("designApproaches"):
            problems.append("batchProblemNoDesignApproaches")

        sweepConfig = configData.get("sweep", {})
        if sweepConfig.get("isEnabled"):
            if sweepConfig.get("paramKey") not in SWEEP_PARAMETERS:
                problems.append("batchProblemInvalidSweepParam")
            if float(sweepConfig.get("stepValue", 0)) <= 0:
                problems.append("batchProblemInvalidSweepStep")
            if float(sweepConfig.get("minValue", 0)) > float(sweepConfig.get("maxValue", 0)):
                problems.append("batchProblemInvalidSweepRange")
            # The geometry engine cannot converge on a non positive iteration step
            if (sweepConfig.get("paramKey") == "iterationStep"
                    and float(sweepConfig.get("minValue", 0)) <= 0):
                problems.append("batchProblemInvalidSweepRange")

        for scenario in configData.get("optimizationScenarios") or []:
            if not scenario.get("isEnabled", True):
                continue
            dMax = scenario.get("dMaxM", 0.0)
            if not (0.05 <= float(dMax) <= 1.50):
                problems.append("batchProblemInvalidOptimizationDMax")
            if float(scenario.get("lMinM", 0.0)) <= 0:
                problems.append("batchProblemInvalidOptimizationLMin")
            # An absent ceiling is the engine default, only an explicitly bad one is a problem
            lkMax = float(scenario.get("lkMaxM", geometry_engine.DEFAULT_LK_MAX_M))
            if lkMax <= 0 or lkMax < float(scenario.get("lMinM", 0.0)):
                problems.append("batchProblemInvalidOptimizationLkMax")
            # A disabled ceiling is never read by the engine, so only an armed one is validated
            if scenario.get("isRMaxEnabled"):
                rMax = float(scenario.get("rMaxM", geometry_engine.DEFAULT_R_MAX_M))
                if not (geometry_engine.R_MAX_MINIMUM_M <= rMax <= geometry_engine.R_MAX_MAXIMUM_M):
                    problems.append("batchProblemInvalidOptimizationRMax")
            ratioC = scenario.get("ratioCPercent", geometry_engine.DEFAULT_RATIO_C_PERCENT)
            if not (0 <= int(ratioC) <= 100):
                problems.append("batchProblemInvalidOptimizationRatio")
            modeLcl = scenario.get("modeLcl", geometry_engine.OPTIMIZATION_MODE_NONE)
            modeLscsl = scenario.get("modeLscsl", geometry_engine.OPTIMIZATION_MODE_NONE)
            validLcl = modeLcl in geometry_engine.LCL_OPTIMIZATION_MODES or modeLcl == geometry_engine.OPTIMIZATION_MODE_NONE
            validLscsl = modeLscsl in geometry_engine.OPTIMIZATION_MODES or modeLscsl == geometry_engine.OPTIMIZATION_MODE_NONE
            if not (validLcl and validLscsl):
                problems.append("batchProblemInvalidOptimizationMode")
            if modeLcl == geometry_engine.OPTIMIZATION_MODE_NONE and modeLscsl == geometry_engine.OPTIMIZATION_MODE_NONE:
                problems.append("batchProblemNoOptimizationPatterns")

        return problems
