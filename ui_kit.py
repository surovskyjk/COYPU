# Small shared widgets used by the vehicle catalog, purge dialog and statistics dock
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QToolButton, QVBoxLayout, QWidget


# Colours used only when a card is themed before the theme manager has handed over its tokens
LIGHT_CARD_TOKENS = {"border": "#c4c4c4", "alternateBase": "#e9e9ec",
                     "text": "#1c1c1c", "mutedText": "#5a5a5a"}
DARK_CARD_TOKENS = {"border": "#4d4d4d", "alternateBase": "#333333",
                    "text": "#e6e6e6", "mutedText": "#b0b0b0"}


# English captions of the three stopping patterns, used when a locale lacks the entry
DEFAULT_PATTERN_CAPTIONS = {"Os": "Os (local)", "Sp": "Sp (semi-fast)", "Ex": "Ex (express)"}


# Caption of one stopping pattern from the translation, with the English text as fallback
def patternCaptionFor(lan, patternKey):
    return lan.get(f"stopPattern{patternKey}", DEFAULT_PATTERN_CAPTIONS.get(patternKey, patternKey))


# Plural neutral count text such as "stops: 6", so no language needs a plural form
def stopsCountText(lan, count):
    return lan.get("stopsCountLabel", "stops: {count}").format(count=count)


# Compact KPI tile showing a bold value, a muted caption and an optional sub caption
class MetricCard(QFrame):
    def __init__(self, captionText="", parent=None):
        super().__init__(parent)

        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.captionLabel = QLabel(captionText)
        self.captionLabel.setStyleSheet("font-size: 9px; color: palette(mid);")

        self.valueLabel = QLabel("-")
        self.valueLabel.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.valueLabel.setWordWrap(True)

        self.subLabel = QLabel("")
        self.subLabel.setStyleSheet("font-size: 9px; color: palette(mid);")
        self.subLabel.setWordWrap(True)
        self.subLabel.setVisible(False)

        layout.addWidget(self.captionLabel)
        layout.addWidget(self.valueLabel)
        layout.addWidget(self.subLabel)

    # Replace the caption shown above the value
    def setCaption(self, captionText):
        self.captionLabel.setText(captionText)

    # Replace the bold value and the optional muted sub caption below it
    def setValue(self, valueText, subText=""):
        self.valueLabel.setText(valueText)
        self.subLabel.setText(subText)
        self.subLabel.setVisible(bool(subText))

    # Restyle the card border, background and captions with the active theme's tokens
    def applyTheme(self, isDark, tokens=None):
        tokens = tokens or (DARK_CARD_TOKENS if isDark else LIGHT_CARD_TOKENS)
        borderColor = tokens.get("border", "#c4c4c4")
        backgroundColor = tokens.get("alternateBase", "#ffffff")
        textColor = tokens.get("text", "#1c1c1c")
        mutedColor = tokens.get("mutedText", "#5a5a5a")

        self.setStyleSheet(
            f"MetricCard {{ border: 1px solid {borderColor}; border-radius: 4px;"
            f" background: {backgroundColor}; }}")

        # Captions carry their own colour so they never fall back to an unreadable palette default
        for label in (self.captionLabel, self.subLabel):
            label.setStyleSheet(f"font-size: 9px; color: {mutedColor};")
        self.valueLabel.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {textColor};")


# Checkable header that shows or hides a content widget built lazily on first expand
class CollapsibleSection(QWidget):
    expandedChanged = Signal(bool)

    def __init__(self, titleText="", parent=None, contentFactory=None, startExpanded=False):
        super().__init__(parent)

        self.contentFactory = contentFactory
        self.contentWidget = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.headerButton = QToolButton()
        self.headerButton.setText(titleText)
        self.headerButton.setCheckable(True)
        self.headerButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.headerButton.setArrowType(Qt.ArrowType.RightArrow)
        self.headerButton.setStyleSheet(
            "QToolButton { border: none; font-weight: 600; padding: 2px; }")
        self.headerButton.toggled.connect(self.onToggled)

        self.contentHost = QWidget()
        self.contentHostLayout = QVBoxLayout(self.contentHost)
        self.contentHostLayout.setContentsMargins(4, 2, 4, 4)
        self.contentHost.setVisible(False)

        layout.addWidget(self.headerButton)
        layout.addWidget(self.contentHost)

        if startExpanded:
            self.headerButton.setChecked(True)

    # Replace the caption on the collapsible header
    def setTitle(self, titleText):
        self.headerButton.setText(titleText)

    # Embed a widget immediately instead of waiting for the first expand
    def setContentWidget(self, widget):
        self.contentWidget = widget
        self.contentHostLayout.addWidget(widget)

    # Build the content widget on demand and toggle its visibility
    def onToggled(self, isExpanded):
        self.headerButton.setArrowType(
            Qt.ArrowType.DownArrow if isExpanded else Qt.ArrowType.RightArrow)

        if isExpanded and self.contentWidget is None and self.contentFactory is not None:
            self.contentWidget = self.contentFactory()
            self.contentHostLayout.addWidget(self.contentWidget)

        self.contentHost.setVisible(isExpanded)
        self.expandedChanged.emit(isExpanded)

    # Programmatically expand or collapse the section
    def setExpanded(self, isExpanded):
        self.headerButton.setChecked(bool(isExpanded))

    def isExpanded(self):
        return self.headerButton.isChecked()
