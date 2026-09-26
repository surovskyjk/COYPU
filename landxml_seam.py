# Seam between an alignment and a LandXML file appended to it: how far the two overlap or miss each
# other, and the trim that makes the incoming file start exactly where the existing one ends
import numpy as np

import readfile
from landxml_merger import SEAM_TOLERANCE_KM

# A chainage overlap beyond this is worth showing, below it the seam is a plain rounding match
OVERLAP_NOTICE_M = 0.01

# A positional step at the seam beyond this is worth showing, either file may be off the other
JUMP_NOTICE_M = 0.10

# The distance the old gap warning used, beyond it the dialog calls the gap a large one
GAP_WARN_M = 100.0

# Smallest margin around the seam when the map zooms onto it
ZOOM_MARGIN_M = 50.0

# Per element arrays a trim rewrites, copied first so the caller's parse is never mutated
TRIMMED_KEYS = ("stationHorizontal", "radius", "curvature",
                "lineStartX", "lineStartY", "lineEndX", "lineEndY", "lineStationStart",
                "spiralStartX", "spiralStartY", "spiralEndX", "spiralEndY", "spiralPIX", "spiralPIY",
                "spiralStationStart", "spiralLength", "spiralRadiusStart", "spiralRadiusEnd",
                "curveStartX", "curveStartY", "curveEndX", "curveEndY", "curveStationStart")


# Which side the incoming file joins on and the chainage of the seam, the rule the merge uses
def mergeDirection(oldData, newData):
    oldStart = float(np.nanmin(oldData["stationHorizontal"]))
    oldEnd = float(np.nanmax(oldData["stationHorizontal"]))
    newStart = float(np.nanmin(newData["stationHorizontal"]))
    newEnd = float(np.nanmax(newData["stationHorizontal"]))
    if newStart >= oldEnd or (abs(newStart - oldEnd) <= abs(newEnd - oldStart)):
        return True, oldEnd
    return False, oldStart


def elementStream(data):
    return readfile.ReadFile().elementStream(data) or []


# Chainage in km at which an element's own geometry starts, before any merge cropped its span
def ownStartKm(data, elementType, typeIndex, spanStartKm):
    stations = data.get(f"{elementType.lower()}StationStart")
    if stations is not None and typeIndex < len(stations):
        return float(stations[typeIndex])
    return spanStartKm


# Length in metres of an element's own geometry
def elementLengthM(data, elementType, typeIndex, epsgInput):
    if elementType == "Line":
        return float(np.hypot(data["lineEndX"][typeIndex] - data["lineStartX"][typeIndex],
                              data["lineEndY"][typeIndex] - data["lineStartY"][typeIndex]))
    if elementType == "Spiral":
        return float(data["spiralLength"][typeIndex])
    angleStart, angleEnd = curveAngles(data, typeIndex, epsgInput)
    return float(abs(data["curveRadius"][typeIndex] * (angleEnd - angleStart)))


def curveAngles(data, typeIndex, epsgInput):
    return readfile.ReadFile().curveAngles(
        data["curveStartX"][typeIndex], data["curveStartY"][typeIndex],
        data["curveEndX"][typeIndex], data["curveEndY"][typeIndex],
        data["curveCenterX"][typeIndex], data["curveCenterY"][typeIndex],
        data["curveRot"][typeIndex], epsgInput)


def spiralClothoid(data, typeIndex, epsgInput):
    return readfile.ReadFile().spiralClothoid(
        data["spiralStartX"][typeIndex], data["spiralStartY"][typeIndex],
        data["spiralPIX"][typeIndex], data["spiralPIY"][typeIndex],
        data["spiralLength"][typeIndex], data["spiralRadiusStart"][typeIndex],
        data["spiralRadiusEnd"][typeIndex], data["spiralRot"][typeIndex], epsgInput)


# Point, heading and signed curvature at a distance in metres along an element's own geometry,
# all in the plane of the file coordinates, so values from different elements compare directly
def geometryAt(data, elementType, typeIndex, distanceM, epsgInput):
    if elementType == "Line":
        startX, startY = float(data["lineStartX"][typeIndex]), float(data["lineStartY"][typeIndex])
        dx = float(data["lineEndX"][typeIndex]) - startX
        dy = float(data["lineEndY"][typeIndex]) - startY
        lengthM = float(np.hypot(dx, dy))
        ratio = distanceM / lengthM if lengthM > 0 else 0.0
        return startX + dx * ratio, startY + dy * ratio, float(np.arctan2(dy, dx)), 0.0

    if elementType == "Spiral":
        spiral = spiralClothoid(data, typeIndex, epsgInput)
        return (float(spiral.X(distanceM)), float(spiral.Y(distanceM)), float(spiral.Theta(distanceM)),
                float(spiral.KappaStart + spiral.dk * distanceM))

    angleStart, angleEnd = curveAngles(data, typeIndex, epsgInput)
    radius = abs(float(data["curveRadius"][typeIndex]))
    sweep = angleEnd - angleStart
    lengthM = radius * abs(sweep)
    angle = angleStart + (sweep * distanceM / lengthM if lengthM > 0 else 0.0)
    turn = 1.0 if sweep >= 0 else -1.0
    return (float(data["curveCenterX"][typeIndex]) + radius * np.cos(angle),
            float(data["curveCenterY"][typeIndex]) + radius * np.sin(angle),
            float(angle + turn * np.pi / 2.0), turn / radius if radius > 0 else 0.0)


# Distance along an element's own geometry at which it reaches a chainage, kept on the element
def distanceAtStationM(data, elementType, typeIndex, spanStartKm, stationKm, epsgInput):
    distanceM = (stationKm - ownStartKm(data, elementType, typeIndex, spanStartKm)) * 1000.0
    return float(np.clip(distanceM, 0.0, elementLengthM(data, elementType, typeIndex, epsgInput)))


def radiusFromCurvature(curvature):
    return 1.0 / abs(curvature) if abs(curvature) > 1e-12 else np.inf


def copiedForTrim(data):
    trimmed = dict(data)
    for key in TRIMMED_KEYS:
        if key in trimmed:
            trimmed[key] = np.array(trimmed[key], copy=True)
    return trimmed


# Element stream radius and curvature at one end of an element, the pair entry index given
def writeStreamEnd(trimmed, pairIndex, radius):
    if "radius" in trimmed and pairIndex < len(trimmed["radius"]):
        trimmed["radius"][pairIndex] = radius
    if "curvature" in trimmed and pairIndex < len(trimmed["curvature"]):
        sign = 1.0
        if "curvatureSign" in trimmed and pairIndex < len(trimmed["curvatureSign"]):
            sign = float(trimmed["curvatureSign"][pairIndex])
        trimmed["curvature"][pairIndex] = sign / radius if np.isfinite(radius) and radius > 0 else 0.0


# Copy of the data whose element starts at a later chainage, its geometry cut to match. A Spiral
# keeps its clothoid, so its new start radius is the one the clothoid has at the cut.
def trimElementStart(data, elementIndex, stationKm, epsgInput):
    elementType, typeIndex, spanStartKm, _ = elementStream(data)[elementIndex]
    distanceM = distanceAtStationM(data, elementType, typeIndex, spanStartKm, stationKm, epsgInput)
    x, y, heading, curvature = geometryAt(data, elementType, typeIndex, distanceM, epsgInput)

    trimmed = copiedForTrim(data)
    prefix = elementType.lower()
    trimmed[f"{prefix}StartX"][typeIndex] = x
    trimmed[f"{prefix}StartY"][typeIndex] = y
    if f"{prefix}StationStart" in trimmed:
        trimmed[f"{prefix}StationStart"][typeIndex] = stationKm
    if elementType == "Spiral":
        # The PI only carries the start direction here, as the optimizer writes it
        trimmed["spiralPIX"][typeIndex] = x + np.cos(heading)
        trimmed["spiralPIY"][typeIndex] = y + np.sin(heading)
        trimmed["spiralLength"][typeIndex] = float(data["spiralLength"][typeIndex]) - distanceM
        trimmed["spiralRadiusStart"][typeIndex] = radiusFromCurvature(curvature)
        writeStreamEnd(trimmed, 2 * elementIndex, radiusFromCurvature(curvature))

    trimmed["stationHorizontal"][2 * elementIndex] = stationKm
    return trimmed


# Copy of the data whose element ends at an earlier chainage, its geometry cut to match
def trimElementEnd(data, elementIndex, stationKm, epsgInput):
    elementType, typeIndex, spanStartKm, _ = elementStream(data)[elementIndex]
    distanceM = distanceAtStationM(data, elementType, typeIndex, spanStartKm, stationKm, epsgInput)
    x, y, _, curvature = geometryAt(data, elementType, typeIndex, distanceM, epsgInput)

    trimmed = copiedForTrim(data)
    prefix = elementType.lower()
    trimmed[f"{prefix}EndX"][typeIndex] = x
    trimmed[f"{prefix}EndY"][typeIndex] = y
    if elementType == "Spiral":
        trimmed["spiralLength"][typeIndex] = distanceM
        trimmed["spiralRadiusEnd"][typeIndex] = radiusFromCurvature(curvature)
        writeStreamEnd(trimmed, 2 * elementIndex + 1, radiusFromCurvature(curvature))

    trimmed["stationHorizontal"][2 * elementIndex + 1] = stationKm
    return trimmed


# Signed element stream curvature at one pair entry, None where the data carries no curvature
def streamCurvature(data, pairIndex):
    curvature = data.get("curvature")
    if curvature is None or len(curvature) == 0:
        return None
    return float(curvature[pairIndex])


# Whether the cut leaves the incoming curvature at the seam no further off the existing alignment's
# than the element's own end already is. A cut Spiral starts on the radius its clothoid has at the
# cut, so where the files disagree, typically an existing tangent running on past the point at
# which the incoming transition began, the cut opens a curvature step neither file has: a Spiral
# leaving a Line at a finite radius. The cant design holds the deficiency at that start to the
# Line's zero, which leaves no permissible speed at all, and the optimizer stops taking the Spiral
# for a clothoid. A cut Line or Curve keeps its curvature, so it always passes.
def isCutCurvatureContinuous(oldData, newData, elementIndex, seamKm, isAppend, epsgInput):
    elementType, typeIndex, spanStartKm, _ = elementStream(newData)[elementIndex]
    existingKappa = streamCurvature(oldData, -1 if isAppend else 0)
    startKappa = streamCurvature(newData, 2 * elementIndex)
    endKappa = streamCurvature(newData, 2 * elementIndex + 1)
    if existingKappa is None or startKappa is None or endKappa is None:
        return True

    # Curvature runs linearly along a clothoid
    lengthM = elementLengthM(newData, elementType, typeIndex, epsgInput)
    distanceM = distanceAtStationM(newData, elementType, typeIndex, spanStartKm, seamKm, epsgInput)
    cutKappa = startKappa + (endKappa - startKappa) * (distanceM / lengthM if lengthM > 0 else 0.0)
    ownKappa = startKappa if isAppend else endKappa
    return abs(cutKappa - existingKappa) <= abs(ownKappa - existingKappa)


# The existing alignment wins the overlap: the incoming element crossing the seam is cut there,
# so the merge that follows keeps it with a chainage span that matches its geometry. Elements
# lying entirely inside the overlap are left for the merge to drop, as before. An element the
# cut would part from the existing curvature stays whole instead, its span clamped to the seam
# by the merge and its drawing clipped there, the way every crossing element was kept before.
def trimIncomingAtSeam(oldData, newData, epsgInput):
    isAppend, seamKm = mergeDirection(oldData, newData)
    for elementIndex, (_, _, spanStartKm, spanEndKm) in enumerate(elementStream(newData)):
        if spanStartKm < seamKm - SEAM_TOLERANCE_KM and spanEndKm > seamKm + SEAM_TOLERANCE_KM:
            if not isCutCurvatureContinuous(oldData, newData, elementIndex, seamKm, isAppend, epsgInput):
                return newData
            trim = trimElementStart if isAppend else trimElementEnd
            return trim(newData, elementIndex, seamKm, epsgInput)
    return newData


# Point and heading at one end of an element, atEnd picking the far end
def elementEdge(data, streamEntry, epsgInput, atEnd):
    elementType, typeIndex, _, _ = streamEntry
    distanceM = elementLengthM(data, elementType, typeIndex, epsgInput) if atEnd else 0.0
    x, y, heading, _ = geometryAt(data, elementType, typeIndex, distanceM, epsgInput)
    return (x, y), heading


# Type, chainage length and radius at the seam end of one element, for the dialog
def describeElement(data, stream, elementIndex, atEnd):
    elementType, _, spanStartKm, spanEndKm = stream[elementIndex]
    radii = data.get("radius")
    pairIndex = 2 * elementIndex + (1 if atEnd else 0)
    radius = float(radii[pairIndex]) if radii is not None and pairIndex < len(radii) else np.inf
    return {"index": elementIndex, "type": elementType,
            "lengthM": (spanEndKm - spanStartKm) * 1000.0, "radiusM": radius}


# Everything the seam dialog shows about one append, in file coordinates and metres.
# overlapM is the chainage overlap, negative for a chainage gap. jumpM is how far the incoming
# alignment sits from the existing end at the seam chainage, or from its own start across a gap.
def analyzeSeam(oldData, newData, epsgInput):
    oldStream, newStream = elementStream(oldData), elementStream(newData)
    isAppend, seamKm = mergeDirection(oldData, newData)
    report = {"isAppend": isAppend, "seamStationKm": seamKm, "needsAttention": False}
    if not oldStream or not newStream:
        return report

    oldStartKm, oldEndKm = oldStream[0][2], oldStream[-1][3]
    newStartKm, newEndKm = newStream[0][2], newStream[-1][3]
    if isAppend:
        existingIndex, incomingEdgeIndex = len(oldStream) - 1, 0
        overlapM = (oldEndKm - newStartKm) * 1000.0
        contributesM = (newEndKm - seamKm) * 1000.0
    else:
        existingIndex, incomingEdgeIndex = 0, len(newStream) - 1
        overlapM = (newEndKm - oldStartKm) * 1000.0
        contributesM = (seamKm - newStartKm) * 1000.0

    existingXY, existingHeading = elementEdge(oldData, oldStream[existingIndex], epsgInput, atEnd=isAppend)
    incomingStartXY, incomingHeading = elementEdge(newData, newStream[incomingEdgeIndex], epsgInput,
                                                   atEnd=not isAppend)

    # Inside an overlap the incoming point that matters is the one at the seam chainage
    incomingIndex, incomingAtSeamXY = incomingEdgeIndex, incomingStartXY
    if overlapM > 0 and contributesM > 0:
        for elementIndex, (elementType, typeIndex, spanStartKm, spanEndKm) in enumerate(newStream):
            if spanStartKm <= seamKm <= spanEndKm and (spanEndKm > seamKm if isAppend else spanStartKm < seamKm):
                distanceM = distanceAtStationM(newData, elementType, typeIndex, spanStartKm, seamKm, epsgInput)
                x, y, incomingHeading, _ = geometryAt(newData, elementType, typeIndex, distanceM, epsgInput)
                incomingIndex, incomingAtSeamXY = elementIndex, (x, y)
                break

    jumpM = float(np.hypot(incomingAtSeamXY[0] - existingXY[0], incomingAtSeamXY[1] - existingXY[1]))
    deviation = (incomingHeading - existingHeading + np.pi) % (2.0 * np.pi) - np.pi

    points = np.array([existingXY, incomingStartXY, incomingAtSeamXY], dtype=float)
    lower, upper = points.min(axis=0), points.max(axis=0)
    margin = max(ZOOM_MARGIN_M, 0.25 * float(np.max(upper - lower)))

    report.update({
        "overlapM": overlapM,
        "jumpM": jumpM,
        "tangentDeviationDeg": float(abs(np.degrees(deviation))),
        "contributesM": contributesM,
        "existingElement": describeElement(oldData, oldStream, existingIndex, atEnd=isAppend),
        "incomingElement": describeElement(newData, newStream, incomingIndex, atEnd=not isAppend),
        "existingEndXY": existingXY,
        "incomingStartXY": incomingStartXY,
        "incomingAtSeamXY": incomingAtSeamXY,
        "zoomBoxXY": (float(lower[0] - margin), float(lower[1] - margin),
                      float(upper[0] + margin), float(upper[1] + margin)),
    })
    report["addsNothing"] = bool(contributesM <= SEAM_TOLERANCE_KM * 1000.0)
    report["needsAttention"] = bool(overlapM > OVERLAP_NOTICE_M or jumpM > JUMP_NOTICE_M
                                    or report["addsNothing"])
    return report
