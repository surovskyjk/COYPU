# Headless builder of the karto/dataset.json entry plus the centreline interpolation the map shares
import json
import math
from datetime import datetime

import numpy as np
from pyproj import Transformer

import app_version
import geometry_engine
import profile_state
import scenario_matrix
import schedule_rules
import stops_model

# Schema version of the exported dataset, bumped on any incompatible change
KARTO_SCHEMA_VERSION = 1

# ZIP entry name the dataset is stored under inside a .coypu archive
KARTO_ENTRY_NAME = "karto/dataset.json"

# Application name written into the dataset header
KARTO_APPLICATION_NAME = "COYPU"

# Centreline sample spacing in metres
CENTERLINE_SAMPLE_SPACING_M = 10.0

# Decimal places of every exported quantity
LAT_LON_DECIMALS = 7
PROJECTED_DECIMALS = 3
KM_DECIMALS = 5
SECONDS_DECIMALS = 1

# Units block of the dataset
KARTO_UNITS = {"chainage": "km", "length": "m", "time": "s", "speed": "km/h"}


# Latitude and longitude along a densified alignment, linear between samples and clamped at the ends
def interpolateCenterline(denseStations, denseAlignment, stationKm):
    if not len(denseStations):
        return None

    # The dense alignment stores chainage in kilometres like the rest of the geometry
    target = float(stationKm)
    if target <= denseStations[0]:
        return denseAlignment[0][1], denseAlignment[0][2]
    if target >= denseStations[-1]:
        return denseAlignment[-1][1], denseAlignment[-1][2]

    index = int(np.searchsorted(denseStations, target, side="right")) - 1
    index = max(0, min(index, len(denseAlignment) - 2))

    startStation, startLat, startLon = denseAlignment[index]
    endStation, endLat, endLon = denseAlignment[index + 1]
    span = endStation - startStation
    ratio = 0.0 if span == 0 else (target - startStation) / span

    return startLat + ratio * (endLat - startLat), startLon + ratio * (endLon - startLon)


# Rounded float, None for anything that is not finite
def roundOrNone(value, decimals):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, decimals) if math.isfinite(number) else None


# List of rounded floats
def roundList(values, decimals):
    return [roundOrNone(value, decimals) for value in values]


# Inverse transform from WGS84 into the source CRS, None when the CRS cannot be built
def buildSourceTransformer(epsgInput):
    try:
        return Transformer.from_crs("EPSG:4326", epsgInput, always_xy=True)
    except Exception:
        return None


# Easting and northing lists of latitude and longitude lists, None entries when no transform exists
def projectToSource(transformer, latitudes, longitudes):
    if transformer is None or not len(latitudes):
        return [None] * len(latitudes), [None] * len(latitudes)
    try:
        eastings, northings = transformer.transform(np.asarray(longitudes, dtype=float),
                                                    np.asarray(latitudes, dtype=float))
    except Exception:
        return [None] * len(latitudes), [None] * len(latitudes)
    return list(np.atleast_1d(eastings)), list(np.atleast_1d(northings))


# Chainage grid every 10 m between the first and the last dense sample, always ending on the last one
def centerlineGrid(startKm, endKm):
    stepKm = CENTERLINE_SAMPLE_SPACING_M / 1000.0
    grid = np.arange(startKm, endKm, stepKm)
    return np.append(grid, endKm) if len(grid) == 0 or grid[-1] < endKm else grid


# The active centreline resampled by stationing, empty arrays when there is no dense alignment
def buildCenterline(denseAlignment, transformer):
    if len(denseAlignment) < 2:
        return {"sampleSpacingM": CENTERLINE_SAMPLE_SPACING_M, "stationingKm": [], "lat": [],
                "lon": [], "easting": [], "northing": []}

    points = np.asarray(sorted(denseAlignment, key=lambda point: point[0]), dtype=float)
    stations, uniqueIndices = np.unique(points[:, 0], return_index=True)
    latitudes = points[uniqueIndices, 1]
    longitudes = points[uniqueIndices, 2]

    grid = centerlineGrid(float(stations[0]), float(stations[-1]))
    gridLat = np.interp(grid, stations, latitudes)
    gridLon = np.interp(grid, stations, longitudes)
    eastings, northings = projectToSource(transformer, gridLat, gridLon)

    return {
        "sampleSpacingM": CENTERLINE_SAMPLE_SPACING_M,
        "stationingKm": roundList(grid, KM_DECIMALS),
        "lat": roundList(gridLat, LAT_LON_DECIMALS),
        "lon": roundList(gridLon, LAT_LON_DECIMALS),
        "easting": roundList(eastings, PROJECTED_DECIMALS),
        "northing": roundList(northings, PROJECTED_DECIMALS),
    }


# Coordinates of one stationing on the centreline, all None when the line is unusable
def pointAtStationing(denseStations, denseAlignment, transformer, stationKm):
    position = interpolateCenterline(denseStations, denseAlignment, stationKm)
    if position is None:
        return {"lat": None, "lon": None, "easting": None, "northing": None}
    latitude, longitude = position
    eastings, northings = projectToSource(transformer, [latitude], [longitude])
    return {
        "lat": roundOrNone(latitude, LAT_LON_DECIMALS),
        "lon": roundOrNone(longitude, LAT_LON_DECIMALS),
        "easting": roundOrNone(eastings[0], PROJECTED_DECIMALS),
        "northing": roundOrNone(northings[0], PROJECTED_DECIMALS),
    }


# Key point type of an element boundary, from the element that starts there and the one before it
def keyPointType(elementType, previousType):
    if previousType is None:
        return "ZÚ"
    if elementType == "Spiral":
        return "ZP" if previousType == "Line" else "KP"
    if elementType == "Curve":
        return "ZO"
    return "KO" if previousType == "Curve" else "KP"


# Element boundaries read from the active alignment: two entries per element in stationHorizontal
def activeElementBoundaries(lxml):
    geometryTypes = lxml.get("geometryType")
    stations = lxml.get("stationHorizontal")
    if geometryTypes is None or stations is None:
        return []
    if len(geometryTypes) != len(stations) or len(stations) < 2 or len(stations) % 2:
        return []

    boundaries = []
    previousType = None
    for elementIndex in range(len(stations) // 2):
        elementType = str(geometryTypes[2 * elementIndex])
        boundaries.append((float(stations[2 * elementIndex]), keyPointType(elementType, previousType)))
        previousType = elementType
    boundaries.append((float(stations[-1]), "KÚ"))
    return boundaries


# Element boundary points on the active alignment with coordinates from the active centreline
def buildKeyPoints(lxml, denseStations, denseAlignment, transformer):
    boundaries = activeElementBoundaries(lxml)
    if boundaries:
        activeStations = [station for station, _ in boundaries]
        keyTypes = [keyType for _, keyType in boundaries]
    else:
        # Without usable element arrays the imported boundaries are mapped onto the active chainage
        keyStations = lxml.get("keyStations")
        keyTypes = lxml.get("keyTypes")
        if keyStations is None or keyTypes is None or len(keyStations) == 0:
            return []
        activeStations = geometry_engine.projectChainageKmArray(lxml, keyStations)

    keyPoints = []
    for stationKm, keyType in zip(activeStations, keyTypes):
        point = {"stationingKm": roundOrNone(stationKm, KM_DECIMALS), "type": str(keyType)}
        point.update(pointAtStationing(denseStations, denseAlignment, transformer, float(stationKm)))
        keyPoints.append(point)
    return keyPoints


# Entered to active stationing map written by an optimization run, None for an untouched alignment
def buildChainageMap(lxml):
    baselineKm = lxml.get("chainageMapBaselineKm")
    activeKm = lxml.get("chainageMapActiveKm")
    if baselineKm is None or activeKm is None or len(baselineKm) == 0:
        return None
    return {"baselineKm": roundList(baselineKm, KM_DECIMALS),
            "activeKm": roundList(activeKm, KM_DECIMALS)}


# Stop table with coordinates, the stored stationing is the entered one and the active one follows the map
def buildStops(records, lxml, denseStations, denseAlignment, transformer):
    exportedStops = []
    for record in records:
        try:
            activeKm = geometry_engine.projectChainageKm(lxml, float(record["stationingKm"]))
        except (IndexError, ValueError, TypeError):
            continue
        stop = {
            "stopId": record["stopId"],
            "stopName": record["stopName"],
            "stationingKm": roundOrNone(record["stationingKm"], KM_DECIMALS),
            "activeStationingKm": roundOrNone(activeKm, KM_DECIMALS),
            "dwellTimeS": roundOrNone(record["dwellTimeS"], SECONDS_DECIMALS),
            "municipalityName": record["municipalityName"],
            "population": record["population"],
            "stopInOs": bool(record["stopInOs"]),
            "stopInSp": bool(record["stopInSp"]),
            "stopInEx": bool(record["stopInEx"]),
            "stopInSpIsManual": bool(record["stopInSpIsManual"]),
            "stopInExIsManual": bool(record["stopInExIsManual"]),
        }
        stop.update(pointAtStationing(denseStations, denseAlignment, transformer, activeKm))
        exportedStops.append(stop)
    return exportedStops


# Speed limit profile of every tier that carries data, the imported TTP follows the active chainage
def buildSpeedProfiles(dataStorage, lxml):
    speedProfiles = {}
    for profileKey in profile_state.PROFILE_KEYS:
        if not profile_state.hasProfileData(dataStorage, profileKey):
            continue
        stationKey, speedKey = profile_state.storageKeysFor(profileKey)
        # After an optimization the stored TTP stations already sit on the active chainage
        stationsKm = np.asarray(dataStorage[stationKey], dtype=float)
        speedProfiles[profileKey] = {
            "stationingKm": roundList(stationsKm, KM_DECIMALS),
            "speedKmh": roundList(np.asarray(dataStorage[speedKey], dtype=float), 1),
        }
    return speedProfiles


# Vehicle table, direction labels resolved to their effective text
def buildVehicles(settingsData, records):
    originCaption, destinationCaption = stops_model.lineEndpointCaptions(records)
    vehicles = []
    for vehicleIndex, vehicleSettings in enumerate(scenario_matrix.matrixVehicles(settingsData)):
        try:
            paramRow = vehicleSettings["trainParam"][0]
            massTonnes = float(paramRow[2])
            lengthM = float(paramRow[3]) if len(paramRow) > 3 else 0.0
        except (IndexError, KeyError, TypeError, ValueError):
            massTonnes, lengthM = None, None
        vehicles.append({
            "vehicleIndex": vehicleIndex,
            "vehicleName": scenario_matrix.vehicleDisplayName(vehicleSettings),
            "trainMaxSpeedKmh": roundOrNone(vehicleSettings.get("trainMaxSpeed"), 1),
            "massTonnes": roundOrNone(massTonnes, 3),
            "lengthM": roundOrNone(lengthM, 3),
            "directionLabels": {
                directionKey: stops_model.resolveDirectionLabel(
                    vehicleSettings, directionKey,
                    originCaption if directionKey == "forward" else destinationCaption,
                    destinationCaption if directionKey == "forward" else originCaption)
                for directionKey in stops_model.DIRECTION_LABEL_KEYS},
        })
    return vehicles


# Captions of the origin and destination stop of one cell, looked up by identifier
def cellStopCaptions(cell, recordsById):
    originRecord = recordsById.get(cell.get("originStopId"))
    destinationRecord = recordsById.get(cell.get("destinationStopId"))
    originCaption = stops_model.stopCaption(originRecord) if originRecord else ""
    destinationCaption = stops_model.stopCaption(destinationRecord) if destinationRecord else ""
    return originCaption, destinationCaption


# One scenario entry with its scheduled values filled in
def buildScenario(cell, settingsData, recordsById, scheduleSettings):
    vehicles = scenario_matrix.matrixVehicles(settingsData)
    vehicleIndex = cell["vehicleIndex"]
    vehicleSettings = vehicles[vehicleIndex] if 0 <= vehicleIndex < len(vehicles) else {}
    originCaption, destinationCaption = cellStopCaptions(cell, recordsById)
    isReversed = cell["direction"] == "reverse"

    scheduled = schedule_rules.scheduleCell(cell, scheduleSettings)
    scheduledLegs = scheduled["scheduledLegsS"] if scheduled else [None] * len(cell["sections"])

    sections = []
    for section, scheduledRunS in zip(cell["sections"], scheduledLegs):
        sections.append({
            "fromStopId": section["fromStopId"],
            "toStopId": section["toStopId"],
            "fromStationingKm": roundOrNone(section["fromStationingKm"], KM_DECIMALS),
            "toStationingKm": roundOrNone(section["toStationingKm"], KM_DECIMALS),
            "lengthKm": roundOrNone(section["lengthKm"], KM_DECIMALS),
            "rawRunS": roundOrNone(section["rawRunS"], SECONDS_DECIMALS),
            "scheduledRunS": roundOrNone(scheduledRunS, SECONDS_DECIMALS),
            "dwellAtToS": roundOrNone(section["dwellAtToS"], SECONDS_DECIMALS),
        })

    return {
        "scenarioId": f"{cell['profileKey']}|v{vehicleIndex}|{cell['patternKey']}|{cell['direction']}",
        "profileKey": cell["profileKey"],
        "vehicleIndex": vehicleIndex,
        "vehicleName": cell["vehicleName"],
        "patternKey": cell["patternKey"],
        "direction": cell["direction"],
        "isReversed": isReversed,
        "directionLabel": stops_model.resolveDirectionLabel(
            vehicleSettings, cell["direction"], originCaption, destinationCaption),
        "originStopId": cell["originStopId"],
        "destinationStopId": cell["destinationStopId"],
        "status": cell["status"],
        "rawTotalRunS": roundOrNone(cell["rawTotalRunS"], SECONDS_DECIMALS),
        "rawOriginDestS": roundOrNone(cell["rawOriginDestS"], SECONDS_DECIMALS),
        "rawRunningS": roundOrNone(cell["rawRunningS"], SECONDS_DECIMALS),
        "dwellTotalS": roundOrNone(cell["dwellTotalS"], SECONDS_DECIMALS),
        "scheduledOriginDestS": roundOrNone(
            scheduled["scheduledOriginDestS"] if scheduled else None, SECONDS_DECIMALS),
        "isLegRoundingRelaxed": bool(scheduled["isLegRoundingRelaxed"]) if scheduled else False,
        "sections": sections,
    }


# Travel time block: every matrix cell, flagged missing when none was run and stale when inputs moved
def buildTravelTimes(dataStorage, settingsData, records):
    matrix = dataStorage.get(scenario_matrix.MATRIX_STORAGE_KEY)
    scheduleSettings = schedule_rules.normalizeScheduleSettings(settingsData.get("scheduleSettings"))
    if not matrix or not matrix.get("cells"):
        return {"status": "missing", "evaluatedAt": None, "scheduleSettings": scheduleSettings,
                "designContext": None, "scenarios": []}

    recordsById = {record["stopId"]: record for record in records}
    isStale = scenario_matrix.isMatrixStale(dataStorage)
    return {
        "status": "stale" if isStale else "ok",
        "evaluatedAt": matrix.get("evaluatedAt"),
        "scheduleSettings": scheduleSettings,
        "designContext": matrix.get("designContext"),
        "scenarios": [buildScenario(cell, settingsData, recordsById, scheduleSettings)
                      for cell in matrix["cells"]],
    }


# Complete dataset dictionary of the current project state
def buildKartoDataset(dataStorage, projectMetadata, epsgInput, generatedAt=None):
    dataStorage = dataStorage or {}
    projectMetadata = projectMetadata or {}
    settingsData = dataStorage.get("settingsData", {}) or {}
    lxml = dataStorage.get("LandXML", {}) or {}
    records = stops_model.normalizeStopRecords(settingsData.get("stopRecords"))

    denseAlignment = [tuple(point) for point in (lxml.get("denseAlignment") or [])]
    denseAlignment.sort(key=lambda point: point[0])
    denseStations = [point[0] for point in denseAlignment]
    transformer = buildSourceTransformer(epsgInput)

    stationHorizontal = lxml.get("stationHorizontal")
    hasStations = stationHorizontal is not None and len(stationHorizontal) > 0
    startKm = float(np.min(stationHorizontal)) if hasStations else None
    endKm = float(np.max(stationHorizontal)) if hasStations else None

    return {
        "schemaVersion": KARTO_SCHEMA_VERSION,
        "generatedAt": generatedAt or datetime.now().isoformat(timespec="seconds"),
        "application": {"name": KARTO_APPLICATION_NAME, "version": app_version.__version__},
        "units": dict(KARTO_UNITS),
        "line": {
            "lineNumber": projectMetadata.get("lineNumber", ""),
            "lineName": projectMetadata.get("lineName", ""),
            "lineCategory": projectMetadata.get("lineCategory", ""),
            "projectTitle": projectMetadata.get("projectTitle", ""),
            "lengthKm": roundOrNone(endKm - startKm, KM_DECIMALS) if hasStations else None,
            "chainageStartKm": roundOrNone(startKm, KM_DECIMALS),
            "chainageEndKm": roundOrNone(endKm, KM_DECIMALS),
            "isOptimizedAlignment": scenario_matrix.isOptimizedAlignment(dataStorage),
        },
        "crs": {
            "source": epsgInput,
            "sourceAxisOrder": "easting,northing",
            "sourceName": projectMetadata.get("coordinateSystemName", ""),
            "geographic": "EPSG:4326",
        },
        "centerline": buildCenterline(denseAlignment, transformer),
        "chainageMap": buildChainageMap(lxml),
        "keyPoints": buildKeyPoints(lxml, denseStations, denseAlignment, transformer),
        "stops": buildStops(records, lxml, denseStations, denseAlignment, transformer),
        "stopPatterns": {patternKey: {"stopIds": stops_model.patternStopIds(records, patternKey)}
                         for patternKey in stops_model.PATTERN_KEYS},
        "speedProfiles": buildSpeedProfiles(dataStorage, lxml),
        "vehicles": buildVehicles(settingsData, records),
        "travelTimes": buildTravelTimes(dataStorage, settingsData, records),
    }


# Compact JSON text of a dataset
def serializeKartoDataset(dataset):
    return json.dumps(dataset, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
