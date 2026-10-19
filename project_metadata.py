# Project metadata model and the Project Properties dialog backing the .coypu file header
from datetime import datetime

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QLineEdit, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)

# Every metadata field persisted into a .coypu project, in dialog order
METADATA_FIELD_KEYS = (
    "projectTitle",
    "authorName",
    "contractNumber",
    "projectDate",
    "description",
    "lineNumber",
    "lineName",
    "lineCategory",
    "targetStandard",
    "trackSection",
    "definitionSection",
    "trackUnitCode",
    "coordinateSystemName",
    "epsgCode",
    "horizontalDatum",
    "verticalDatum",
)

# Line category codes, an empty code means not specified
LINE_CATEGORY_CODES = ("", "regional", "national")

# Translation key and English fallback of every line category caption
LINE_CATEGORY_LABELS = {
    "": ("lineCategoryNone", "Not specified"),
    "regional": ("lineCategoryRegional", "Regional"),
    "national": ("lineCategoryNational", "National / TEN-T"),
}

# Suggested design norms offered by the editable target standard combo box
STANDARD_SUGGESTIONS = ("ČSN 73 6360", "TSI INF", "DB Ril 800.0110", "SŽ S3", "EN 13803")

# Suggested coordinate system descriptors offered by the editable combo box
COORDINATE_SYSTEM_SUGGESTIONS = ("S-JTSK / Bpv", "ETRS89 / UTM 33N", "WGS 84", "DB_REF / DHHN2016")

# Fallback coordinate system descriptor written when the user leaves the field empty
DEFAULT_COORDINATE_SYSTEM_NAME = "S-JTSK / Bpv"

# Fallback EPSG descriptor matching the application wide default projection
DEFAULT_EPSG_CODE = "EPSG:5514"

# Fallback datums written into the exported LandXML coordinate system tag
DEFAULT_HORIZONTAL_DATUM = "S-JTSK"
DEFAULT_VERTICAL_DATUM = "Bpv"

# Timestamp format used for the project date field
DATE_FORMAT = "%Y-%m-%d %H:%M"


# A fresh metadata dictionary with every key present and the date stamped to now
def buildDefaultMetadata():
    return {
        "projectTitle": "",
        "authorName": "",
        "contractNumber": "",
        "projectDate": datetime.now().strftime(DATE_FORMAT),
        "description": "",
        "lineNumber": "",
        "lineName": "",
        "lineCategory": "",
        "targetStandard": STANDARD_SUGGESTIONS[0],
        "trackSection": "",
        "definitionSection": "",
        "trackUnitCode": "",
        "coordinateSystemName": DEFAULT_COORDINATE_SYSTEM_NAME,
        "epsgCode": DEFAULT_EPSG_CODE,
        "horizontalDatum": DEFAULT_HORIZONTAL_DATUM,
        "verticalDatum": DEFAULT_VERTICAL_DATUM,
    }


# Merge a loaded or partial dictionary onto the defaults so no key is ever missing
def normalizeMetadata(rawMetadata):
    normalized = buildDefaultMetadata()
    for fieldKey in METADATA_FIELD_KEYS:
        value = (rawMetadata or {}).get(fieldKey)
        if value is not None:
            normalized[fieldKey] = str(value)
    # Only the known category codes survive, anything else reads as not specified
    if normalized["lineCategory"] not in LINE_CATEGORY_CODES:
        normalized["lineCategory"] = ""
    return normalized


# Short project label used by window titles and report headers, falling back to the file stem
def describeProject(metadata, fallbackName=""):
    title = (metadata or {}).get("projectTitle", "").strip()
    return title or fallbackName


class ProjectMetadataDialog(QDialog):
    def __init__(self, metadata, lan, parent=None):
        super().__init__(parent)
        self.lan = lan or {}
        self.metadata = normalizeMetadata(metadata)

        self.setWindowTitle(self.lan.get("projectPropertiesTitle", "Project Properties"))
        self.setMinimumSize(560, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # The groups scroll, so the buttons stay on screen even on a small display
        groupsHost = QWidget()
        groupsLayout = QVBoxLayout(groupsHost)
        groupsLayout.setContentsMargins(0, 0, 0, 0)
        groupsLayout.setSpacing(8)
        groupsLayout.addWidget(self.buildIdentificationGroup())
        groupsLayout.addWidget(self.buildLineGroup())
        groupsLayout.addWidget(self.buildSectionGroup())
        groupsLayout.addWidget(self.buildCoordinateGroup())
        groupsLayout.addStretch(1)

        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameShape(QScrollArea.Shape.NoFrame)
        scrollArea.setWidget(groupsHost)
        layout.addWidget(scrollArea, 1)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                          | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    # Standard identification fields every project carries
    def buildIdentificationGroup(self):
        group = QGroupBox(self.lan.get("metadataGroupIdentification", "Identification"))
        formLayout = QFormLayout(group)

        self.inputProjectTitle = QLineEdit(self.metadata["projectTitle"])
        self.inputProjectTitle.setPlaceholderText(
            self.lan.get("metadataTitlePlaceholder", "e.g. Praha - Kacov, track modernisation"))
        formLayout.addRow(self.lan.get("metadataProjectTitle", "Project title:"), self.inputProjectTitle)

        self.inputAuthorName = QLineEdit(self.metadata["authorName"])
        formLayout.addRow(self.lan.get("metadataAuthorName", "Author / engineer:"), self.inputAuthorName)

        self.inputContractNumber = QLineEdit(self.metadata["contractNumber"])
        formLayout.addRow(self.lan.get("metadataContractNumber", "Project / contract number:"),
                          self.inputContractNumber)

        self.inputProjectDate = QLineEdit(self.metadata["projectDate"])
        formLayout.addRow(self.lan.get("metadataProjectDate", "Date / timestamp:"), self.inputProjectDate)

        self.inputTargetStandard = QComboBox()
        self.inputTargetStandard.setEditable(True)
        self.inputTargetStandard.addItems(list(STANDARD_SUGGESTIONS))
        self.inputTargetStandard.setCurrentText(self.metadata["targetStandard"])
        formLayout.addRow(self.lan.get("metadataTargetStandard", "Target standard / norm:"),
                          self.inputTargetStandard)

        self.inputDescription = QPlainTextEdit(self.metadata["description"])
        self.inputDescription.setMinimumHeight(80)
        formLayout.addRow(self.lan.get("metadataDescription", "Description / notes:"), self.inputDescription)

        return group

    # Line identification shared with the exported dataset
    def buildLineGroup(self):
        group = QGroupBox(self.lan.get("metadataGroupLine", "Line"))
        formLayout = QFormLayout(group)

        self.inputLineNumber = QLineEdit(self.metadata["lineNumber"])
        formLayout.addRow(self.lan.get("metadataLineNumber", "Line number:"), self.inputLineNumber)

        self.inputLineName = QLineEdit(self.metadata["lineName"])
        formLayout.addRow(self.lan.get("metadataLineName", "Line name:"), self.inputLineName)

        self.inputLineCategory = QComboBox()
        for categoryCode in LINE_CATEGORY_CODES:
            labelKey, fallbackText = LINE_CATEGORY_LABELS[categoryCode]
            self.inputLineCategory.addItem(self.lan.get(labelKey, fallbackText), categoryCode)
        self.inputLineCategory.setCurrentIndex(
            max(0, self.inputLineCategory.findData(self.metadata["lineCategory"])))
        formLayout.addRow(self.lan.get("metadataLineCategory", "Line category:"), self.inputLineCategory)

        return group

    # Optional national track identifiers, left blank for international projects
    def buildSectionGroup(self):
        group = QGroupBox(self.lan.get("metadataGroupSection", "Section identifiers (optional)"))
        formLayout = QFormLayout(group)

        self.inputTrackSection = QLineEdit(self.metadata["trackSection"])
        formLayout.addRow(self.lan.get("metadataTrackSection", "Track section:"), self.inputTrackSection)

        self.inputDefinitionSection = QLineEdit(self.metadata["definitionSection"])
        formLayout.addRow(self.lan.get("metadataDefinitionSection", "Definition section:"),
                          self.inputDefinitionSection)

        self.inputTrackUnitCode = QLineEdit(self.metadata["trackUnitCode"])
        self.inputTrackUnitCode.setPlaceholderText(
            self.lan.get("metadataTrackUnitPlaceholder", "TUDU code"))
        formLayout.addRow(self.lan.get("metadataTrackUnitCode", "Track unit code (TUDU):"),
                          self.inputTrackUnitCode)

        return group

    # Coordinate reference descriptors reused verbatim by the LandXML exporter
    def buildCoordinateGroup(self):
        group = QGroupBox(self.lan.get("metadataGroupCoordinates", "Coordinate system"))
        formLayout = QFormLayout(group)

        self.inputCoordinateSystemName = QComboBox()
        self.inputCoordinateSystemName.setEditable(True)
        self.inputCoordinateSystemName.addItems(list(COORDINATE_SYSTEM_SUGGESTIONS))
        self.inputCoordinateSystemName.setCurrentText(self.metadata["coordinateSystemName"])
        formLayout.addRow(self.lan.get("metadataCoordinateSystem", "Coordinate system:"),
                          self.inputCoordinateSystemName)

        self.inputEpsgCode = QLineEdit(self.metadata["epsgCode"])
        formLayout.addRow(self.lan.get("metadataEpsgCode", "EPSG code:"), self.inputEpsgCode)

        self.inputHorizontalDatum = QLineEdit(self.metadata["horizontalDatum"])
        formLayout.addRow(self.lan.get("metadataHorizontalDatum", "Horizontal datum:"),
                          self.inputHorizontalDatum)

        self.inputVerticalDatum = QLineEdit(self.metadata["verticalDatum"])
        formLayout.addRow(self.lan.get("metadataVerticalDatum", "Vertical datum:"), self.inputVerticalDatum)

        return group

    # Read every edited field back into a complete metadata dictionary
    def getMetadata(self):
        return {
            "projectTitle": self.inputProjectTitle.text().strip(),
            "authorName": self.inputAuthorName.text().strip(),
            "contractNumber": self.inputContractNumber.text().strip(),
            "projectDate": self.inputProjectDate.text().strip(),
            "description": self.inputDescription.toPlainText().strip(),
            "lineNumber": self.inputLineNumber.text().strip(),
            "lineName": self.inputLineName.text().strip(),
            "lineCategory": self.inputLineCategory.currentData() or "",
            "targetStandard": self.inputTargetStandard.currentText().strip(),
            "trackSection": self.inputTrackSection.text().strip(),
            "definitionSection": self.inputDefinitionSection.text().strip(),
            "trackUnitCode": self.inputTrackUnitCode.text().strip(),
            "coordinateSystemName": self.inputCoordinateSystemName.currentText().strip(),
            "epsgCode": self.inputEpsgCode.text().strip(),
            "horizontalDatum": self.inputHorizontalDatum.text().strip(),
            "verticalDatum": self.inputVerticalDatum.text().strip(),
        }
