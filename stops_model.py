# Headless stop records model: Os / Sp / Ex stopping patterns, CSV parsing and legacy migration
import copy
import csv
import io

# Stopping pattern codes: Os is a local train, Sp a semi fast one and Ex an express
PATTERN_KEYS = ("Os", "Sp", "Ex")

# Pattern shown and simulated until the user picks another one
DEFAULT_ACTIVE_PATTERN = "Os"

# Population from which a municipality earns a stop in the Sp pattern
DEFAULT_SP_POPULATION_THRESHOLD = 2000

# Dwell time a stop gets when its source states none, in seconds
DEFAULT_DWELL_TIME_S = 30.0

# Prefix and digit count of the generated stable stop identifiers
STOP_ID_PREFIX = "s"
STOP_ID_DIGITS = 3

# Columns of the stops CSV in the order they are written
CSV_COLUMNS = ("stopName", "stationingKm", "dwellTimeS", "municipalityName", "population",
               "stopInOs", "stopInSp", "stopInEx")

# Header spellings accepted for each column, compared in lower case without spaces or underscores
CSV_COLUMN_ALIASES = {
    "stopName": ("stopname", "name", "stop", "stop name"),
    "stationingKm": ("stationingkm", "stationing", "km", "chainage", "chainagekm"),
    "dwellTimeS": ("dwelltimes", "dwelltime", "dwell", "dwells"),
    "municipalityName": ("municipalityname", "municipality", "obec"),
    "population": ("population", "inhabitants", "pop", "obyvatel"),
    "stopInOs": ("stopinos", "os"),
    "stopInSp": ("stopinsp", "sp"),
    "stopInEx": ("stopinex", "ex"),
}

# Spellings of a ticked and an unticked pattern flag, compared in lower case
TRUE_TEXTS = ("1", "true", "yes", "y", "ano", "x", "t")
FALSE_TEXTS = ("0", "false", "no", "n", "ne", "f")

# Delimiters the CSV sniffer chooses between and how many lines it samples
CSV_DELIMITERS = (",", ";", "\t")
SNIFF_LINE_COUNT = 10


# Record key holding the membership flag of one pattern
def patternFlagKey(patternKey):
    return f"stopIn{patternKey}"


# Pattern code that is safe to use, anything unknown falls back to the default
def normalizePatternKey(patternKey):
    return patternKey if patternKey in PATTERN_KEYS else DEFAULT_ACTIVE_PATTERN


# Number from text with either decimal separator, None for blank or unreadable cells
def parseNumber(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    cleaned = str(text).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


# Whole number from text, thousands separators such as 12,500 or 12 500 or 12.500 are dropped
def parseInteger(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(round(float(text)))
    cleaned = str(text).strip().replace(" ", "").replace(" ", "")
    if not cleaned:
        return None
    for separator in (",", "."):
        groups = cleaned.split(separator)
        isGrouped = (len(groups) > 1 and groups[0].isdigit() and len(groups[0]) <= 3
                     and all(len(group) == 3 and group.isdigit() for group in groups[1:]))
        if isGrouped:
            return int("".join(groups))
    number = parseNumber(cleaned)
    return None if number is None else int(round(number))


# Flag from text, None when the cell is blank or not a recognised spelling
def parseFlag(text):
    if isinstance(text, bool):
        return text
    cleaned = str(text if text is not None else "").strip().lower()
    if cleaned in TRUE_TEXTS:
        return True
    if cleaned in FALSE_TEXTS:
        return False
    return None


# Generated identifier of the given one based sequence number
def formatStopId(sequenceNumber):
    return f"{STOP_ID_PREFIX}{sequenceNumber:0{STOP_ID_DIGITS}d}"


# Sequence number inside a generated identifier, 0 for any other text
def stopIdNumber(stopId):
    text = str(stopId or "")
    if text.startswith(STOP_ID_PREFIX) and text[len(STOP_ID_PREFIX):].isdigit():
        return int(text[len(STOP_ID_PREFIX):])
    return 0


# Next identifier, one above the highest number in use so a freed gap is never filled again
def nextStopId(records):
    highest = max((stopIdNumber(record.get("stopId")) for record in records or []), default=0)
    return formatStopId(highest + 1)


# One complete stop record, every key present and typed
def buildStopRecord(stopName="", stationingKm=0.0, dwellTimeS=DEFAULT_DWELL_TIME_S,
                    municipalityName="", population=None, stopInOs=True, stopInSp=False,
                    stopInEx=False, stopInSpIsManual=False, stopId="", stopInExIsManual=False):
    return {
        "stopId": str(stopId or ""),
        "stopName": str(stopName or ""),
        "stationingKm": float(stationingKm),
        "dwellTimeS": float(dwellTimeS),
        "municipalityName": str(municipalityName or ""),
        "population": None if population is None else int(round(float(population))),
        "stopInOs": bool(stopInOs),
        "stopInSp": bool(stopInSp),
        "stopInEx": bool(stopInEx),
        "stopInSpIsManual": bool(stopInSpIsManual),
        "stopInExIsManual": bool(stopInExIsManual),
    }


# Indices of the lowest and the highest stationing, the line endpoints
def endpointIndices(records):
    if not records:
        return set()
    stationings = [float(record["stationingKm"]) for record in records]
    return {stationings.index(min(stationings)), stationings.index(max(stationings))}


# True when a population reaches the threshold, a missing population never does
def meetsThreshold(population, threshold):
    return population is not None and float(population) >= float(threshold)


# Sp flag the automatic rule gives one record
def automaticSpFlag(record, isEndpoint, threshold):
    return bool(isEndpoint or meetsThreshold(record.get("population"), threshold))


# Recompute the Sp column of every record without a manual override, in place
def applySpRule(records, threshold, isAuto=True):
    if not isAuto:
        return records
    endpoints = endpointIndices(records)
    for index, record in enumerate(records):
        if not record.get("stopInSpIsManual"):
            record["stopInSp"] = automaticSpFlag(record, index in endpoints, threshold)
    return records


# Recompute the Ex column of every record without a manual override, the endpoints in place
def applyExRule(records):
    endpoints = endpointIndices(records)
    for index, record in enumerate(records):
        if not record.get("stopInExIsManual"):
            record["stopInEx"] = index in endpoints
    return records


# Recompute every automatic column: Ex always, Sp only while its automatic rule is on
def applyPatternRules(records, threshold, isSpAuto=True):
    applyExRule(records)
    return applySpRule(records, threshold, isSpAuto)


# Clear every manual Sp and Ex override and fall back to the automatic rules, in place
def resetSpOverrides(records, threshold):
    for record in records:
        record["stopInSpIsManual"] = False
        record["stopInExIsManual"] = False
    return applyPatternRules(records, threshold, True)


# Keep the ids of imported records that match an existing record by name and position, in place
def carryOverStopIds(importedRecords, existingRecords, toleranceKm=0.001):
    unmatched = list(existingRecords or [])
    for record in importedRecords:
        record["stopId"] = ""
        wantedName = str(record["stopName"]).strip().casefold()
        for candidate in unmatched:
            sameName = str(candidate["stopName"]).strip().casefold() == wantedName
            if sameName and abs(float(candidate["stationingKm"]) - float(record["stationingKm"])) <= toleranceKm:
                record["stopId"] = candidate["stopId"]
                unmatched.remove(candidate)
                break
    # Rows without a match get numbers above everything the dialog has held so far
    highest = max([stopIdNumber(record.get("stopId")) for record in existingRecords or []]
                  + [stopIdNumber(record["stopId"]) for record in importedRecords], default=0)
    for record in importedRecords:
        if not record["stopId"]:
            highest += 1
            record["stopId"] = formatStopId(highest)
    return importedRecords


# Fill a missing stop id on every record, in place
def assignStopIds(records):
    for record in records:
        if not record.get("stopId"):
            record["stopId"] = nextStopId(records)
    return records


# Records of a stored list coerced to the full typed shape, unusable entries dropped
def normalizeStopRecords(rawRecords):
    normalized = []
    for rawRecord in rawRecords or []:
        if not isinstance(rawRecord, dict):
            continue
        stationingKm = parseNumber(rawRecord.get("stationingKm"))
        if stationingKm is None:
            continue
        dwellTimeS = parseNumber(rawRecord.get("dwellTimeS"))
        normalized.append(buildStopRecord(
            stopName=rawRecord.get("stopName", ""),
            stationingKm=stationingKm,
            dwellTimeS=DEFAULT_DWELL_TIME_S if dwellTimeS is None else dwellTimeS,
            municipalityName=rawRecord.get("municipalityName", ""),
            population=parseInteger(rawRecord.get("population")),
            stopInOs=bool(rawRecord.get("stopInOs", True)),
            stopInSp=bool(rawRecord.get("stopInSp", False)),
            stopInEx=bool(rawRecord.get("stopInEx", False)),
            stopInSpIsManual=bool(rawRecord.get("stopInSpIsManual", False)),
            stopInExIsManual=bool(rawRecord.get("stopInExIsManual", False)),
            stopId=rawRecord.get("stopId", "")))
    return assignStopIds(normalized)


# Records migrated from a legacy [km, dwell, name] list: Os takes every stop, Sp and Ex the endpoints
def recordsFromLegacyStops(trainStops, threshold=DEFAULT_SP_POPULATION_THRESHOLD):
    records = []
    for stop in trainStops or []:
        try:
            stationingKm = float(stop[0])
            dwellTimeS = float(stop[1]) if len(stop) > 1 else DEFAULT_DWELL_TIME_S
        except (IndexError, ValueError, TypeError):
            continue
        stopName = str(stop[2]) if len(stop) > 2 and stop[2] is not None else ""
        records.append(buildStopRecord(stopName=stopName, stationingKm=stationingKm,
                                       dwellTimeS=dwellTimeS))
    endpoints = endpointIndices(records)
    for index, record in enumerate(records):
        record["stopInSp"] = index in endpoints
        record["stopInEx"] = index in endpoints
    applySpRule(records, threshold, True)
    return assignStopIds(records)


# Records of one pattern in their stored order
def patternRecords(records, patternKey):
    flagKey = patternFlagKey(normalizePatternKey(patternKey))
    return [record for record in records or [] if record.get(flagKey)]


# Legacy [km, dwell, name] rows of one pattern, the shape the engine and the map consume
def patternTrainStops(records, patternKey):
    return [[float(record["stationingKm"]), float(record["dwellTimeS"]), str(record["stopName"])]
            for record in patternRecords(records, patternKey)]


# Stop identifiers of one pattern in their stored order
def patternStopIds(records, patternKey):
    return [record["stopId"] for record in patternRecords(records, patternKey)]


# Number of stops in every pattern
def patternStopCounts(records):
    return {patternKey: len(patternRecords(records, patternKey)) for patternKey in PATTERN_KEYS}


# Write the active pattern into settingsData["trainStops"], leaving legacy data alone without records
def syncTrainStops(settingsData):
    if "stopRecords" not in settingsData:
        return settingsData
    settingsData["activeStopPattern"] = normalizePatternKey(
        settingsData.get("activeStopPattern", DEFAULT_ACTIVE_PATTERN))
    settingsData["trainStops"] = patternTrainStops(settingsData["stopRecords"],
                                                   settingsData["activeStopPattern"])
    return settingsData


# Give a settings dictionary every stop key, migrating a bare legacy trainStops list into records
def ensureStopSettings(settingsData):
    settingsData.setdefault("activeStopPattern", DEFAULT_ACTIVE_PATTERN)
    settingsData["activeStopPattern"] = normalizePatternKey(settingsData["activeStopPattern"])
    settingsData.setdefault("spPopulationThreshold", DEFAULT_SP_POPULATION_THRESHOLD)
    settingsData.setdefault("isSpThresholdAuto", True)

    records = normalizeStopRecords(settingsData.get("stopRecords"))
    if not records and settingsData.get("trainStops"):
        records = recordsFromLegacyStops(settingsData["trainStops"],
                                         settingsData["spPopulationThreshold"])
    settingsData["stopRecords"] = records
    return syncTrainStops(settingsData)


# Direction keys of the per vehicle labels, forward means rising chainage
DIRECTION_LABEL_KEYS = ("forward", "reverse")


# Direction labels with both keys present, anything missing or non text becomes empty
def normalizeDirectionLabels(rawLabels):
    rawLabels = rawLabels if isinstance(rawLabels, dict) else {}
    return {directionKey: str(rawLabels.get(directionKey) or "").strip()
            for directionKey in DIRECTION_LABEL_KEYS}


# Name of a stop, its stationing when it has no name
def stopCaption(record):
    name = str(record.get("stopName", "")).strip()
    return name or f"{float(record.get('stationingKm', 0.0)):.3f}"


# Captions of the lowest and the highest stop of a record list, the ends of the forward direction
def lineEndpointCaptions(records):
    if not records:
        return "", ""
    ordered = sorted(records, key=lambda record: float(record["stationingKm"]))
    return stopCaption(ordered[0]), stopCaption(ordered[-1])


# Label of one direction, an empty custom label resolves to origin and destination of that direction
def resolveDirectionLabel(vehicleSettings, directionKey, originCaption, destinationCaption):
    customLabels = normalizeDirectionLabels((vehicleSettings or {}).get("directionLabels"))
    if customLabels.get(directionKey):
        return customLabels[directionKey]
    if not originCaption and not destinationCaption:
        return ""
    return f"{originCaption} → {destinationCaption}"


# How many sampled lines of the text a delimiter splits into the same number of columns
def sampledColumnCounts(sampleLines, delimiter):
    return [len(row) for row in csv.reader(sampleLines, delimiter=delimiter)]


# Delimiter that splits the first lines into a consistent number of columns, a semicolon wins a tie
def sniffDelimiter(text):
    sampleLines = [line for line in str(text or "").splitlines() if line.strip()][:SNIFF_LINE_COUNT]
    if not sampleLines:
        return ","

    # A semicolon is tried before a comma, because decimal commas and commas inside names are common
    preferenceOrder = (";", "\t", ",")
    for delimiter in preferenceOrder:
        counts = sampledColumnCounts(sampleLines, delimiter)
        if len(set(counts)) == 1 and counts[0] > 1:
            return delimiter

    # No delimiter is consistent, so the header line decides and a tie goes to the earlier preference
    headerCounts = {delimiter: sampleLines[0].count(delimiter) for delimiter in preferenceOrder}
    best = max(preferenceOrder, key=lambda delimiter: headerCounts[delimiter])
    return best if headerCounts[best] > 0 else ","


# Header cell reduced to its comparable form
def normalizeHeaderCell(cell):
    return str(cell or "").strip().lower().replace("_", "").replace("-", "")


# Column index of every canonical column found in a header row
def mapHeaderColumns(headerRow):
    columnIndices = {}
    for index, cell in enumerate(headerRow):
        comparable = normalizeHeaderCell(cell)
        for columnName, aliases in CSV_COLUMN_ALIASES.items():
            compactAliases = [alias.replace(" ", "") for alias in aliases]
            if columnName not in columnIndices and comparable.replace(" ", "") in compactAliases:
                columnIndices[columnName] = index
                break
    return columnIndices


# Cell of a row, empty text when the row is shorter than the column index
def cellAt(row, index):
    if index is None or index >= len(row):
        return ""
    return row[index]


# Parse stops CSV text into records, the header decides between named and positional columns
def parseStopsCsv(text, defaultDwellS=DEFAULT_DWELL_TIME_S,
                  threshold=DEFAULT_SP_POPULATION_THRESHOLD):
    delimiter = sniffDelimiter(text)
    rows = [row for row in csv.reader(io.StringIO(str(text or "")), delimiter=delimiter)
            if any(str(cell).strip() for cell in row)]
    result = {"records": [], "isLegacyFormat": True, "hasPatternColumns": False}
    if not rows:
        return result

    columnIndices = mapHeaderColumns(rows[0])
    isNamed = "stationingKm" in columnIndices
    if isNamed:
        dataRows = rows[1:]
    else:
        # A legacy or unknown header is read as [km, dwell, name], a numeric first row is data
        columnIndices = {"stationingKm": 0, "dwellTimeS": 1, "stopName": 2}
        dataRows = rows if parseNumber(rows[0][0]) is not None else rows[1:]

    hasPatternColumns = isNamed and any(
        patternFlagKey(patternKey) in columnIndices for patternKey in PATTERN_KEYS)
    result["isLegacyFormat"] = not isNamed
    result["hasPatternColumns"] = hasPatternColumns

    records = []
    givenSpFlags = []
    givenFlags = []
    for row in dataRows:
        stationingKm = parseNumber(cellAt(row, columnIndices.get("stationingKm")))
        if stationingKm is None:
            continue
        dwellTimeS = parseNumber(cellAt(row, columnIndices.get("dwellTimeS")))
        records.append(buildStopRecord(
            stopName=str(cellAt(row, columnIndices.get("stopName"))).strip(),
            stationingKm=stationingKm,
            dwellTimeS=defaultDwellS if dwellTimeS is None else dwellTimeS,
            municipalityName=str(cellAt(row, columnIndices.get("municipalityName"))).strip(),
            population=parseInteger(cellAt(row, columnIndices.get("population")))))
        givenFlags.append({patternKey: parseFlag(cellAt(row, columnIndices.get(
            patternFlagKey(patternKey)))) for patternKey in PATTERN_KEYS})

    endpoints = endpointIndices(records)
    for index, record in enumerate(records):
        isEndpoint = index in endpoints
        given = givenFlags[index]
        record["stopInOs"] = True if given["Os"] is None else given["Os"]
        record["stopInEx"] = isEndpoint if given["Ex"] is None else given["Ex"]
        # An explicit Ex value that differs from the endpoint rule is a deliberate manual override
        record["stopInExIsManual"] = given["Ex"] is not None and given["Ex"] != isEndpoint
        autoSp = automaticSpFlag(record, isEndpoint, threshold)
        # An explicit Sp value that differs from the automatic rule is a deliberate manual override
        record["stopInSp"] = autoSp if given["Sp"] is None else given["Sp"]
        record["stopInSpIsManual"] = given["Sp"] is not None and given["Sp"] != autoSp
    result["records"] = assignStopIds(records)
    return result


# Number as the shortest text that reads back as exactly the same float, a whole number without ".0"
def formatCsvNumber(value):
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


# Serialise records into the stops CSV with the new header
def serializeStopsCsv(records):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for record in records or []:
        population = record.get("population")
        writer.writerow([
            record.get("stopName", ""),
            formatCsvNumber(record.get("stationingKm", 0.0)),
            formatCsvNumber(record.get("dwellTimeS", 0.0)),
            record.get("municipalityName", ""),
            "" if population is None else int(population),
            int(bool(record.get("stopInOs"))),
            int(bool(record.get("stopInSp"))),
            int(bool(record.get("stopInEx"))),
        ])
    return buffer.getvalue()


# Independent copy of a record list, safe to edit in a dialog
def copyRecords(records):
    return copy.deepcopy(list(records or []))
