# Provenance for imported LandXML segments and TTP files, enabling a selective purge
LANDXML_KIND = "landxml"
TTP_KIND = "ttp"


# One imported file's resolved contribution, kept so it can be replayed or dropped
class SourceEntry:
    def __init__(self, sourceId, kind, fileName, payload, stationStart, stationEnd, rawText=""):
        self.sourceId = sourceId
        self.kind = kind
        self.fileName = fileName
        # LandXML entries hold the parsed per file dict, TTP entries hold a (stations, speeds) tuple
        self.payload = payload
        self.stationStart = stationStart
        self.stationEnd = stationEnd
        # Original file text, kept so a saved .coypu project can carry the raw asset alongside the parse
        self.rawText = rawText or ""


class SourceStack:
    def __init__(self):
        self.entries = []
        self.nextId = 1
        # Bumped on every change, so anything derived from the imports can tell it went stale
        self.revision = 0

    # Record one resolved import and return the entry created for it
    def addEntry(self, kind, fileName, payload, stationStart, stationEnd, rawText=""):
        entry = SourceEntry(self.nextId, kind, fileName, payload, stationStart, stationEnd, rawText)
        self.entries.append(entry)
        self.nextId += 1
        self.revision += 1
        return entry

    # Entries of one kind, in the order they were imported
    def entriesForKind(self, kind):
        return [entry for entry in self.entries if entry.kind == kind]

    # Drop a single entry by id, used by the segment manager
    def removeEntry(self, sourceId):
        self.entries = [entry for entry in self.entries if entry.sourceId != sourceId]
        self.revision += 1

    # Drop every entry of one kind
    def clearKind(self, kind):
        self.entries = [entry for entry in self.entries if entry.kind != kind]
        self.revision += 1

    # Drop every entry, used by a complete project reset
    def clearAll(self):
        self.entries = []
        self.revision += 1
