# Folder based vehicle catalog backed by the extended vehicle CSV format
import csv
import io
import math
from pathlib import Path

import readfile
from resource_paths import getBundleRoot, getWritableRoot

# Highest number of vehicles the dialog, reports, plots and statistics support
MAX_VEHICLES = 5

# Folder scanned for catalog files, resolved against the bundle and writable roots
CATALOG_DIRECTORY_NAME = "vehicles"

# Section identifiers understood by the extended vehicle CSV format
SECTION_META = "meta"
SECTION_PARAM = "param"
SECTION_RES = "res"
SECTION_TRAC = "trac"

# Header row written by the serialiser and skipped by the parser
CSV_HEADER_ROW = ["Section", "Col1", "Col2", "Col3", "Col4", "Col5", "Col6"]

# Metadata keys carried by the single line Meta rows
META_VEHICLE_NAME = "vehicleName"
META_MAX_SPEED = "maxSpeedKmh"
META_MASS = "massTonnes"
META_LENGTH = "lengthM"
META_BRAKE_DECEL = "brakeDecelMs2"
META_MAX_TRACTIVE_FORCE = "maxTractiveForceKN"
META_ROT_MASS = "rotMassFactor"
META_MAX_CANT_DEFICIENCY = "maxCantDeficiencyMm"

# Fallbacks applied when a legacy CSV carries no Meta block
DEFAULT_ROT_MASS_FACTOR = 1.08
DEFAULT_BRAKE_DECEL = 0.45
DEFAULT_MAX_SPEED = 120.0

# Certified cant deficiency assumed for a vehicle whose catalog file states none
DEFAULT_MAX_CANT_DEFICIENCY_MM = 150.0

# Sampling step of the rendered tractive effort curve
CURVE_SAMPLE_STEP_KMH = 0.5

# Speed profile assigned to a vehicle that does not carry one yet
DEFAULT_SPEED_LIMIT_PLOT = ["stationSpeed150", "speedLimits150"]


# Convert a cell to a float without raising on blank or malformed input
def toFloat(value, fallback=0.0):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


class CatalogVehicle:
    def __init__(self, vehicleName="", fileName="", sourcePath=None):
        self.vehicleName = vehicleName
        self.fileName = fileName
        self.sourcePath = sourcePath

        self.maxSpeedKmh = DEFAULT_MAX_SPEED
        self.massTonnes = 0.0
        self.lengthM = 0.0
        self.brakeDecelMs2 = DEFAULT_BRAKE_DECEL
        self.rotMassFactor = DEFAULT_ROT_MASS_FACTOR
        self.maxTractiveForceKN = None
        self.maxCantDeficiencyMm = DEFAULT_MAX_CANT_DEFICIENCY_MM

        self.resCoefficients = [0.0, 0.0, 0.0]
        self.tracBands = []

    # Tractive effort in kN, mirroring the band lookup of the simulation engine
    def tractiveForceAt(self, speedKmh):
        for band in self.tracBands:
            vFrom, vTo, b0, b1, b2 = band
            if vFrom <= speedKmh <= vTo:
                return b0 + b1 * speedKmh + b2 * (speedKmh ** 2)
        return 0.0

    # Speed and tractive effort samples of every band, used by the F(v) diagram
    def sampleTractiveCurve(self, stepKmh=CURVE_SAMPLE_STEP_KMH):
        speedValues = []
        forceValues = []
        step = max(float(stepKmh), 0.01)

        for band in self.tracBands:
            vFrom, vTo, b0, b1, b2 = band
            if vTo < vFrom:
                continue

            # Round up so the exact band end is always the last sample, never skipped
            sampleCount = max(math.ceil((vTo - vFrom) / step), 1)
            for sampleIndex in range(sampleCount + 1):
                speed = min(vFrom + sampleIndex * step, vTo)
                speedValues.append(speed)
                forceValues.append(b0 + b1 * speed + b2 * (speed ** 2))

        return speedValues, forceValues

    # Highest tractive effort found on the curve, used when the CSV states none
    def peakTractiveForceKN(self):
        if self.maxTractiveForceKN is not None:
            return float(self.maxTractiveForceKN)
        _, forceValues = self.sampleTractiveCurve()
        return max(forceValues) if forceValues else 0.0

    # Highest speed covered by the traction bands
    def curveTopSpeedKmh(self):
        return max((band[1] for band in self.tracBands), default=0.0)

    # Build the vehicle settings dictionary the simulation engine consumes
    def toVehicleSettings(self, baseSettings=None):
        settings = dict(baseSettings or {})

        settings["trainMaxSpeed"] = float(self.maxSpeedKmh)
        settings["trainBrakeDecel"] = float(self.brakeDecelMs2)
        settings["maxCantDeficiencyMm"] = float(self.maxCantDeficiencyMm)
        settings["trainParam"] = [[self.vehicleName, float(self.rotMassFactor),
                                   float(self.massTonnes), float(self.lengthM)]]
        settings["trainRes"] = [[self.vehicleName] + [float(value) for value in self.resCoefficients]]
        settings["trainTrac"] = [[self.vehicleName] + [float(value) for value in band]
                                 for band in self.tracBands]

        settings.setdefault("trainInitialSpeed", 0.0)
        settings.setdefault("trainFinalSpeed", 0.0)
        settings.setdefault("runReversed", False)
        settings.setdefault("speedLimitPlot", list(DEFAULT_SPEED_LIMIT_PLOT))
        return settings


class VehicleCatalog:
    def __init__(self):
        self.vehicles = []
        self.scanErrors = []

    # Bundled and user writable catalog folders, in scanning order
    def catalogDirectories(self):
        directories = []
        for root in (getBundleRoot(), getWritableRoot()):
            candidate = Path(root) / CATALOG_DIRECTORY_NAME
            if candidate not in directories:
                directories.append(candidate)
        return directories

    # Folder new catalog files are written to, created on demand by the caller
    def writableDirectory(self):
        return Path(getWritableRoot()) / CATALOG_DIRECTORY_NAME

    # Rebuild the vehicle list from disk, a user copy overriding a bundled file
    def scanCatalog(self):
        parsedByFileName = {}
        self.scanErrors = []

        for directory in self.catalogDirectories():
            if not directory.is_dir():
                continue
            for filePath in sorted(directory.glob("*.csv")):
                catalogVehicle = self.parseCatalogFile(filePath)
                if catalogVehicle is not None:
                    parsedByFileName[filePath.name.lower()] = catalogVehicle

        self.vehicles = sorted(parsedByFileName.values(), key=lambda entry: entry.vehicleName.lower())
        return self.vehicles

    # Display names of every catalog entry, in scan order
    def vehicleNames(self):
        return [entry.vehicleName for entry in self.vehicles]

    # Look up one catalog entry by its display name
    def vehicleByName(self, vehicleName):
        needle = str(vehicleName or "").strip().lower()
        for entry in self.vehicles:
            if entry.vehicleName.strip().lower() == needle:
                return entry
        return None

    # Read and parse a single catalog file, recording a message when it fails
    def parseCatalogFile(self, filePath):
        fileContent = readfile.ReadFile().Read(str(filePath))
        if not isinstance(fileContent, str) or fileContent.startswith("Error"):
            self.scanErrors.append(str(filePath))
            return None

        try:
            return self.parseCsvText(fileContent, Path(filePath).name, filePath)
        except (csv.Error, ValueError):
            self.scanErrors.append(str(filePath))
            return None

    # Parse the extended CSV text, legacy files without a Meta block still load
    def parseCsvText(self, csvText, fileName="", sourcePath=None):
        reader = csv.reader(io.StringIO(csvText), delimiter=",")

        metaValues = {}
        paramRow = None
        resRow = None
        tracBands = []

        for row in reader:
            if not row or not str(row[0]).strip():
                continue

            section = str(row[0]).strip().lower()
            if section == "section":
                continue

            if section == SECTION_META and len(row) >= 3:
                metaValues[str(row[1]).strip()] = str(row[2]).strip()
            elif section == SECTION_PARAM and len(row) >= 4 and paramRow is None:
                paramRow = row
            elif section == SECTION_RES and len(row) >= 5 and resRow is None:
                resRow = row
            elif section == SECTION_TRAC and len(row) >= 7:
                tracBands.append([toFloat(row[2]), toFloat(row[3]), toFloat(row[4]),
                                  toFloat(row[5]), toFloat(row[6])])

        catalogVehicle = CatalogVehicle(fileName=fileName, sourcePath=sourcePath)
        catalogVehicle.tracBands = tracBands

        if paramRow is not None:
            catalogVehicle.vehicleName = str(paramRow[1]).strip()
            catalogVehicle.rotMassFactor = toFloat(paramRow[2], DEFAULT_ROT_MASS_FACTOR)
            catalogVehicle.massTonnes = toFloat(paramRow[3])
            catalogVehicle.lengthM = toFloat(paramRow[4]) if len(paramRow) >= 5 else 0.0

        if resRow is not None:
            catalogVehicle.resCoefficients = [toFloat(resRow[2]), toFloat(resRow[3]),
                                              toFloat(resRow[4])]

        # A Meta block always wins over the values duplicated in the tabular rows
        if META_VEHICLE_NAME in metaValues:
            catalogVehicle.vehicleName = metaValues[META_VEHICLE_NAME]
        if META_ROT_MASS in metaValues:
            catalogVehicle.rotMassFactor = toFloat(metaValues[META_ROT_MASS],
                                                   catalogVehicle.rotMassFactor)
        if META_MASS in metaValues:
            catalogVehicle.massTonnes = toFloat(metaValues[META_MASS], catalogVehicle.massTonnes)
        if META_LENGTH in metaValues:
            catalogVehicle.lengthM = toFloat(metaValues[META_LENGTH], catalogVehicle.lengthM)
        if META_BRAKE_DECEL in metaValues:
            catalogVehicle.brakeDecelMs2 = toFloat(metaValues[META_BRAKE_DECEL],
                                                   DEFAULT_BRAKE_DECEL)
        if META_MAX_TRACTIVE_FORCE in metaValues:
            catalogVehicle.maxTractiveForceKN = toFloat(metaValues[META_MAX_TRACTIVE_FORCE], None)
        if META_MAX_CANT_DEFICIENCY in metaValues:
            catalogVehicle.maxCantDeficiencyMm = toFloat(metaValues[META_MAX_CANT_DEFICIENCY],
                                                         DEFAULT_MAX_CANT_DEFICIENCY_MM)

        # Legacy files state no top speed, the last traction band is the best guess
        if META_MAX_SPEED in metaValues:
            catalogVehicle.maxSpeedKmh = toFloat(metaValues[META_MAX_SPEED], DEFAULT_MAX_SPEED)
        else:
            catalogVehicle.maxSpeedKmh = catalogVehicle.curveTopSpeedKmh() or DEFAULT_MAX_SPEED

        if not catalogVehicle.vehicleName:
            catalogVehicle.vehicleName = Path(fileName).stem if fileName else "Vehicle"

        return catalogVehicle

    # Render a vehicle settings dictionary as extended CSV text
    def serialiseVehicle(self, vehicleSettings, vehicleName=None):
        paramRows = vehicleSettings.get("trainParam") or []
        resRows = vehicleSettings.get("trainRes") or []
        tracRows = vehicleSettings.get("trainTrac") or []

        resolvedName = vehicleName
        if not resolvedName and paramRows:
            resolvedName = str(paramRows[0][0])
        resolvedName = (resolvedName or "Vehicle").strip()

        rotMassFactor = toFloat(paramRows[0][1], DEFAULT_ROT_MASS_FACTOR) if paramRows else DEFAULT_ROT_MASS_FACTOR
        massTonnes = toFloat(paramRows[0][2]) if paramRows else 0.0
        lengthM = toFloat(paramRows[0][3]) if paramRows and len(paramRows[0]) > 3 else 0.0

        peakForce = 0.0
        for row in tracRows:
            band = [toFloat(value) for value in row[1:6]]
            if len(band) < 5:
                continue
            probe = CatalogVehicle()
            probe.tracBands = [band]
            peakForce = max(peakForce, probe.peakTractiveForceKN())

        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(CSV_HEADER_ROW)

        writer.writerow([SECTION_META.capitalize(), META_VEHICLE_NAME, resolvedName])
        writer.writerow([SECTION_META.capitalize(), META_MAX_SPEED,
                         toFloat(vehicleSettings.get("trainMaxSpeed"), DEFAULT_MAX_SPEED)])
        writer.writerow([SECTION_META.capitalize(), META_MASS, massTonnes])
        writer.writerow([SECTION_META.capitalize(), META_LENGTH, lengthM])
        writer.writerow([SECTION_META.capitalize(), META_BRAKE_DECEL,
                         toFloat(vehicleSettings.get("trainBrakeDecel"), DEFAULT_BRAKE_DECEL)])
        writer.writerow([SECTION_META.capitalize(), META_MAX_TRACTIVE_FORCE, round(peakForce, 4)])
        writer.writerow([SECTION_META.capitalize(), META_ROT_MASS, rotMassFactor])
        writer.writerow([SECTION_META.capitalize(), META_MAX_CANT_DEFICIENCY,
                         toFloat(vehicleSettings.get("maxCantDeficiencyMm"),
                                 DEFAULT_MAX_CANT_DEFICIENCY_MM)])

        writer.writerow([SECTION_PARAM.capitalize(), resolvedName, rotMassFactor, massTonnes, lengthM])

        if resRows:
            writer.writerow([SECTION_RES.capitalize(), resolvedName, toFloat(resRows[0][1]),
                             toFloat(resRows[0][2]), toFloat(resRows[0][3])])

        for row in tracRows:
            if len(row) < 6:
                continue
            writer.writerow([SECTION_TRAC.capitalize(), resolvedName] +
                            [toFloat(value) for value in row[1:6]])

        return buffer.getvalue()

    # Write catalog CSV text to disk, creating the target folder when needed
    def writeCatalogFile(self, csvText, filePath):
        targetPath = Path(filePath)
        targetPath.parent.mkdir(parents=True, exist_ok=True)
        with open(targetPath, "w", encoding="utf-8", newline="") as fileHandle:
            fileHandle.write(csvText)
        return targetPath
