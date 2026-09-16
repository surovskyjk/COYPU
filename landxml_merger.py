# Sequential end-to-end concatenation of parsed LandXML alignments with rebased chainage
import numpy as np

# Scalar-km chainage arrays that must be offset when a file is rebased onto a running chainage
CHAINAGE_KEYS = ("stationHorizontal", "stationCant", "stationVertical",
                  "lineStationStart", "spiralStationStart", "curveStationStart", "keyStations")

# Numpy arrays concatenated unchanged, never treated as chainage
PASSTHROUGH_ARRAY_KEYS = ("cant", "geometryType", "radius", "curvature", "curvatureSign", "elevation",
                           "lineStartX", "lineStartY", "lineEndX", "lineEndY",
                           "spiralStartX", "spiralStartY", "spiralEndX", "spiralEndY", "spiralPIX", "spiralPIY",
                           "curveStartX", "curveStartY", "curveEndX", "curveEndY", "curveCenterX", "curveCenterY",
                           "spiralLength", "spiralRadiusStart", "spiralRadiusEnd", "spiralRot", "spiralType",
                           "spiralConst", "curveRot", "curveType", "curveRadius", "keyTypes", "keyX", "keyY")

# Plain python lists concatenated unchanged, never treated as chainage
PASSTHROUGH_LIST_KEYS = ("keyLat", "keyLon")

# Coordinate-list keys combined by plain list concatenation, never offset
LIST_CONCAT_KEYS = ("alignmentCoordinates", "alignmentCoordsOriginal")

# Per-element arrays addressed by their own element type's running counter rather than by element
# index, so a crop that drops an element from geometryType must drop its entry here in the same pass
ELEMENT_ARRAY_KEYS = {
    "Line": ("lineStartX", "lineStartY", "lineEndX", "lineEndY", "lineStationStart"),
    "Spiral": ("spiralStartX", "spiralStartY", "spiralEndX", "spiralEndY", "spiralPIX", "spiralPIY",
               "spiralStationStart", "spiralLength", "spiralRadiusStart", "spiralRadiusEnd",
               "spiralRot", "spiralType", "spiralConst"),
    "Curve": ("curveStartX", "curveStartY", "curveEndX", "curveEndY", "curveCenterX", "curveCenterY",
              "curveStationStart", "curveRot", "curveType", "curveRadius"),
}

# Which element type owns a given per-element array, the reverse of ELEMENT_ARRAY_KEYS
ELEMENT_TYPE_OF_KEY = {key: elementType
                       for elementType, keys in ELEMENT_ARRAY_KEYS.items()
                       for key in keys}

# Element indexed lists holding one polyline per element, cropped alongside the element stream
ELEMENT_LIST_KEYS = ("alignmentCoordinates", "alignmentCoordsOriginal")


# Split one keep decision per element into the per type masks the element arrays are indexed by
def elementTypeMasks(geometryType, elementKeep):
    elementTypes = list(np.asarray(geometryType)[::2])
    masks = {elementType: [] for elementType in ELEMENT_ARRAY_KEYS}
    for elementIndex, elementType in enumerate(elementTypes):
        if elementType in masks and elementIndex < len(elementKeep):
            masks[elementType].append(bool(elementKeep[elementIndex]))
    return {elementType: np.array(values, dtype=bool) for elementType, values in masks.items()}


# Distance beyond which a junction gap is reported to the user
JUNCTION_GAP_WARN_M = 100.0

# Tolerance for treating two chainage values as the same seam point
SEAM_TOLERANCE_KM = 1e-6

# Tolerance for treating two cant values as identical at a seam
CANT_TOLERANCE_MM = 0.5


# Offset every chainage-bearing array of a parsed alignment by offsetKm, returning a new dict
def shiftChainage(parsedData, offsetKm):
    shifted = dict(parsedData)
    for key in CHAINAGE_KEYS:
        if key in shifted:
            shifted[key] = np.asarray(shifted[key], dtype=float) + offsetKm
    if "denseAlignment" in shifted:
        shifted["denseAlignment"] = [(station + offsetKm, lat, lon) for station, lat, lon in shifted["denseAlignment"]]
    if "keyLat" in shifted:
        shifted["keyLat"] = list(shifted["keyLat"])
    if "keyLon" in shifted:
        shifted["keyLon"] = list(shifted["keyLon"])
    return shifted


# Euclidean distance in metres between the last key point of one file and the first of the next, in original coordinates
def junctionGapMeters(previousData, nextData):
    prevX = previousData.get("keyX")
    prevY = previousData.get("keyY")
    nextX = nextData.get("keyX")
    nextY = nextData.get("keyY")
    if prevX is None or nextX is None or len(prevX) == 0 or len(nextX) == 0:
        return 0.0
    dx = float(nextX[0]) - float(prevX[-1])
    dy = float(nextY[0]) - float(prevY[-1])
    return float(np.sqrt(dx * dx + dy * dy))


# Drop the shifted file's leading cant sample when it exactly restates the merged data's trailing one
def trimCantSeam(mergedData, shifted, tolKm=SEAM_TOLERANCE_KM):
    mergedStations = mergedData.get("stationCant")
    shiftedStations = shifted.get("stationCant")
    if mergedStations is None or shiftedStations is None or len(mergedStations) == 0 or len(shiftedStations) == 0:
        return shifted
    mergedCant = mergedData.get("cant")
    shiftedCant = shifted.get("cant")
    stationsMatch = abs(float(mergedStations[-1]) - float(shiftedStations[0])) <= tolKm
    cantMatches = abs(float(mergedCant[-1]) - float(shiftedCant[0])) <= CANT_TOLERANCE_MM
    if stationsMatch and cantMatches:
        trimmed = dict(shifted)
        trimmed["stationCant"] = shiftedStations[1:]
        trimmed["cant"] = shiftedCant[1:]
        return trimmed
    return shifted


# Drop the shifted file's leading vertical sample when it lands on the merged data's trailing station
def trimVerticalSeam(mergedData, shifted, tolKm=SEAM_TOLERANCE_KM):
    mergedStations = mergedData.get("stationVertical")
    shiftedStations = shifted.get("stationVertical")
    if mergedStations is None or shiftedStations is None or len(mergedStations) == 0 or len(shiftedStations) == 0:
        return shifted
    if abs(float(mergedStations[-1]) - float(shiftedStations[0])) <= tolKm:
        trimmed = dict(shifted)
        trimmed["stationVertical"] = shiftedStations[1:]
        trimmed["elevation"] = np.asarray(shifted["elevation"])[1:]
        return trimmed
    return shifted


# Concatenate one shifted file's arrays onto the running merged dict
def appendInto(merged, shifted):
    combined = dict(merged)
    for key in CHAINAGE_KEYS + PASSTHROUGH_ARRAY_KEYS:
        if key in combined and key in shifted:
            combined[key] = np.concatenate([np.asarray(combined[key]), np.asarray(shifted[key])])
    for key in PASSTHROUGH_LIST_KEYS + LIST_CONCAT_KEYS:
        if key in combined and key in shifted:
            combined[key] = list(combined[key]) + list(shifted[key])
    if "denseAlignment" in combined and "denseAlignment" in shifted:
        combined["denseAlignment"] = list(combined["denseAlignment"]) + list(shifted["denseAlignment"])
    return combined


# Recompute slope in permille from stationVertical [km] and elevation [m], mirroring gui.py:1556-1561
def recomputeSlope(mergedData):
    stations = np.asarray(mergedData.get("stationVertical", []), dtype=float)
    elevation = np.asarray(mergedData.get("elevation", []), dtype=float)
    if len(stations) < 2:
        mergedData["slope"] = np.array([0.0])
        return
    deltaZ = np.diff(elevation)
    deltaX = np.diff(stations)
    slope = np.zeros_like(deltaX)
    valid = deltaX != 0
    slope[valid] = deltaZ[valid] / deltaX[valid]
    mergedData["slope"] = slope


# Concatenate several parsed LandXML alignments end to end, rebasing chainage unless the caller
# already has genuinely contiguous real-world chainage across the files (rebaseChainage=False)
def concatAlignments(parsedList, startChainageKm=0.0, rebaseChainage=True):
    if not parsedList:
        raise ValueError("concatAlignments requires at least one parsed alignment")
    for parsedData in parsedList:
        if "error" in parsedData:
            raise ValueError(f"cannot merge a failed parse result: {parsedData['error']}")

    merged = None
    junctions = []
    runningEndKm = startChainageKm

    for fileIndex, parsedData in enumerate(parsedList):
        stationHorizontal = np.asarray(parsedData["stationHorizontal"], dtype=float)
        fileStartKm = float(np.min(stationHorizontal))
        fileEndKm = float(np.max(stationHorizontal))
        offsetKm = (runningEndKm - fileStartKm) if rebaseChainage else 0.0
        shifted = shiftChainage(parsedData, offsetKm)

        if merged is None:
            merged = shifted
        else:
            junctions.append({
                "junctionIndex": fileIndex,
                "stationKm": runningEndKm,
                "gapMeters": junctionGapMeters(parsedList[fileIndex - 1], parsedData),
            })
            shifted = trimCantSeam(merged, shifted)
            shifted = trimVerticalSeam(merged, shifted)
            merged = appendInto(merged, shifted)

        runningEndKm += (fileEndKm - fileStartKm)

    recomputeSlope(merged)
    merged["denseAlignment"] = sorted(merged.get("denseAlignment", []), key=lambda point: point[0])
    merged["junctionStationsKm"] = [junction["stationKm"] for junction in junctions]

    if len(merged["geometryType"]) != len(merged["stationHorizontal"]):
        raise ValueError("stationHorizontal and geometryType length mismatch after merge")

    return merged, junctions
