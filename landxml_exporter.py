# LandXML 1.2 writer for the merged alignment: CoordGeom, calculated Cant and a non-overlapping Profile
import xml.etree.ElementTree as ET
from datetime import datetime

import numpy as np

import project_metadata

# Namespace and schema version every exported document declares
LANDXML_NAMESPACE = "http://www.landxml.org/schema/LandXML-1.2"
LANDXML_SCHEMA_LOCATION = ("http://www.landxml.org/schema/LandXML-1.2 "
                           "http://www.landxml.org/schema/LandXML-1.2/LandXML-1.2.xsd")
LANDXML_VERSION = "1.2"

# Application identity required in the header of every exported file
EXPORTER_APPLICATION_NAME = "COYPU"
EXPORTER_APPLICATION_VERSION = "2.0"
EXPORTER_MANUFACTURER = "COYPU Team"

# Preferred vertical curve radius, scaled down only when adjacent tangents would overlap
DEFAULT_VERTICAL_RADIUS_M = 5000.0

# Fraction of the available tangent length two neighbouring vertical curves may consume
VERTICAL_TANGENT_SAFETY = 0.98

# Passes allowed while shrinking vertical radii until no pair of tangents overlaps
VERTICAL_FIT_ITERATIONS = 32

# Nominal track gauge written into the cant block
TRACK_GAUGE_MM = 1435.0

# Speed profile written when the project settings name none
DEFAULT_SPEED_PROFILE = "150"

# Decimal places used for coordinates, stations and cant values
COORDINATE_DECIMALS = 4
STATION_DECIMALS = 4
CANT_DECIMALS = 1
SPEED_DECIMALS = 1


# Trim a float to a fixed number of decimals, writing INF the way LandXML expects
def formatNumber(value, decimals=COORDINATE_DECIMALS):
    numericValue = float(value)
    if not np.isfinite(numericValue):
        return "INF"
    return f"{numericValue:.{decimals}f}"


# Drop attributes whose value is empty so the document carries no meaningless pairs
def nonEmptyAttributes(attributes):
    return {name: value for name, value in attributes.items() if str(value).strip()}


# One array element or None when the index is out of range, keeps partial data exportable
def safeIndex(values, index):
    array = np.asarray(values) if values is not None else np.asarray([])
    if index < 0 or index >= len(array):
        return None
    return array[index]


# Speed profile suffix (100/130/150/K) chosen in the project settings
def resolveSpeedProfileKey(settingsData):
    profileDefault = (settingsData or {}).get("profileDefault", [])
    profileName = str(profileDefault[0]) if profileDefault else ""
    profileName = profileName.strip()
    if profileName.startswith("I"):
        profileName = profileName[1:]
    return profileName or DEFAULT_SPEED_PROFILE


# Rebuild the per element table from the flat station and type arrays produced by the parser
def buildElementTable(landXmlData):
    stationHorizontal = np.asarray(landXmlData.get("stationHorizontal", []), dtype=float)
    geometryType = np.asarray(landXmlData.get("geometryType", []))

    elements = []
    typeCounters = {}
    for elementIndex in range(len(stationHorizontal) // 2):
        typeName = str(geometryType[2 * elementIndex]) if 2 * elementIndex < len(geometryType) else "Line"
        typeIndex = typeCounters.get(typeName, 0)
        typeCounters[typeName] = typeIndex + 1
        elements.append({
            "elementType": typeName,
            "typeIndex": typeIndex,
            "staStartM": float(stationHorizontal[2 * elementIndex]) * 1000.0,
            "staEndM": float(stationHorizontal[2 * elementIndex + 1]) * 1000.0,
        })
    return elements


# Shrink the placeholder vertical radii until no two adjacent curve tangents overlap
def buildVerticalCurvePlan(stationsM, elevations, defaultRadius=DEFAULT_VERTICAL_RADIUS_M):
    stations = np.asarray(stationsM, dtype=float)
    heights = np.asarray(elevations, dtype=float)
    pointCount = min(len(stations), len(heights))
    if pointCount < 2:
        return [{"stationM": float(stations[index]), "elevation": float(heights[index]),
                 "radius": 0.0, "curveLength": 0.0} for index in range(pointCount)]

    stations = stations[:pointCount]
    heights = heights[:pointCount]

    spans = np.diff(stations)
    grades = np.zeros(pointCount - 1)
    validSpans = spans != 0
    grades[validSpans] = np.diff(heights)[validSpans] / spans[validSpans]

    # Grade change at every interior break, the endpoints never carry a vertical curve
    gradeChanges = np.zeros(pointCount)
    gradeChanges[1:-1] = np.abs(np.diff(grades))

    radii = np.where(gradeChanges > 0.0, float(defaultRadius), 0.0)

    for _ in range(VERTICAL_FIT_ITERATIONS):
        tangents = radii * gradeChanges / 2.0
        hasOverlap = False
        for spanIndex in range(pointCount - 1):
            availableLength = float(spans[spanIndex]) * VERTICAL_TANGENT_SAFETY
            requiredLength = float(tangents[spanIndex] + tangents[spanIndex + 1])
            if requiredLength <= 0.0:
                continue
            if availableLength <= 0.0:
                radii[spanIndex] = 0.0
                radii[spanIndex + 1] = 0.0
                hasOverlap = True
                continue
            if requiredLength > availableLength:
                shrinkFactor = availableLength / requiredLength
                radii[spanIndex] *= shrinkFactor
                radii[spanIndex + 1] *= shrinkFactor
                hasOverlap = True
        if not hasOverlap:
            break

    tangents = radii * gradeChanges / 2.0
    return [{"stationM": float(stations[index]), "elevation": float(heights[index]),
             "radius": float(radii[index]), "curveLength": float(2.0 * tangents[index])}
            for index in range(pointCount)]


class LandXmlExporter:
    def __init__(self, landXmlData, metadata, settingsData=None):
        self.landXmlData = landXmlData or {}
        self.metadata = project_metadata.normalizeMetadata(metadata)
        self.settingsData = settingsData or {}
        self.speedProfileKey = resolveSpeedProfileKey(self.settingsData)

    # True once there is enough parsed geometry for an export to be meaningful
    def hasExportableGeometry(self):
        return len(np.asarray(self.landXmlData.get("stationHorizontal", []))) >= 2

    # Chainage of the first and last element in metres
    def alignmentBounds(self):
        stationHorizontal = np.asarray(self.landXmlData.get("stationHorizontal", []), dtype=float)
        if len(stationHorizontal) == 0:
            return 0.0, 0.0
        return float(np.nanmin(stationHorizontal)) * 1000.0, float(np.nanmax(stationHorizontal)) * 1000.0

    # Alignment name shown by receiving CAD software
    def alignmentName(self):
        return (self.metadata.get("projectTitle") or self.metadata.get("trackSection")
                or "COYPU_Alignment")

    # Complete LandXML document as an indented UTF-8 string
    def buildDocument(self):
        timestamp = datetime.now()
        rootElement = ET.Element("LandXML", {
            "xmlns": LANDXML_NAMESPACE,
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": LANDXML_SCHEMA_LOCATION,
            "version": LANDXML_VERSION,
            "date": timestamp.strftime("%Y-%m-%d"),
            "time": timestamp.strftime("%H:%M:%S"),
        })

        self.appendUnits(rootElement)
        self.appendCoordinateSystem(rootElement)
        self.appendProject(rootElement)
        self.appendApplication(rootElement, timestamp)
        self.appendAlignments(rootElement)

        ET.indent(rootElement, space="  ")
        return ET.tostring(rootElement, encoding="unicode", xml_declaration=True)

    # Metric unit declaration, cant values are written in millimetres as noted on the Cant element
    def appendUnits(self, rootElement):
        unitsElement = ET.SubElement(rootElement, "Units")
        ET.SubElement(unitsElement, "Metric", {
            "areaUnit": "squareMeter",
            "linearUnit": "meter",
            "volumeUnit": "cubicMeter",
            "temperatureUnit": "celsius",
            "pressureUnit": "milliBars",
            "diameterUnit": "millimeter",
            "angularUnit": "decimal degrees",
            "directionUnit": "decimal degrees",
        })

    # Coordinate reference descriptors taken straight from the project metadata dialog
    def appendCoordinateSystem(self, rootElement):
        ET.SubElement(rootElement, "CoordinateSystem", nonEmptyAttributes({
            "name": self.metadata.get("coordinateSystemName", ""),
            "horizontalDatum": self.metadata.get("horizontalDatum", ""),
            "verticalDatum": self.metadata.get("verticalDatum", ""),
            "desc": self.metadata.get("epsgCode", ""),
        }))

    # Project header carrying the identification fields and the optional national track codes
    def appendProject(self, rootElement):
        projectElement = ET.SubElement(rootElement, "Project", nonEmptyAttributes({
            "name": self.alignmentName(),
            "desc": self.metadata.get("description", ""),
        }))
        featureElement = ET.SubElement(projectElement, "Feature", {"code": "COYPU_Metadata"})
        for fieldKey in project_metadata.METADATA_FIELD_KEYS:
            fieldValue = self.metadata.get(fieldKey, "")
            if fieldValue:
                ET.SubElement(featureElement, "Property", {"label": fieldKey, "value": fieldValue})

    # Explicit application tag identifying COYPU as the producing software
    def appendApplication(self, rootElement, timestamp):
        applicationElement = ET.SubElement(rootElement, "Application", {
            "name": EXPORTER_APPLICATION_NAME,
            "version": EXPORTER_APPLICATION_VERSION,
            "manufacturer": EXPORTER_MANUFACTURER,
            "timeStamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        authorName = self.metadata.get("authorName", "")
        if authorName:
            ET.SubElement(applicationElement, "Author", {"createdBy": authorName})

    # Single alignment holding the horizontal geometry, the vertical profile and the cant block
    def appendAlignments(self, rootElement):
        startStation, endStation = self.alignmentBounds()
        alignmentsElement = ET.SubElement(rootElement, "Alignments", {"name": self.alignmentName()})
        alignmentElement = ET.SubElement(alignmentsElement, "Alignment", nonEmptyAttributes({
            "name": self.alignmentName(),
            "length": formatNumber(endStation - startStation, STATION_DECIMALS),
            "staStart": formatNumber(startStation, STATION_DECIMALS),
            "desc": self.metadata.get("targetStandard", ""),
        }))

        self.appendCoordGeom(alignmentElement)
        self.appendProfile(alignmentElement)
        self.appendCant(alignmentElement)

    # Straight lines, clothoids and circular arcs in running chainage order
    def appendCoordGeom(self, alignmentElement):
        coordGeomElement = ET.SubElement(alignmentElement, "CoordGeom",
                                         {"name": self.alignmentName()})
        for element in buildElementTable(self.landXmlData):
            elementType = element["elementType"]
            if elementType == "Line":
                self.appendLine(coordGeomElement, element)
            elif elementType == "Spiral":
                self.appendSpiral(coordGeomElement, element)
            elif elementType == "Curve":
                self.appendCurve(coordGeomElement, element)

    # Append a point child such as Start, End, PI or Center
    def appendPoint(self, parentElement, tagName, pointX, pointY):
        if pointX is None or pointY is None:
            return
        pointElement = ET.SubElement(parentElement, tagName)
        pointElement.text = f"{formatNumber(pointX)} {formatNumber(pointY)}"

    def appendLine(self, coordGeomElement, element):
        typeIndex = element["typeIndex"]
        startX = safeIndex(self.landXmlData.get("lineStartX"), typeIndex)
        startY = safeIndex(self.landXmlData.get("lineStartY"), typeIndex)
        endX = safeIndex(self.landXmlData.get("lineEndX"), typeIndex)
        endY = safeIndex(self.landXmlData.get("lineEndY"), typeIndex)

        lineElement = ET.SubElement(coordGeomElement, "Line", {
            "staStart": formatNumber(element["staStartM"], STATION_DECIMALS),
            "length": formatNumber(element["staEndM"] - element["staStartM"], STATION_DECIMALS),
        })
        self.appendPoint(lineElement, "Start", startX, startY)
        self.appendPoint(lineElement, "End", endX, endY)

    def appendSpiral(self, coordGeomElement, element):
        typeIndex = element["typeIndex"]
        radiusStart = safeIndex(self.landXmlData.get("spiralRadiusStart"), typeIndex)
        radiusEnd = safeIndex(self.landXmlData.get("spiralRadiusEnd"), typeIndex)
        spiralLength = safeIndex(self.landXmlData.get("spiralLength"), typeIndex)
        rotation = safeIndex(self.landXmlData.get("spiralRot"), typeIndex)
        spiralType = safeIndex(self.landXmlData.get("spiralType"), typeIndex)

        if spiralLength is None:
            spiralLength = element["staEndM"] - element["staStartM"]

        spiralElement = ET.SubElement(coordGeomElement, "Spiral", {
            "staStart": formatNumber(element["staStartM"], STATION_DECIMALS),
            "length": formatNumber(spiralLength, STATION_DECIMALS),
            "radiusStart": formatNumber(radiusStart if radiusStart is not None else np.inf),
            "radiusEnd": formatNumber(radiusEnd if radiusEnd is not None else np.inf),
            "rot": str(rotation) if rotation is not None else "cw",
            "spiType": str(spiralType) if spiralType is not None else "clothoid",
        })
        self.appendPoint(spiralElement, "Start",
                         safeIndex(self.landXmlData.get("spiralStartX"), typeIndex),
                         safeIndex(self.landXmlData.get("spiralStartY"), typeIndex))
        self.appendPoint(spiralElement, "PI",
                         safeIndex(self.landXmlData.get("spiralPIX"), typeIndex),
                         safeIndex(self.landXmlData.get("spiralPIY"), typeIndex))
        self.appendPoint(spiralElement, "End",
                         safeIndex(self.landXmlData.get("spiralEndX"), typeIndex),
                         safeIndex(self.landXmlData.get("spiralEndY"), typeIndex))

    def appendCurve(self, coordGeomElement, element):
        typeIndex = element["typeIndex"]
        radius = safeIndex(self.landXmlData.get("curveRadius"), typeIndex)
        rotation = safeIndex(self.landXmlData.get("curveRot"), typeIndex)
        curveType = safeIndex(self.landXmlData.get("curveType"), typeIndex)

        curveElement = ET.SubElement(coordGeomElement, "Curve", {
            "staStart": formatNumber(element["staStartM"], STATION_DECIMALS),
            "length": formatNumber(element["staEndM"] - element["staStartM"], STATION_DECIMALS),
            "radius": formatNumber(radius if radius is not None else np.inf),
            "rot": str(rotation) if rotation is not None else "cw",
            "crvType": str(curveType) if curveType is not None else "arc",
        })
        self.appendPoint(curveElement, "Start",
                         safeIndex(self.landXmlData.get("curveStartX"), typeIndex),
                         safeIndex(self.landXmlData.get("curveStartY"), typeIndex))
        self.appendPoint(curveElement, "Center",
                         safeIndex(self.landXmlData.get("curveCenterX"), typeIndex),
                         safeIndex(self.landXmlData.get("curveCenterY"), typeIndex))
        self.appendPoint(curveElement, "End",
                         safeIndex(self.landXmlData.get("curveEndX"), typeIndex),
                         safeIndex(self.landXmlData.get("curveEndY"), typeIndex))

    # Vertical profile with circular curves whose tangents are guaranteed never to overlap
    def appendProfile(self, alignmentElement):
        stationsKm = np.asarray(self.landXmlData.get("stationVertical", []), dtype=float)
        elevations = np.asarray(self.landXmlData.get("elevation", []), dtype=float)
        if len(stationsKm) == 0 or len(elevations) == 0:
            return

        profileElement = ET.SubElement(alignmentElement, "Profile", {
            "name": self.alignmentName(),
            "desc": "COYPU vertical alignment",
        })
        profAlignElement = ET.SubElement(profileElement, "ProfAlign", {"name": self.alignmentName()})

        for point in buildVerticalCurvePlan(stationsKm * 1000.0, elevations):
            pointText = (f"{formatNumber(point['stationM'], STATION_DECIMALS)} "
                         f"{formatNumber(point['elevation'], STATION_DECIMALS)}")
            if point["radius"] > 0.0 and point["curveLength"] > 0.0:
                curveElement = ET.SubElement(profAlignElement, "CircCurve", {
                    "length": formatNumber(point["curveLength"], STATION_DECIMALS),
                    "radius": formatNumber(point["radius"], STATION_DECIMALS),
                })
                curveElement.text = pointText
            else:
                pviElement = ET.SubElement(profAlignElement, "PVI")
                pviElement.text = pointText

    # Cant stations carrying the newly calculated cant D and the matching design speed
    def appendCant(self, alignmentElement):
        stationsKm, cantValues, isCalculated = self.resolveCantSeries()
        if len(stationsKm) == 0:
            return

        designSpeeds = self.resolveDesignSpeeds(stationsKm)
        maximumSpeed = float(np.nanmax(designSpeeds)) if len(designSpeeds) else 0.0

        cantElement = ET.SubElement(alignmentElement, "Cant", {
            "name": self.alignmentName(),
            "gauge": formatNumber(TRACK_GAUGE_MM, 0),
            "rotationPoint": "insideRail",
            "equilibriumConstant": "11.8",
            "speed": formatNumber(maximumSpeed, SPEED_DECIMALS),
            "desc": ("COYPU optimized cant D in millimetres"
                     if isCalculated else "Imported cant D in millimetres"),
        })

        for index, stationKm in enumerate(stationsKm):
            ET.SubElement(cantElement, "CantStation", {
                "station": formatNumber(float(stationKm) * 1000.0, STATION_DECIMALS),
                "appliedCant": formatNumber(abs(float(cantValues[index])), CANT_DECIMALS),
                "speed": formatNumber(float(designSpeeds[index]), SPEED_DECIMALS),
            })

    # Prefer the optimized cant produced by the geometry engine, fall back to the imported one
    def resolveCantSeries(self):
        calculatedStations = np.asarray(self.landXmlData.get("stationCantPossible", []), dtype=float)
        calculatedCant = np.asarray(self.landXmlData.get("cantPossible", []), dtype=float)
        if len(calculatedStations) > 0 and len(calculatedCant) == len(calculatedStations):
            return calculatedStations, calculatedCant, True

        importedStations = np.asarray(self.landXmlData.get("stationCant", []), dtype=float)
        importedCant = np.asarray(self.landXmlData.get("cant", []), dtype=float)
        sampleCount = min(len(importedStations), len(importedCant))
        return importedStations[:sampleCount], importedCant[:sampleCount], False

    # Design speed sampled from the active GPK profile at every cant station
    def resolveDesignSpeeds(self, stationsKm):
        profileStations = np.asarray(
            self.landXmlData.get(f"stationSpeed{self.speedProfileKey}", []), dtype=float)
        profileSpeeds = np.asarray(
            self.landXmlData.get(f"speedLimits{self.speedProfileKey}", []), dtype=float)

        sampleCount = min(len(profileStations), len(profileSpeeds))
        if sampleCount < 2:
            fallbackSpeed = float((self.settingsData.get("vInit") or [0])[0])
            return np.full(len(stationsKm), fallbackSpeed, dtype=float)

        order = np.argsort(profileStations[:sampleCount], kind="stable")
        return np.interp(np.asarray(stationsKm, dtype=float),
                         profileStations[:sampleCount][order], profileSpeeds[:sampleCount][order])


# Write the export to disk and return the number of geometry elements it contains
def exportAlignmentToFile(filePath, landXmlData, metadata, settingsData=None):
    exporter = LandXmlExporter(landXmlData, metadata, settingsData)
    if not exporter.hasExportableGeometry():
        raise ValueError("no parsed horizontal geometry available for export")

    documentText = exporter.buildDocument()
    with open(filePath, "w", encoding="utf-8") as fileHandle:
        fileHandle.write(documentText)
    return len(buildElementTable(landXmlData))
