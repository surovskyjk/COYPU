import io
import json
from urllib.parse import quote

import folium
from folium import DivIcon
from folium.features import ColorLine
import math
from PySide6.QtCore import (QBuffer, QFile, QIODevice, QObject, Qt, QTimer, QUrl,
                            Signal, Slot)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QWidget, QVBoxLayout)
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
                                     QWebEngineUrlScheme, QWebEngineUrlSchemeHandler)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
import numpy as np
import branca.colormap as bcm
from branca.element import MacroElement, Template

import basemap_key
import icons
from geometry_engine import SLEW_VISIBLE_THRESHOLD_MM
from ribbon import SERIES_TOGGLE_PROPERTY

# Maximum number of alignment samples handed to the page for nearest point lookup
MAX_LOOKUP_POINTS = 2000

# Maximum number of vertices drawn per line, a coloured line costs one svg path per segment
MAX_RENDER_POINTS = 20000

# Tile policies want the application named with a contact, and OpenRailwayMap refuses a bare
# browser agent. It is the real application agent, the CARTO and OSM terms forbid a forged one
MAP_TILE_USER_AGENT = "COYPU/1.0 (+https://github.com/surovskyjk/COYPU)"

# Private scheme the rendered page is served over, so no size limited data url is involved
MAP_PAGE_SCHEME = b"coypu"
MAP_PAGE_URL = "coypu://map/page.html"

# Set once the scheme was registered, a second registration would be refused by Qt anyway
isMapPageSchemeRegistered = False


# Qt refuses a scheme registered after QApplication exists, so this runs at import time
def registerMapPageScheme():
    global isMapPageSchemeRegistered
    if isMapPageSchemeRegistered:
        return

    scheme = QWebEngineUrlScheme(MAP_PAGE_SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme
                    | QWebEngineUrlScheme.Flag.LocalAccessAllowed
                    | QWebEngineUrlScheme.Flag.CorsEnabled)
    QWebEngineUrlScheme.registerScheme(scheme)
    isMapPageSchemeRegistered = True


# main.py imports this module before it builds QApplication, which is what makes this legal
registerMapPageScheme()

# The imported axis is kept only as a faint reference under the active one
BASELINE_ALIGNMENT_COLOR = "#888888"
BASELINE_ALIGNMENT_OPACITY = 0.6
BASELINE_ALIGNMENT_DASH = "6,6"

# Width and opacity of the heat line marking the sections that actually moved
SLEW_INDICATOR_WEIGHT = 7
SLEW_INDICATOR_OPACITY = 0.55

# Base maps offered by the overlay selector, the value is stored in currentBaseMap
BASEMAP_CHOICES = [
    ("positron", "mapPositron", "CartoDB Voyager"),
    ("osm", "mapOSM", "OpenStreetMap"),
    ("cuzk", "mapCUZK", "CUZK orthophoto"),
    ("cartodbDark", "mapCartoDark", "CartoDB Dark"),
]

# Attribution wording the CARTO, OSM and OpenRailwayMap terms each ask for, linked as required
CARTO_ATTRIBUTION = ('&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
                     'contributors, &copy; <a href="https://carto.com/attribution/">CARTO</a>')
OSM_ATTRIBUTION = ('&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
                   'contributors')
RAIL_OVERLAY_ATTRIBUTION = (
    'Data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, '
    'Style: <a href="https://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA 2.0</a> '
    '<a href="https://www.openrailwaymap.org/">OpenRailwayMap</a>')

# Tile template, attribution and the deepest zoom the provider actually ships, per base map
BASEMAP_TILE_SOURCES = {
    "positron": ("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
                 CARTO_ATTRIBUTION, 20),
    "cartodbDark": ("https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png",
                    CARTO_ATTRIBUTION, 20),
    "osm": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", OSM_ATTRIBUTION, 19),
}

# CARTO stamps every tile requested without a key, so these are only offered once one is set
CARTO_BASEMAPS = ("positron", "cartodbDark")

# Base map used when a chosen one has no tile definition or needs a key that is missing
FALLBACK_BASEMAP = "osm"

# Zoom bounds of the viewport, deeper than any provider ships so slews stay inspectable
MAP_MAX_ZOOM = 22
MAP_MIN_ZOOM = 3

# Deepest zoom the OpenRailwayMap overlay renders natively
RAIL_OVERLAY_NATIVE_ZOOM = 19

# Alignment rendering styles offered by the style selector
DRAW_MODE_SINGLE = "single"
DRAW_MODE_SPEED = "speed"
DRAW_MODE_TYPE = "type"

# Alignment style combo entries, the value is emitted by drawModeChanged
DRAW_MODE_CHOICES = [
    (DRAW_MODE_SINGLE, "mapDrawSingleColor", "Single Color"),
    (DRAW_MODE_TYPE, "mapDrawByType", "By Element Type"),
    (DRAW_MODE_SPEED, "mapDrawBySpeed", "By Speed Limit"),
]

# Offset of the floating control panel, chosen to clear the Leaflet zoom buttons
CONTROL_PANEL_MARGIN = 10

# Width of the two compact zoom step buttons
ZOOM_BUTTON_WIDTH = 34
CONTROL_PANEL_TOP = 10

# Injected into every rendered map so the chainage crosshair works in both directions
CURSOR_SCRIPT_TEMPLATE = """
{webChannelSource}

window.coypuCursorMarker = null;
window.coypuBridge = null;
window.coypuPoints = {lookupPoints};
window.coypuDetailsInitial = {detailsEnabled};
window.coypuLabels = {tooltipLabels};
window.coypuTooltip = null;
window.coypuLastSent = 0;
window.coypuMeasurePoints = [];
window.coypuMeasureLayer = null;
window.coypuMeasureMode = false;
window.coypuDetailsEnabled = true;

// Railway style chainage caption, 12.345 km becomes km 12+345
window.coypuFormatChainage = function (stationKm) {{
    var whole = Math.floor(stationKm);
    var metres = (stationKm - whole) * 1000.0;
    return 'km ' + whole + '+' + ('00' + metres.toFixed(0)).slice(-3);
}};

window.coypuHideTooltip = function () {{
    if (window.coypuTooltip !== null) {{ window.coypuTooltip.style.display = 'none'; }}
}};

// Show element type, radius, length, chainage and any lateral slew under the cursor
window.coypuUpdateTooltip = function (event, point) {{
    if (window.coypuTooltip === null) {{
        window.coypuTooltip = document.createElement('div');
        window.coypuTooltip.style.cssText = 'position:fixed;z-index:10000;pointer-events:none;' +
            'padding:3px 7px;border-radius:3px;font:11px sans-serif;white-space:nowrap;' +
            'background:rgba(30,30,30,0.88);color:#ffffff;';
        document.body.appendChild(window.coypuTooltip);
    }}

    var parts = [];
    // Element identity first, its number and its type read as one caption
    var identity = [];
    if (point.length > 6 && point[6]) {{ identity.push(point[6]); }}
    if (point.length > 7 && point[7]) {{ identity.push(point[7]); }}
    if (identity.length) {{
        parts.push(window.coypuLabels.type + ' ' + identity.join(' \u00b7 '));
    }}

    if (point.length > 4 && point[4] !== null && isFinite(point[4])) {{
        var radiusText = point[4].toFixed(0);
        if (point.length > 5 && point[5] !== null && isFinite(point[5]) &&
            Math.abs(point[5] - point[4]) > 0.5) {{
            radiusText += ' \u2192 ' + point[5].toFixed(0);
        }}
        parts.push(window.coypuLabels.radius + ' ' + radiusText + ' m');
    }} else if (point.length > 7 && point[7]) {{
        // A straight has no centre of curvature, saying so beats leaving the field out
        parts.push(window.coypuLabels.radius + ' \u221e');
    }}
    if (point.length > 8 && point[8] !== null) {{
        parts.push(window.coypuLabels.length + ' ' + point[8].toFixed(1) + ' m');
    }}
    // Stationing range of the whole element, with the hovered chainage after it
    if (point.length > 10 && point[9] !== null && point[10] !== null) {{
        parts.push(window.coypuFormatChainage(point[9]) + ' \u2013 ' + window.coypuFormatChainage(point[10]));
    }}
    parts.push(window.coypuLabels.chainage + ' ' + window.coypuFormatChainage(point[0]));
    if (point.length > 3 && point[3] !== null && Math.abs(point[3]) >= 1.0) {{
        parts.push(window.coypuLabels.slew + ': ' + point[3].toFixed(0) + ' mm');
    }}

    window.coypuTooltip.textContent = parts.join(' | ');
    window.coypuTooltip.style.display = 'block';
    window.coypuTooltip.style.left = (event.originalEvent.clientX + 14) + 'px';
    window.coypuTooltip.style.top = (event.originalEvent.clientY + 14) + 'px';
}};

window.setTrackCursor = function (lat, lon) {{
    var mapObject = {mapName};
    if (!mapObject) {{ return; }}
    if (window.coypuCursorMarker === null) {{
        window.coypuCursorMarker = L.circleMarker([lat, lon], {{
            radius: 7, color: '#2f6fb5', weight: 3,
            fillColor: '#ffffff', fillOpacity: 1.0
        }}).addTo(mapObject);
    }} else {{
        window.coypuCursorMarker.setLatLng([lat, lon]);
    }}
}};

// Report the chainage of the alignment point nearest to the mouse back to Qt
window.coypuReportNearest = function (event) {{
    if (window.coypuMeasureMode) {{ return; }}
    if (window.coypuPoints.length === 0) {{ return; }}
    var now = Date.now();
    if (now - window.coypuLastSent < 50) {{ return; }}
    window.coypuLastSent = now;

    var latlng = event.latlng;
    var scale = Math.cos(latlng.lat * Math.PI / 180.0);
    var bestIndex = -1;
    var bestDistance = Infinity;
    for (var i = 0; i < window.coypuPoints.length; i++) {{
        var dLat = window.coypuPoints[i][1] - latlng.lat;
        var dLon = (window.coypuPoints[i][2] - latlng.lng) * scale;
        var distance = dLat * dLat + dLon * dLon;
        if (distance < bestDistance) {{ bestDistance = distance; bestIndex = i; }}
    }}
    if (bestIndex < 0) {{ return; }}

    if (window.coypuBridge) {{
        window.coypuBridge.reportChainage(window.coypuPoints[bestIndex][0]);
    }}
    if (window.coypuDetailsEnabled) {{
        window.coypuUpdateTooltip(event, window.coypuPoints[bestIndex]);
    }} else {{
        window.coypuHideTooltip();
    }}
}};

// Report the camera back to Qt so the viewport survives a rebuild, a save and a reload
window.coypuReportView = function () {{
    if (!window.coypuBridge) {{ return; }}
    var center = {mapName}.getCenter();
    window.coypuBridge.reportViewState(center.lat, center.lng, {mapName}.getZoom());
}};

// Frame the whole alignment without rebuilding the page
window.coypuFitBounds = function (south, west, north, east) {{
    if (![south, west, north, east].every(isFinite)) {{ return; }}
    {mapName}.fitBounds([[south, west], [north, east]], {{padding: [24, 24]}});
}};

// Step the zoom from the Qt controls, so the page carries no Leaflet zoom widget of its own
window.coypuZoomBy = function (delta) {{
    if (delta > 0) {{ {mapName}.zoomIn(delta); }} else if (delta < 0) {{ {mapName}.zoomOut(-delta); }}
}};

// Swap tile providers in place, the camera is never touched so the viewport survives untouched
window.coypuSetBasemap = function (key) {{
    var target = window.coypuLayers.basemaps[key];
    if (!target || key === window.coypuActiveBasemap) {{ return; }}
    var current = window.coypuLayers.basemaps[window.coypuActiveBasemap];
    if (current && {mapName}.hasLayer(current)) {{ {mapName}.removeLayer(current); }}
    {mapName}.addLayer(target);
    if (target.bringToBack) {{ target.bringToBack(); }}
    window.coypuActiveBasemap = key;
}};

// Opacity and visibility of the railway overlay, changed in place instead of by a full redraw
window.coypuSetRailOverlay = function (isEnabled, opacity) {{
    var overlay = window.coypuLayers.railOverlay;
    if (!overlay) {{ return; }}
    if (isEnabled) {{
        if (!{mapName}.hasLayer(overlay)) {{ {mapName}.addLayer(overlay); }}
        overlay.setOpacity(opacity);
    }} else if ({mapName}.hasLayer(overlay)) {{
        {mapName}.removeLayer(overlay);
    }}
}};

// Station markers live in one group, so showing and hiding them costs no page rebuild either
window.coypuSetStations = function (isVisible) {{
    var group = window.coypuLayers.stations;
    if (!group) {{ return; }}
    if (isVisible && !{mapName}.hasLayer(group)) {{
        {mapName}.addLayer(group);
    }} else if (!isVisible && {mapName}.hasLayer(group)) {{
        {mapName}.removeLayer(group);
    }}
}};

// Kept for backwards compatibility with a page rendered before the overlay helper existed
window.coypuSetRailOpacity = function (opacity) {{
    window.coypuSetRailOverlay(true, opacity);
}};

// Show or hide the hover inspector, the chainage readout keeps working either way
window.coypuSetElementDetails = function (isEnabled) {{
    window.coypuDetailsEnabled = !!isEnabled;
    if (!isEnabled) {{ window.coypuHideTooltip(); }}
}};

// Redraw the running measurement and report its total length back to Qt
window.coypuRenderMeasure = function () {{
    if (window.coypuMeasureLayer === null) {{
        window.coypuMeasureLayer = L.layerGroup().addTo({mapName});
    }}
    window.coypuMeasureLayer.clearLayers();
    var total = 0.0;
    for (var i = 0; i < window.coypuMeasurePoints.length; i++) {{
        L.circleMarker(window.coypuMeasurePoints[i], {{
            radius: 4, color: '#2f6fb5', weight: 2,
            fillColor: '#ffffff', fillOpacity: 1.0
        }}).addTo(window.coypuMeasureLayer);
        if (i > 0) {{
            total += {mapName}.distance(window.coypuMeasurePoints[i - 1],
                                        window.coypuMeasurePoints[i]);
        }}
    }}
    if (window.coypuMeasurePoints.length > 1) {{
        L.polyline(window.coypuMeasurePoints, {{
            color: '#2f6fb5', weight: 2, dashArray: '5,5'
        }}).addTo(window.coypuMeasureLayer);
    }}
    if (window.coypuBridge) {{ window.coypuBridge.reportMeasureDistance(total); }}
}};

// Collect one vertex per click while the measure tool is armed
window.coypuAddMeasurePoint = function (event) {{
    if (!window.coypuMeasureMode) {{ return; }}
    window.coypuMeasurePoints.push([event.latlng.lat, event.latlng.lng]);
    window.coypuRenderMeasure();
}};

// Drop every vertex and tell Qt the measurement is back to zero
window.coypuClearMeasure = function () {{
    window.coypuMeasurePoints = [];
    if (window.coypuMeasureLayer !== null) {{ window.coypuMeasureLayer.clearLayers(); }}
    if (window.coypuBridge) {{ window.coypuBridge.reportMeasureDistance(0.0); }}
}};

// Arming the tool starts a fresh measurement, disarming wipes what is on screen
window.coypuSetMeasureMode = function (isEnabled) {{
    window.coypuMeasureMode = !!isEnabled;
    window.coypuClearMeasure();
    if ({mapName} && {mapName}.getContainer) {{
        {mapName}.getContainer().style.cursor = isEnabled ? 'crosshair' : '';
    }}
}};

// Everything above is a definition, only the bindings below need the map to exist already
if (typeof {mapName} === 'undefined') {{
    console.error('coypu: leaflet map global missing, page bindings skipped');
}} else {{
    window.coypuDetailsEnabled = window.coypuDetailsInitial;
    window.coypuLayers = {layerRegistry};
    window.coypuActiveBasemap = {activeBasemap};
    {mapName}.on('mousemove', function (event) {{ window.coypuReportNearest(event); }});
    {mapName}.on('mouseout', function () {{ window.coypuHideTooltip(); }});
    {mapName}.on('click', function (event) {{ window.coypuAddMeasurePoint(event); }});
    {mapName}.on('moveend', window.coypuReportView);
    {mapName}.whenReady(function () {{ window.setTimeout(window.coypuReportView, 0); }});
}}

// The handshake is asynchronous, so the first camera report waits for the bridge to arrive
if (typeof qt !== 'undefined' && qt.webChannelTransport) {{
    new QWebChannel(qt.webChannelTransport, function (channel) {{
        window.coypuBridge = channel.objects.coypuBridge;
        if (window.coypuReportView) {{ window.coypuReportView(); }}
    }});
}}
"""


class CoypuCursorScript(MacroElement):
    """Carries the cursor script into folium's own script block."""

    # Rendering here rather than into body puts the script after the Leaflet map global exists
    _template = Template("{% macro script(this, kwargs) %}{{ this.scriptSource }}{% endmacro %}")

    def __init__(self, scriptSource):
        super().__init__()
        self.scriptSource = scriptSource


class MapControlsPanel(QFrame):
    """Floating heads up display holding every map control."""

    # Emitted with the identifier of the newly selected base map
    baseMapChanged = Signal(str)

    # Emitted with the enabled flag and the opacity fraction of the rail overlay
    railOverlayChanged = Signal(bool, float)

    # Emitted with the alignment rendering style identifier
    drawModeChanged = Signal(str)

    # Emitted when the station marker toggle is switched
    stationsToggled = Signal(bool)

    # Emitted when the user asks to frame the whole alignment
    fitTrackRequested = Signal()

    # Emitted with a positive or negative number of zoom steps
    zoomRequested = Signal(int)

    # Emitted when the click to measure tool is armed or disarmed
    measureModeChanged = Signal(bool)

    # Emitted when the hover element inspector is switched on or off
    detailsToggled = Signal(bool)

    def __init__(self, lan, parent=None):
        super().__init__(parent)

        self.lan = lan or {}
        self.setObjectName("mapControlsPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        panelLayout = QVBoxLayout(self)
        panelLayout.setContentsMargins(6, 6, 6, 6)
        panelLayout.setSpacing(4)

        # Every group heading is retranslated together, so they are tracked as one list
        self.groupLabels = []

        panelLayout.addWidget(self.makeGroupLabel("mapGroupView", "View"))

        viewRow = QWidget()
        viewLayout = QHBoxLayout(viewRow)
        viewLayout.setContentsMargins(0, 0, 0, 0)
        viewLayout.setSpacing(4)

        self.zoomInButton = QPushButton()
        self.zoomInButton.setIcon(icons.makeIcon("zoomIn"))
        self.zoomInButton.setFixedWidth(ZOOM_BUTTON_WIDTH)
        self.zoomInButton.clicked.connect(self.onZoomInClicked)
        viewLayout.addWidget(self.zoomInButton)

        self.zoomOutButton = QPushButton()
        self.zoomOutButton.setIcon(icons.makeIcon("zoomOut"))
        self.zoomOutButton.setFixedWidth(ZOOM_BUTTON_WIDTH)
        self.zoomOutButton.clicked.connect(self.onZoomOutClicked)
        viewLayout.addWidget(self.zoomOutButton)

        self.fitTrackButton = QPushButton()
        self.fitTrackButton.setIcon(icons.makeIcon("resetView"))
        self.fitTrackButton.clicked.connect(self.onFitTrackClicked)
        viewLayout.addWidget(self.fitTrackButton)

        panelLayout.addWidget(viewRow)

        panelLayout.addWidget(self.makeGroupLabel("mapGroupLayers", "Layers"))

        self.baseMapCombo = QComboBox()
        for baseMapKey, languageKey, fallbackName in BASEMAP_CHOICES:
            self.baseMapCombo.addItem(self.lan.get(languageKey, fallbackName), baseMapKey)
        self.baseMapCombo.currentIndexChanged.connect(self.onBaseMapSelected)
        panelLayout.addWidget(self.baseMapCombo)

        overlayRow = QWidget()
        overlayLayout = QHBoxLayout(overlayRow)
        overlayLayout.setContentsMargins(0, 0, 0, 0)
        overlayLayout.setSpacing(4)

        self.railOverlayButton = QPushButton()
        self.railOverlayButton.setCheckable(True)
        self.railOverlayButton.setIcon(icons.makeIcon("railway"))
        self.railOverlayButton.setProperty(SERIES_TOGGLE_PROPERTY, True)
        self.railOverlayButton.toggled.connect(self.onRailOverlayToggled)
        overlayLayout.addWidget(self.railOverlayButton)

        self.railOpacitySlider = QSlider(Qt.Orientation.Horizontal)
        self.railOpacitySlider.setRange(10, 100)
        self.railOpacitySlider.setValue(70)
        self.railOpacitySlider.setFixedWidth(70)
        self.railOpacitySlider.setEnabled(False)
        self.railOpacitySlider.sliderReleased.connect(self.onRailOpacityChanged)
        overlayLayout.addWidget(self.railOpacitySlider)

        panelLayout.addWidget(overlayRow)

        self.stationsButton = QPushButton()
        self.stationsButton.setCheckable(True)
        self.stationsButton.setChecked(True)
        self.stationsButton.setIcon(icons.makeIcon("station"))
        self.stationsButton.setProperty(SERIES_TOGGLE_PROPERTY, True)
        self.stationsButton.toggled.connect(self.stationsToggled)
        panelLayout.addWidget(self.stationsButton)

        self.alignmentStyleCombo = QComboBox()
        for drawModeKey, languageKey, fallbackName in DRAW_MODE_CHOICES:
            self.alignmentStyleCombo.addItem(self.lan.get(languageKey, fallbackName), drawModeKey)
        self.alignmentStyleCombo.currentIndexChanged.connect(self.onAlignmentStyleSelected)
        panelLayout.addWidget(self.alignmentStyleCombo)

        panelLayout.addWidget(self.makeGroupLabel("mapGroupTools", "Tools"))

        self.detailsButton = QPushButton()
        self.detailsButton.setCheckable(True)
        self.detailsButton.setChecked(True)
        self.detailsButton.setIcon(icons.makeIcon("details"))
        self.detailsButton.setProperty(SERIES_TOGGLE_PROPERTY, True)
        self.detailsButton.toggled.connect(self.detailsToggled)
        panelLayout.addWidget(self.detailsButton)

        self.measureButton = QPushButton()
        self.measureButton.setCheckable(True)
        self.measureButton.setIcon(icons.makeIcon("measure"))
        self.measureButton.setProperty(SERIES_TOGGLE_PROPERTY, True)
        self.measureButton.toggled.connect(self.onMeasureToggled)
        panelLayout.addWidget(self.measureButton)

        self.measureReadoutLabel = QLabel()
        self.measureReadoutLabel.setObjectName("mapMeasureReadout")
        self.measureReadoutLabel.setVisible(False)
        panelLayout.addWidget(self.measureReadoutLabel)

        self.currentDrawMode = DRAW_MODE_SPEED
        # Whether a CARTO key is set, without one the CARTO entries stay listed but unselectable
        self.hasCartoKey = True
        self.updateTexts(self.lan)

    # Build one heading and remember it so a language change can retranslate it
    def makeGroupLabel(self, languageKey, fallbackText):
        groupLabel = QLabel(self.lan.get(languageKey, fallbackText))
        groupLabel.setObjectName("mapGroupLabel")
        self.groupLabels.append((groupLabel, languageKey, fallbackText))
        return groupLabel

    # Report the base map the user picked from the combo box
    def onBaseMapSelected(self, index):
        self.baseMapChanged.emit(self.baseMapCombo.itemData(index))

    # Enable the opacity slider together with the rail overlay itself
    def onRailOverlayToggled(self, isChecked):
        self.railOpacitySlider.setEnabled(isChecked)
        self.railOverlayChanged.emit(isChecked, self.railOpacitySlider.value() / 100.0)

    # Report a new overlay opacity once the slider is released
    def onRailOpacityChanged(self):
        if self.railOverlayButton.isChecked():
            self.railOverlayChanged.emit(True, self.railOpacitySlider.value() / 100.0)

    # Report the alignment rendering style the user picked from the combo box
    def onAlignmentStyleSelected(self, index):
        self.currentDrawMode = self.alignmentStyleCombo.itemData(index)
        self.drawModeChanged.emit(self.currentDrawMode)

    # The clicked signal carries a checked flag the plain request signals do not want
    def onFitTrackClicked(self):
        self.fitTrackRequested.emit()

    def onZoomInClicked(self):
        self.zoomRequested.emit(1)

    def onZoomOutClicked(self):
        self.zoomRequested.emit(-1)

    # Show the running total only while the tool is actually armed
    def onMeasureToggled(self, isChecked):
        self.measureReadoutLabel.setVisible(isChecked)
        self.measureModeChanged.emit(isChecked)

    # Display the formatted measure total handed over by the map widget
    def setMeasureReadout(self, readoutText):
        template = self.lan.get("mapMeasureTotal", "Total: {distance}")
        self.measureReadoutLabel.setText(template.format(distance=readoutText))

    # Grey out the CARTO entries while no key is set, the tooltip says where to add one
    def applyCartoAvailability(self):
        disabledTip = self.lan.get("mapCartoKeyDisabledTip",
                                   "Needs a CARTO API key, add one in Map Settings")
        comboModel = self.baseMapCombo.model()
        for itemIndex, (baseMapKey, _, _) in enumerate(BASEMAP_CHOICES):
            if baseMapKey not in CARTO_BASEMAPS:
                continue
            comboItem = comboModel.item(itemIndex)
            comboItem.setEnabled(self.hasCartoKey)
            comboItem.setToolTip("" if self.hasCartoKey else disabledTip)

    # Adopt the state owned by the map widget without re-emitting signals
    def syncState(self, baseMap, drawMode, railEnabled, railOpacity, showStations,
                  showElementDetails=True, hasCartoKey=True):
        for controlWidget in (self.baseMapCombo, self.railOverlayButton,
                              self.alignmentStyleCombo, self.stationsButton,
                              self.detailsButton):
            controlWidget.blockSignals(True)

        self.hasCartoKey = bool(hasCartoKey)
        self.applyCartoAvailability()

        comboIndex = self.baseMapCombo.findData(baseMap)
        if comboIndex >= 0:
            self.baseMapCombo.setCurrentIndex(comboIndex)

        validModes = (DRAW_MODE_SINGLE, DRAW_MODE_TYPE, DRAW_MODE_SPEED)
        self.currentDrawMode = drawMode if drawMode in validModes else DRAW_MODE_SPEED
        styleIndex = self.alignmentStyleCombo.findData(self.currentDrawMode)
        if styleIndex >= 0:
            self.alignmentStyleCombo.setCurrentIndex(styleIndex)
        self.railOverlayButton.setChecked(bool(railEnabled))
        self.railOpacitySlider.setEnabled(bool(railEnabled))
        self.railOpacitySlider.setValue(int(round(railOpacity * 100)))
        self.stationsButton.setChecked(bool(showStations))
        self.detailsButton.setChecked(bool(showElementDetails))

        for controlWidget in (self.baseMapCombo, self.railOverlayButton,
                              self.alignmentStyleCombo, self.stationsButton,
                              self.detailsButton):
            controlWidget.blockSignals(False)

    # Refresh every caption after a language change
    def updateTexts(self, lan):
        self.lan = lan or {}

        for groupLabel, languageKey, fallbackText in self.groupLabels:
            groupLabel.setText(self.lan.get(languageKey, fallbackText))

        self.baseMapCombo.blockSignals(True)
        for itemIndex, (baseMapKey, languageKey, fallbackName) in enumerate(BASEMAP_CHOICES):
            self.baseMapCombo.setItemText(itemIndex, self.lan.get(languageKey, fallbackName))
        self.applyCartoAvailability()
        self.baseMapCombo.blockSignals(False)

        self.alignmentStyleCombo.blockSignals(True)
        for itemIndex, (drawModeKey, languageKey, fallbackName) in enumerate(DRAW_MODE_CHOICES):
            self.alignmentStyleCombo.setItemText(itemIndex, self.lan.get(languageKey, fallbackName))
        self.alignmentStyleCombo.blockSignals(False)

        self.baseMapCombo.setToolTip(self.lan.get("mapBasemap", "Base map"))
        self.railOverlayButton.setText(self.lan.get("mapRailOverlay", "Railways"))
        self.railOverlayButton.setToolTip(self.lan.get("mapRailOverlayTip",
                                                       "Toggle the OpenRailwayMap overlay"))
        self.railOpacitySlider.setToolTip(self.lan.get("mapRailOpacity", "Overlay transparency"))
        self.stationsButton.setText(self.lan.get("mapShowStations", "Stations"))
        self.alignmentStyleCombo.setToolTip(self.lan.get("mapAlignmentStyle", "Alignment style"))
        self.fitTrackButton.setText(self.lan.get("mapFitTrack", "Fit"))
        self.fitTrackButton.setToolTip(self.lan.get("mapFitTrackTip", "Zoom to track extent"))
        self.zoomInButton.setToolTip(self.lan.get("mapZoomInTip", "Zoom in"))
        self.zoomOutButton.setToolTip(self.lan.get("mapZoomOutTip", "Zoom out"))
        self.detailsButton.setText(self.lan.get("mapDetails", "Element details"))
        self.detailsButton.setToolTip(self.lan.get(
            "mapDetailsTip", "Show stationing, radii and length under the cursor"))
        self.measureButton.setText(self.lan.get("mapMeasure", "Measure"))
        self.measureButton.setToolTip(self.lan.get("mapMeasureTip",
                                                   "Click the map to measure a distance"))
        self.setMeasureReadout(self.lan.get("mapMeasureHint", "click the map"))

    # Rebuild the icons so they follow the active theme colours
    def applyTheme(self, isDark, tokens=None):
        self.zoomInButton.setIcon(icons.makeIcon("zoomIn"))
        self.zoomOutButton.setIcon(icons.makeIcon("zoomOut"))
        self.railOverlayButton.setIcon(icons.makeIcon("railway"))
        self.stationsButton.setIcon(icons.makeIcon("station"))
        self.fitTrackButton.setIcon(icons.makeIcon("resetView"))
        self.detailsButton.setIcon(icons.makeIcon("details"))
        self.measureButton.setIcon(icons.makeIcon("measure"))

        background = "rgba(43, 43, 43, 235)" if isDark else "rgba(255, 255, 255, 235)"
        border = tokens["border"] if tokens else "#999999"
        mutedText = tokens["mutedText"] if tokens else "#777777"
        activeBorder = tokens["accentDone"] if tokens else "#2e7d32"
        activeBackground = tokens["accentDoneBackground"] if tokens else "#e6f4e6"

        # An armed toggle carries the theme accent so its state reads without hovering it
        self.setStyleSheet(
            f"#mapControlsPanel {{ background: {background};"
            f" border: 1px solid {border}; border-radius: 4px; }}"
            f" #mapGroupLabel {{ color: {mutedText}; font-size: 10px;"
            f" text-transform: uppercase; }}"
            f" #mapMeasureReadout {{ color: {mutedText}; font-size: 10px; }}"
            f" #mapControlsPanel QPushButton:checked {{ background: {activeBackground};"
            f" border: 1px solid {activeBorder}; }}"
            f" #mapControlsPanel QPushButton:disabled {{ color: {mutedText}; }}")


class MapPageHandler(QWebEngineUrlSchemeHandler):
    """Serves the last rendered page over the private map scheme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pageBytes = b""

    # Hand the browser whatever publishPage stored last, the query string only defeats caching
    def requestStarted(self, job):
        buffer = QBuffer(job)
        buffer.setData(self.pageBytes)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(b"text/html", buffer)


class MapPage(QWebEnginePage):
    """Web page that forwards its JavaScript console to Qt."""

    # Emitted with the severity name, the message text and the source line number
    consoleMessageReceived = Signal(str, str, int)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        # The level is an enum in PySide6, int() on it raises, so the name is what travels
        self.consoleMessageReceived.emit(level.name, message, lineNumber)

    # A clicked web link, such as the tile attribution, opens in the system browser and the map stays
    def acceptNavigationRequest(self, url, navigationType, isMainFrame):
        isLinkClick = navigationType == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        if isLinkClick and url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, navigationType, isMainFrame)


class MapBridge(QObject):
    # Emitted with the chainage in kilometres reported by the page
    chainageReported = Signal(float)

    # Emitted with the map centre and zoom level after every pan or zoom
    viewStateReported = Signal(float, float, float)

    # Emitted with the running measure tool total in metres
    measureDistanceReported = Signal(float)

    # Invoked from JavaScript through the web channel on every throttled mouse move
    @Slot(float)
    def reportChainage(self, stationKm):
        self.chainageReported.emit(float(stationKm))

    # Invoked from JavaScript once the Leaflet camera settles after a pan or zoom
    @Slot(float, float, float)
    def reportViewState(self, centerLat, centerLon, zoomLevel):
        self.viewStateReported.emit(float(centerLat), float(centerLon), float(zoomLevel))

    # Invoked from JavaScript whenever the measure tool gains or loses a vertex
    @Slot(float)
    def reportMeasureDistance(self, distanceMeters):
        self.measureDistanceReported.emit(float(distanceMeters))

class MapWidget(QWidget):
    # Emitted with the chainage in kilometres when the alignment is hovered on the map
    cursorMoved = Signal(float)

    # Emitted with a translated message whenever the page itself could not do its job
    mapFailed = Signal(str)

    def __init__(self, parent=None, lan=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.mapBrowser = QWebEngineView()
        self.layout.addWidget(self.mapBrowser)
        self.currentBaseMap = "positron"
        self.drawMode = "single"
        self.speedProfile = "150"
        self.alignment = []
        self.lxml = None
        self.denseAlignment = []
        self.denseStations = []
        self.stationList = []
        self.showStations = True
        self.railOverlayEnabled = False
        self.railOverlayOpacity = 0.7
        self.isMapReady = False
        self.wasDarkTheme = False
        self.lan = lan or {}
        self.themeTokens = None
        # CARTO key from the credential vault, held in memory only and never written to a project
        self.cartoApiKey = basemap_key.loadKey()
        # Active unit system, km/h when true and m/s when false
        self.useKmh = False
        # Bounding box of everything drawn, the fallback target of the fit view control
        self.trackBounds = None
        # Bounding box of the active axis alone, what the fit view control aims at first
        self.activeTrackBounds = None
        # Set when a fit was asked for before the page was live, flushed once it finishes loading
        self.isFitPending = False
        # Scripts issued while a page was loading, keyed so a burst replays only its last value
        self.pendingScripts = {}
        # Bumped on every publish, so a superseded page's failure is not blamed on the live one
        self.loadGeneration = 0
        # Set once per page so a broken tile source cannot flood the status bar
        self.wasConsoleErrorReported = False
        # Latest measure tool total in metres, reported by the page
        self.measureDistanceMeters = 0.0
        # Armed state of the click to measure tool
        self.isMeasureMode = False
        # Whether the hover inspector shows element stationing, radii and length
        self.showElementDetails = True
        # Page globals of the layers folium emitted, so a toggle can address them from Qt
        self.layerRegistry = {"basemaps": {}, "railOverlay": None, "stations": None}
        # Live Leaflet camera, restored from a project file or reported back by the page
        self.viewCenterLat = None
        self.viewCenterLon = None
        self.viewZoom = None
        self.mapBrowser.loadFinished.connect(self.onMapLoadFinished)

        # Floating Qt controls sit above the web view and survive every page reload
        self.controlsPanel = MapControlsPanel(lan or {}, self)
        self.controlsPanel.baseMapChanged.connect(self.setBaseMap)
        self.controlsPanel.railOverlayChanged.connect(self.setRailOverlay)
        self.controlsPanel.drawModeChanged.connect(self.setDrawMode)
        self.controlsPanel.stationsToggled.connect(self.setStationsVisible)
        self.controlsPanel.fitTrackRequested.connect(self.fitToTrackExtent)
        self.controlsPanel.zoomRequested.connect(self.zoomBy)
        self.controlsPanel.measureModeChanged.connect(self.setMeasureMode)
        self.controlsPanel.detailsToggled.connect(self.setElementDetailsVisible)
        self.controlsPanel.applyTheme(False)
        self.syncControlsPanel()

        # The bridge lets the page report the chainage under the mouse back to Qt
        self.bridge = MapBridge(self)
        self.bridge.chainageReported.connect(self.cursorMoved)
        self.bridge.viewStateReported.connect(self.onViewStateReported)
        self.bridge.measureDistanceReported.connect(self.onMeasureDistanceReported)
        self.webChannel = QWebChannel(self)
        self.webChannel.registerObject("coypuBridge", self.bridge)

        # The reference is held because setPage does not take ownership of the page
        self.mapPage = MapPage(self.mapBrowser)
        self.mapPage.consoleMessageReceived.connect(self.onPageConsoleMessage)
        self.mapBrowser.setPage(self.mapPage)
        self.mapPage.setWebChannel(self.webChannel)

        # One handler serves every rendered page, so it is installed once per widget
        self.pageHandler = MapPageHandler(self)
        # The default profile is off the record, so tiles live in a memory cache only. It honours
        # the tile cache headers for the session as the OSM policy asks, and nothing stays on disk,
        # which keeps within the CARTO limit on caching and on keeping content after use ends
        mapProfile = QWebEngineProfile.defaultProfile()
        mapProfile.installUrlSchemeHandler(MAP_PAGE_SCHEME, self.pageHandler)
        # Naming the application is what keeps the railway tiles from answering 403
        mapProfile.setHttpUserAgent(MAP_TILE_USER_AGENT)

        # Coalesces the bursts of refreshes a single user action can trigger
        self.redrawTimer = QTimer(self)
        self.redrawTimer.setSingleShot(True)
        self.redrawTimer.setInterval(0)
        self.redrawTimer.timeout.connect(self.redraw)

        self.webChannelSource = self.readWebChannelSource()
        self.resetMap()

    # Read the Qt supplied qwebchannel.js so the page needs no external request
    def readWebChannelSource(self):
        resource = QFile(":/qtwebchannel/qwebchannel.js")
        if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
            return ""
        source = bytes(resource.readAll()).decode("utf-8", errors="replace")
        resource.close()
        return source

    def setDrawOptions(self, drawMode, speedProfile):
        self.drawMode = drawMode
        self.speedProfile = speedProfile
        self.syncControlsPanel()
        self.redraw()

    # Switch the alignment rendering style from the floating quick toggle
    def setDrawMode(self, drawMode):
        self.drawMode = drawMode
        self.redraw()

    # The only place a script reaches the page, so every caller shares one guard
    def runPageScript(self, script, resultHandler=None):
        if not self.isMapReady:
            return False
        if resultHandler is None:
            self.mapBrowser.page().runJavaScript(script)
        else:
            self.mapBrowser.page().runJavaScript(script, resultHandler)
        return True

    # Run now when the page is live, otherwise keep only the newest script for that intent
    def queueScript(self, intentKey, script):
        if self.runPageScript(script):
            return True
        self.pendingScripts[intentKey] = script
        return False

    # Replay whatever was asked for while the page was still loading, in the order it arrived
    def flushPendingScripts(self):
        queuedScripts = list(self.pendingScripts.values())
        self.pendingScripts.clear()
        for script in queuedScripts:
            self.runPageScript(script)

    # Run a page helper when the map is live, reporting whether the in place path was taken
    def runLayerScript(self, script):
        if not self.isMapReady or not self.layerRegistry["basemaps"]:
            return False
        return self.runPageScript(script)

    # Report a page that never loaded, unless a newer page has already superseded it
    def reportPageFailure(self, failedGeneration):
        if failedGeneration != self.loadGeneration:
            return
        self.pendingScripts.clear()
        self.mapFailed.emit(self.lan.get("mapPageFailed",
                                         "The map page could not be displayed"))

    # Surface a page side error once per page, so the cause stops being invisible
    def onPageConsoleMessage(self, levelName, message, lineNumber):
        if levelName != "ErrorMessageLevel" or self.wasConsoleErrorReported:
            return
        self.wasConsoleErrorReported = True
        template = self.lan.get("mapScriptFailed", "Map script error: {message}")
        # A failed tile request can quote its URL, which must not put the key on screen
        self.mapFailed.emit(template.format(message=basemap_key.redactKey(message)))

    # Keep the measure readout in the floating controls in step with the page
    def onMeasureDistanceReported(self, distanceMeters):
        self.measureDistanceMeters = float(distanceMeters)
        self.controlsPanel.setMeasureReadout(self.formatMeasureDistance(distanceMeters))

    # Metres below a kilometre and kilometres above it, matching how the rest of the app reads
    def formatMeasureDistance(self, distanceMeters):
        if distanceMeters < 1000.0:
            return f"{distanceMeters:.1f} m"
        return f"{distanceMeters / 1000.0:.3f} km"

    def setBaseMap(self, baseMap):
        # The dedicated rail overlay replaced the former combined orm base map
        if baseMap == "orm":
            self.railOverlayEnabled = True
            baseMap = "osm"

        self.currentBaseMap = baseMap
        self.syncControlsPanel()

        # Without a key the CARTO tiles come back watermarked, so the keyless fallback is shown
        if self.effectiveBaseMap() != baseMap and baseMap in CARTO_BASEMAPS:
            self.mapFailed.emit(self.lan.get(
                "mapCartoNeedsKey",
                "CARTO basemaps need a free API key, add it in Map Settings. "
                "Showing OpenStreetMap."))

        # Swapping tiles in the live page keeps the camera exactly where the user left it
        activeBaseMap = json.dumps(self.effectiveBaseMap())
        if self.runLayerScript(
                f"if (window.coypuSetBasemap) {{ window.coypuSetBasemap({activeBaseMap}); }}"):
            return

        self.redraw()

    # The base map actually drawn, a CARTO choice falls back to OpenStreetMap while no key is set
    def effectiveBaseMap(self):
        if self.currentBaseMap in CARTO_BASEMAPS and not self.cartoApiKey:
            return FALLBACK_BASEMAP
        return self.currentBaseMap

    # Adopt a new CARTO key, the tile URLs are baked into the page so it is rebuilt
    def setCartoApiKey(self, apiKey):
        apiKey = str(apiKey or "").strip()
        if apiKey == self.cartoApiKey:
            return
        self.cartoApiKey = apiKey
        self.syncControlsPanel()
        self.redraw()

    # Enable or disable the OpenRailwayMap overlay and set its transparency
    def setRailOverlay(self, isEnabled, opacity=None):
        self.railOverlayEnabled = bool(isEnabled)
        if opacity is not None:
            self.railOverlayOpacity = float(opacity)

        # Neither the toggle nor the opacity slider is worth a page rebuild and a tile refetch
        if self.runLayerScript(
                f"if (window.coypuSetRailOverlay) {{ window.coypuSetRailOverlay("
                f"{json.dumps(self.railOverlayEnabled)}, {self.railOverlayOpacity}); }}"):
            return

        self.redraw()

    # Show or hide the station and stop markers on the map
    def setStationsVisible(self, isVisible):
        self.showStations = bool(isVisible)

        if self.runLayerScript(
                f"if (window.coypuSetStations) {{ window.coypuSetStations("
                f"{json.dumps(self.showStations)}); }}"):
            return

        self.redraw()

    # Remember the camera the page just settled on, no redraw is needed for a pure pan or zoom
    def onViewStateReported(self, centerLat, centerLon, zoomLevel):
        self.viewCenterLat = centerLat
        self.viewCenterLon = centerLon
        self.viewZoom = zoomLevel

    # Current map camera as a (lat, lon, zoom) triple, all None while the map was never moved
    def getViewState(self):
        return self.viewCenterLat, self.viewCenterLon, self.viewZoom

    # Restore a previously saved camera, any missing component falls back to the computed view
    def setViewState(self, centerLat, centerLon, zoomLevel):
        if centerLat is None or centerLon is None or zoomLevel is None:
            return
        self.viewCenterLat = float(centerLat)
        self.viewCenterLon = float(centerLon)
        # Leaflet zoom is fractional, truncating it would walk the camera outward on every rebuild
        self.viewZoom = float(zoomLevel)

    # Forget the saved camera so the next draw re-frames the alignment
    def clearViewState(self):
        self.viewCenterLat = None
        self.viewCenterLon = None
        self.viewZoom = None

    # Build the folium map on the saved camera when there is one, otherwise on the computed view
    def buildMap(self, centerLat, centerLon, zoomStart):
        if self.viewCenterLat is not None and self.viewCenterLon is not None and self.viewZoom is not None:
            centerLat, centerLon, zoomStart = self.viewCenterLat, self.viewCenterLon, self.viewZoom
        # Layer identifiers belong to the page about to be built, so the old ones are dropped here
        self.resetLayerRegistry()
        builtMap = folium.Map(location=[centerLat, centerLon], zoom_start=zoomStart,
                              tiles=None, zoom_control=False)
        # With tiles=None folium drops its own zoom arguments, so Leaflet is configured directly
        builtMap.options["maxZoom"] = MAP_MAX_ZOOM
        builtMap.options["minZoom"] = MAP_MIN_ZOOM
        return builtMap

    # Frame the alignment, driven from the floating toolbar without rebuilding the page
    def fitToTrackExtent(self):
        # The active axis is what the user is working on, the dashed baseline only backs it up
        bounds = self.activeTrackBounds or self.trackBounds
        if not self.hasValidBounds(bounds):
            # Nothing to frame is worth saying, the silent no op was indistinguishable from a bug
            self.isFitPending = False
            self.mapFailed.emit(self.lan.get("mapFitNoTrack",
                                             "No alignment is loaded to zoom to"))
            return

        if not self.isMapReady:
            # Asking before the page is live is honoured once it finishes loading, not dropped
            self.isFitPending = True
            return

        south, west, north, east = (json.dumps(float(value)) for value in bounds)
        self.runPageScript(
            f"if (window.coypuFitBounds) {{ window.coypuFitBounds({south}, {west}, {north}, {east}); }}")

    # A box is only worth handing to Leaflet when it has four real numbers in it
    def hasValidBounds(self, bounds):
        if not bounds or len(bounds) != 4:
            return False
        return all(math.isfinite(float(value)) for value in bounds)

    # Step the zoom from the floating controls rather than a Leaflet widget over the page
    def zoomBy(self, delta):
        self.queueScript("zoom", f"if (window.coypuZoomBy) {{ window.coypuZoomBy({int(delta)}); }}")

    # Show or hide the hover element inspector, no rebuild is needed for either
    def setElementDetailsVisible(self, isVisible):
        self.showElementDetails = bool(isVisible)
        self.queueScript(
            "details",
            f"if (window.coypuSetElementDetails) {{ window.coypuSetElementDetails("
            f"{json.dumps(self.showElementDetails)}); }}")

    # Arm or disarm the click to measure tool inside the page
    def setMeasureMode(self, isEnabled):
        self.isMeasureMode = bool(isEnabled)
        if not self.isMeasureMode:
            self.measureDistanceMeters = 0.0
            self.controlsPanel.setMeasureReadout(self.formatMeasureDistance(0.0))
        self.queueScript(
            "measure",
            f"if (window.coypuSetMeasureMode) {{ window.coypuSetMeasureMode("
            f"{json.dumps(self.isMeasureMode)}); }}")

    # Thin a point list for drawing only, the cursor lookups keep the full resolution
    def decimateForRender(self, points):
        if len(points) <= MAX_RENDER_POINTS:
            return points
        step = (len(points) // MAX_RENDER_POINTS) + 1
        thinned = points[::step]
        # The stride can drop the final vertex, which would visibly shorten the line
        if thinned[-1] is not points[-1]:
            thinned = thinned + [points[-1]]
        return thinned

    # Bounding box of a point list, or None when there is not enough of it to frame
    def boundsOf(self, points):
        if len(points) < 2:
            return None
        latitudes = [point[0] for point in points]
        longitudes = [point[1] for point in points]
        return (min(latitudes), min(longitudes), max(latitudes), max(longitudes))

    # Both boxes are refreshed whenever the alignment is redrawn, the active one taking priority
    def rememberTrackBounds(self, allPoints, activePoints=None):
        self.trackBounds = self.boundsOf(allPoints)
        self.activeTrackBounds = self.boundsOf(activePoints if activePoints is not None else allPoints)
        self.refreshFitAvailability()

    # The greyed out control is the primary feedback, the status message only backs it up
    def refreshFitAvailability(self):
        hasExtent = self.hasValidBounds(self.activeTrackBounds or self.trackBounds)
        self.controlsPanel.fitTrackButton.setEnabled(hasExtent)

    # Follow the ribbon units toggle, the colour scale and its legend both carry a unit.
    # The caller redraws, so a unit switch never costs two page rebuilds in a row
    def setUnitSystem(self, useKmh):
        self.useKmh = bool(useKmh)

    # Store the scheduled stops so they can be placed along the alignment
    def setStations(self, stations):
        newStations = list(stations or [])
        # A stop list that did not change is not worth a page rebuild
        if newStations == self.stationList:
            return
        self.stationList = newStations
        self.scheduleRedraw()

    # Collapse a burst of refreshes in one event loop turn into a single page build
    def scheduleRedraw(self):
        self.redrawTimer.start()

    # Any render already satisfies a queued redraw, so the timer is stopped alongside it
    def cancelScheduledRedraw(self):
        self.redrawTimer.stop()

    # Redraw the alignment when there is data, otherwise show the empty map
    def redraw(self):
        if len(self.alignment) >= 2:
            self.drawAlignment(self.alignment, self.lxml)
        else:
            self.resetMap()

    # Push the current state into the floating controls without emitting signals
    def syncControlsPanel(self):
        self.controlsPanel.syncState(self.effectiveBaseMap(), self.drawMode,
                                     self.railOverlayEnabled, self.railOverlayOpacity,
                                     self.showStations, self.showElementDetails,
                                     hasCartoKey=bool(self.cartoApiKey))

    # Keep the floating controls pinned to the top left corner of the view
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.controlsPanel.adjustSize()
        self.controlsPanel.move(CONTROL_PANEL_MARGIN, CONTROL_PANEL_TOP)
        self.controlsPanel.raise_()

    # Refresh the floating control captions after a language change
    def updateTexts(self, lan):
        self.lan = lan or {}
        self.controlsPanel.updateTexts(lan)
        # Tooltip and legend captions are baked into the page, so they need a rebuild to follow
        self.redraw()

    # Restyle the floating controls when the application theme changes, and default
    # to the dark basemap the first time the app switches into dark mode, when a key allows it
    def applyTheme(self, isDark, tokens=None):
        if (isDark and not self.wasDarkTheme and self.cartoApiKey
                and self.currentBaseMap != "cartodbDark"):
            self.setBaseMap("cartodbDark")
        self.wasDarkTheme = isDark
        self.themeTokens = tokens
        self.controlsPanel.applyTheme(isDark, tokens)

    # Tile template for a base map. The CARTO key goes to the CARTO hosts only, never to a third party
    def basemapTileUrl(self, baseMapKey):
        tileUrl, attribution, nativeZoom = BASEMAP_TILE_SOURCES.get(
            baseMapKey, BASEMAP_TILE_SOURCES[FALLBACK_BASEMAP])
        if baseMapKey in CARTO_BASEMAPS and self.cartoApiKey:
            separator = "&" if "?" in tileUrl else "?"
            tileUrl = f"{tileUrl}{separator}key={quote(self.cartoApiKey, safe='')}"
        return tileUrl, attribution, nativeZoom

    # One layer object per base map, so switching provider is an addLayer and never a page rebuild
    def buildBasemapLayer(self, baseMapKey, isActive):
        if baseMapKey == "cuzk":
            return folium.WmsTileLayer(
                url="https://ags.cuzk.gov.cz/arcgis1/services/ORTOFOTO/MapServer/WMSServer",
                layers="0",
                name="ČÚZK Ortofoto",
                fmt="image/jpeg",
                transparent=False,
                attr="© ČÚZK",
                overlay=False,
                control=False,
                show=isActive
            )

        # Explicit endpoints, so the key and attribution of each provider stay under our control
        tileUrl, attribution, nativeZoom = self.basemapTileUrl(baseMapKey)
        return folium.TileLayer(
            tiles=tileUrl,
            attr=attribution,
            name=baseMapKey,
            subdomains="abcd",
            overlay=False,
            control=False,
            max_zoom=MAP_MAX_ZOOM,
            max_native_zoom=nativeZoom,
            show=isActive
        )

    def addTiles(self, m):
        # Every usable provider is emitted, only the active one is shown, so a switch stays in the
        # page. A CARTO layer without a key would only ever serve watermarked tiles, so it is left out
        activeBaseMap = self.effectiveBaseMap()
        for baseMapKey, _, _ in BASEMAP_CHOICES:
            if baseMapKey in CARTO_BASEMAPS and not self.cartoApiKey:
                continue
            isActive = baseMapKey == activeBaseMap
            layer = self.buildBasemapLayer(baseMapKey, isActive)
            layer.add_to(m)
            self.layerRegistry["basemaps"][baseMapKey] = layer.get_name()

        # The railway overlay is independent of the chosen base map
        railOverlay = folium.TileLayer(
            tiles='https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png',
            attr=RAIL_OVERLAY_ATTRIBUTION,
            name='OpenRailwayMap',
            className='coypuRailOverlay',
            subdomains='abc',
            overlay=True,
            control=False,
            transparent=True,
            opacity=self.railOverlayOpacity,
            max_zoom=MAP_MAX_ZOOM,
            max_native_zoom=RAIL_OVERLAY_NATIVE_ZOOM,
            show=self.railOverlayEnabled
        )
        railOverlay.add_to(m)
        self.layerRegistry["railOverlay"] = railOverlay.get_name()

    # Place one interactive marker per imported station or stop
    # Speed colour scale caption, translated and following the active unit system
    def speedLegendCaption(self):
        base = self.lan.get("mapSpeedLegendBase", "Speed")
        unit = self.lan.get("unitKmh", "km/h") if self.useKmh else self.lan.get("unitMs", "m/s")
        return f"{base} [{unit}]"

    def addStationMarkers(self, m):
        if not self.stationList or len(self.denseAlignment) < 2:
            return

        # One group for every marker, so the visibility toggle never costs a page rebuild
        stationGroup = folium.FeatureGroup(name="coypuStations", overlay=True, control=False,
                                           show=self.showStations)
        for stationKm, stationName in self.stationList:
            position = self.interpolatePosition(stationKm)
            if position is None:
                continue

            latitude, longitude = position
            caption = stationName or f"{float(stationKm):.3f} km"
            folium.CircleMarker(
                [latitude, longitude], radius=6, color="#1a3d7c", weight=2,
                fill=True, fill_color="#ffffff", fill_opacity=1.0,
                tooltip=f"{caption} ({float(stationKm):.3f} km)",
                popup=caption).add_to(stationGroup)

        stationGroup.add_to(m)
        self.layerRegistry["stations"] = stationGroup.get_name()

    def resetMap(self):
        # Nothing is drawn, so a box left over from a previous alignment must not survive
        self.trackBounds = None
        self.activeTrackBounds = None
        # A fit queued against the previous alignment must not fire against this page
        self.isFitPending = False
        self.refreshFitAvailability()
        m = self.buildMap(49.8, 15.5, 7)
        self.addTiles(m)
        self.renderMap(m)

    def drawAlignment(self, alignment, lxml=None):
        self.alignment = alignment
        self.lxml = lxml
        self.denseAlignment = (lxml or {}).get("denseAlignment") or []

        # The chainage column is cached because the cursor lookup runs on every mouse move
        self.denseStations = [point[0] for point in self.denseAlignment]

        if len(alignment) < 2:
            self.resetMap()
            return

        # The argument is always the active axis, the imported one survives only for comparison
        baselineAlignment = (lxml or {}).get("alignmentCoordinatesBaseline") or []
        activePoints = [pt for segmentData in alignment for pt in segmentData[0]]
        allPoints = activePoints + [pt for segmentData in baselineAlignment for pt in segmentData[0]]
        if not allPoints:
            self.resetMap()
            return

        self.rememberTrackBounds(allPoints, activePoints)
        lats = [pt[0] for pt in allPoints]
        lons = [pt[1] for pt in allPoints]
        centerLat = (min(lats) + max(lats)) / 2
        centerLon = (min(lons) + max(lons)) / 2
        m = self.buildMap(centerLat, centerLon, 11)
        self.addTiles(m)

        # The dashed baseline goes down first so the styled active axis always reads on top
        if baselineAlignment:
            self.drawBaselineOverlay(m, baselineAlignment)
            self.drawSlewIndicators(m, lxml or {})

        self.drawStyledAlignment(m, alignment, lxml)

        self.addStationMarkers(m)
        self.renderMap(m)

    # The active axis keeps every rendering style, whether or not it has been optimized
    def drawStyledAlignment(self, m, alignment, lxml):
        if self.drawMode == DRAW_MODE_TYPE:
            typeColors = {"Line": "blue", "Spiral": "orange", "Curve": "purple"}
            for segmentCoords, segmentType in alignment:
                folium.PolyLine(segmentCoords, color=typeColors.get(segmentType, "gray"),
                                weight=3, opacity=1, tooltip=segmentType).add_to(m)
            return

        if self.drawMode == DRAW_MODE_SPEED and lxml:
            self.drawSpeedColoredAlignment(m, lxml)
            return

        allCoords = [segmentData[0] for segmentData in alignment]
        folium.PolyLine(allCoords, color="red", weight=3, opacity=1,
                        tooltip=self.lan.get("mapNewAlignment", "Alignment")).add_to(m)

    # The imported axis, a subtle dashed guide the active one is compared against
    def drawBaselineOverlay(self, m, baselineAlignment):
        baselineCoords = [segmentData[0] for segmentData in baselineAlignment]
        folium.PolyLine(baselineCoords, color=BASELINE_ALIGNMENT_COLOR, weight=2,
                        opacity=BASELINE_ALIGNMENT_OPACITY, dash_array=BASELINE_ALIGNMENT_DASH,
                        tooltip=self.lan.get("mapBaselineAlignment", "Baseline alignment")).add_to(m)

    # Heat line over every stretch whose lateral shift clears the visibility threshold
    def drawSlewIndicators(self, m, lxml):
        denseOptimized = lxml.get("denseAlignment") or []
        stations = lxml.get("slewProfileStationKm")
        offsets = lxml.get("slewProfileOffsetMm")
        if len(denseOptimized) < 2 or stations is None or offsets is None or len(stations) < 2:
            return

        stations = np.asarray(stations, dtype=float)
        offsets = np.asarray(offsets, dtype=float)
        order = np.argsort(stations)
        stations, offsets = stations[order], offsets[order]

        peakMm = float(np.max(np.abs(offsets)))
        if peakMm <= SLEW_VISIBLE_THRESHOLD_MM:
            return

        colorMap = bcm.LinearColormap(
            ['#ffd166', '#ef7d3b', '#c1121f'],
            vmin=SLEW_VISIBLE_THRESHOLD_MM, vmax=peakMm,
            caption=self.lan.get("mapSlewLegend", "Lateral slew [mm]"))
        colorMap.add_to(m)

        # Contiguous runs are drawn one polyline at a time so unshifted stretches stay clean
        runCoords = []
        runPeakMm = 0.0
        for point in self.decimateForRender(denseOptimized):
            slewMm = abs(float(np.interp(point[0], stations, offsets)))
            if slewMm > SLEW_VISIBLE_THRESHOLD_MM:
                runCoords.append((point[1], point[2]))
                runPeakMm = max(runPeakMm, slewMm)
            elif runCoords:
                self.addSlewRun(m, runCoords, runPeakMm, colorMap)
                runCoords, runPeakMm = [], 0.0
        self.addSlewRun(m, runCoords, runPeakMm, colorMap)

    def addSlewRun(self, m, runCoords, runPeakMm, colorMap):
        if len(runCoords) < 2:
            return
        tooltip = f"{self.lan.get('mapSlewSection', 'Slew section')}: {runPeakMm:.0f} mm"
        folium.PolyLine(runCoords, color=colorMap(runPeakMm), weight=SLEW_INDICATOR_WEIGHT,
                        opacity=SLEW_INDICATOR_OPACITY, tooltip=tooltip).add_to(m)

    def drawSpeedColoredAlignment(self, m, lxml):
        denseAlignment = lxml.get("denseAlignment")
        if not denseAlignment or len(denseAlignment) < 2:
            return

        # One svg path per segment, so the drawn copy is capped even though the data is not
        denseAlignment = self.decimateForRender(list(denseAlignment))

        # Resolve data keys — TTP uses its own stored arrays
        if self.speedProfile == "TTP":
            speedKey   = "speedLimitsTTP"
            stationKey = "stationSpeedTTP"
        else:
            speedKey   = f"speedLimits{self.speedProfile}"
            stationKey = f"stationSpeed{self.speedProfile}"

        speeds   = lxml.get(speedKey)
        stations = lxml.get(stationKey)

        missing = (speeds is None or stations is None or
                    (hasattr(speeds, '__len__') and len(speeds) == 0))
        if missing:
            allCoords = [seg[0] for seg in self.alignment]
            folium.PolyLine(allCoords, color="gray", weight=2.5, opacity=0.6,
                            tooltip="Speed data not yet calculated").add_to(m)
            return

        speeds   = np.asarray(speeds,   dtype=float)
        stations = np.asarray(stations, dtype=float)

        # Drop NaN / zero entries (geometry engine initialises arrays to 0)
        valid = np.isfinite(speeds) & np.isfinite(stations) & (speeds > 0)
        speeds, stations = speeds[valid], stations[valid]

        # Stored limits are km/h, the scale and its legend show whichever unit is active
        if not self.useKmh:
            speeds = speeds / 3.6
        if len(speeds) == 0:
            allCoords = [seg[0] for seg in self.alignment]
            folium.PolyLine(allCoords, color="gray", weight=2.5, opacity=0.6,
                            tooltip="Speed data not yet calculated").add_to(m)
            return

        minSpd = float(np.min(speeds))
        maxSpd = float(np.max(speeds))
        if maxSpd <= minSpd:
            maxSpd = minSpd + 1.0

        # Branca colormap: red (slow) → yellow → green (fast).
        # Adding it to the map automatically renders a colour-scale legend.
        cmapBc = bcm.LinearColormap(
            ['#d73027', '#fee08b', '#1a9850'],
            vmin=minSpd,
            vmax=maxSpd,
            caption=self.speedLegendCaption(),
        )
        cmapBc.add_to(m)

        sortIdx    = np.argsort(stations)
        sortedSt   = stations[sortIdx]
        sortedSp   = speeds[sortIdx]
        n           = len(sortedSp)

        points     = [(p[1], p[2]) for p in denseAlignment]
        spdValues = []
        for i in range(len(denseAlignment) - 1):
            avg = (denseAlignment[i][0] + denseAlignment[i + 1][0]) * 0.5
            idx = int(np.clip(
                np.searchsorted(sortedSt, avg, side='right') - 1,
                0, n - 1
            ))
            spdValues.append(float(sortedSp[idx]))

        if points and spdValues:
            # An optimized overlay takes visual priority, so the speed coloured baseline steps back
            ColorLine(points, colors=spdValues, colormap=cmapBc, weight=3,
                      opacity=1.0).add_to(m)

    def renderMap(self, m):
        # Expose the JavaScript hooks that drive the crosshair in both directions
        cursorScript = CURSOR_SCRIPT_TEMPLATE.format(
            mapName=m.get_name(),
            webChannelSource=self.webChannelSource,
            lookupPoints=json.dumps(self.buildLookupPoints()),
            # Layer variables are emitted as bare identifiers, they are page globals and not strings
            layerRegistry=self.renderLayerRegistry(),
            activeBasemap=json.dumps(self.effectiveBaseMap()),
            detailsEnabled=json.dumps(self.showElementDetails),
            tooltipLabels=json.dumps({
                "slew": self.lan.get("mapSlewTooltip", "Slew"),
                "type": self.lan.get("mapTipType", "Element"),
                "radius": self.lan.get("mapTipRadius", "R"),
                "length": self.lan.get("mapTipLength", "L"),
                "chainage": self.lan.get("mapTipChainage", "at"),
            }),
        )
        CoypuCursorScript(cursorScript).add_to(m)

        # A render satisfies whatever redraw was queued, so the timer must not fire again after it
        self.cancelScheduledRedraw()
        data = io.BytesIO()
        m.save(data, close_file=False)
        self.publishPage(data.getvalue().decode())

    # The one place a rendered page reaches the browser, which is what the tests stub
    def publishPage(self, html):
        self.isMapReady = False
        self.wasConsoleErrorReported = False
        self.loadGeneration += 1
        self.pageHandler.pageBytes = html.encode("utf-8")
        # The generation in the query string keeps the browser from serving a cached page
        self.mapBrowser.load(QUrl(f"{MAP_PAGE_URL}?g={self.loadGeneration}"))

    # The registry maps a layer name onto the page global folium generated for it
    def renderLayerRegistry(self):
        basemaps = ", ".join(f"{json.dumps(key)}: {variableName}"
                             for key, variableName in self.layerRegistry["basemaps"].items())
        railOverlay = self.layerRegistry.get("railOverlay") or "null"
        stations = self.layerRegistry.get("stations") or "null"
        return f"{{basemaps: {{{basemaps}}}, railOverlay: {railOverlay}, stations: {stations}}}"

    # Layer identifiers are regenerated on every render, so the registry starts each build empty
    def resetLayerRegistry(self):
        self.layerRegistry = {"basemaps": {}, "railOverlay": None, "stations": None}

    # Subsample the densified alignment so the in page lookup stays responsive
    def buildLookupPoints(self):
        if len(self.denseAlignment) < 2:
            return []
        step = max(1, len(self.denseAlignment) // MAX_LOOKUP_POINTS)
        sampledPoints = self.denseAlignment[::step]

        slewByStation = self.buildSlewLookup()
        radiusByStation = self.buildRadiusLookup()
        elementByStation = self.buildElementLookup()
        lookupPoints = []
        for point in sampledPoints:
            stationKm = float(point[0])
            row = [stationKm, float(point[1]), float(point[2])]
            row.append(slewByStation(stationKm))
            row.extend(radiusByStation(stationKm))
            row.extend(elementByStation(stationKm))
            lookupPoints.append(row)
        return lookupPoints

    # Element name, type caption, length and stationing range at a chainage, for the hover inspector
    def buildElementLookup(self):
        lxml = self.lxml or {}
        stations = np.asarray(lxml.get("stationHorizontal", []), dtype=float)
        elementTypes = list(lxml.get("geometryType", []))
        emptyRow = [None, None, None, None, None]
        # An odd length would leave the last element without an end station to read
        if stations.size < 2 or stations.size % 2 or len(elementTypes) != stations.size:
            return lambda stationKm: list(emptyRow)

        typeCaptions = {"Line": self.lan.get("elemLine", "Straight"),
                        "Spiral": self.lan.get("elemSpiral", "Spiral"),
                        "Curve": self.lan.get("elemCurve", "Curve")}

        # Elements are stored as start and end pairs, so one element spans two array entries
        starts = stations[::2]
        ends = stations[1::2]
        captions = [typeCaptions.get(str(elementTypes[index * 2]), str(elementTypes[index * 2]))
                    for index in range(len(starts))]
        names = self.elementNames(len(starts))

        def lookup(stationKm):
            index = int(np.searchsorted(starts, stationKm, side="right") - 1)
            if index < 0 or index >= len(starts):
                return list(emptyRow)
            return [names[index], captions[index],
                    float((ends[index] - starts[index]) * 1000.0),
                    float(starts[index]), float(ends[index])]

        return lookup

    # LandXML names the alignment but not its geometry elements, so the position is the name
    def elementNames(self, elementCount):
        label = self.lan.get("mapTipElementNumber", "#{index}")
        return [label.format(index=index + 1) for index in range(elementCount)]

    # Interpolator over the optimizer's slew profile, returns None wherever no profile exists
    def buildSlewLookup(self):
        lxml = self.lxml or {}
        stations = lxml.get("slewProfileStationKm")
        offsets = lxml.get("slewProfileOffsetMm")
        if stations is None or offsets is None or len(stations) < 2:
            return lambda stationKm: None

        stations = np.asarray(stations, dtype=float)
        offsets = np.asarray(offsets, dtype=float)
        order = np.argsort(stations)
        stations, offsets = stations[order], offsets[order]

        def lookup(stationKm):
            if stationKm < stations[0] or stationKm > stations[-1]:
                return None
            return round(float(np.interp(stationKm, stations, offsets)), 1)
        return lookup

    # Original and optimized radius of the curve group covering a chainage, None outside every group
    def buildRadiusLookup(self):
        summary = (self.lxml or {}).get("optimizationSummary") or {}
        groupRanges = [(g["startKm"], g["endKm"], g["radiusOldM"], g["radiusNewM"])
                       for g in summary.get("groups", [])
                       if g.get("radiusOldM") is not None and g.get("radiusNewM") is not None]
        if not groupRanges:
            return lambda stationKm: [None, None]

        def lookup(stationKm):
            for startKm, endKm, radiusOld, radiusNew in groupRanges:
                if startKm <= stationKm <= endKm:
                    return [round(float(radiusOld), 1), round(float(radiusNew), 1)]
            return [None, None]
        return lookup

    # The JavaScript hook only exists once the page has finished loading
    def onMapLoadFinished(self, isOk):
        self.isMapReady = bool(isOk)

        if not self.isMapReady:
            # A superseded page reports a failure too, so the complaint waits for a newer generation
            failedGeneration = self.loadGeneration
            QTimer.singleShot(0, lambda: self.reportPageFailure(failedGeneration))
            return

        # Anything asked for while the page was loading is replayed rather than dropped
        self.flushPendingScripts()

        # A fit asked for while the page was still loading is honoured now rather than lost
        if self.isFitPending:
            self.isFitPending = False
            self.fitToTrackExtent()

    # Move the map cursor marker to the position matching a chainage in kilometres
    def setCursorStation(self, stationKm):
        if len(self.denseAlignment) < 2:
            return

        position = self.interpolatePosition(stationKm)
        if position is None:
            return

        latitude, longitude = position
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            return

        # Keyed so a burst of mouse moves during a page load collapses to the last one
        self.queueScript(
            "cursor",
            f"if (window.setTrackCursor) {{ window.setTrackCursor("
            f"{json.dumps(float(latitude))}, {json.dumps(float(longitude))}); }}")

    # Linear interpolation of latitude and longitude along the densified alignment
    def interpolatePosition(self, stationKm):
        stations = self.denseStations
        if not stations:
            return None

        # denseAlignment stores chainage in kilometres like the rest of the geometry
        target = float(stationKm)
        if target <= stations[0]:
            return self.denseAlignment[0][1], self.denseAlignment[0][2]
        if target >= stations[-1]:
            return self.denseAlignment[-1][1], self.denseAlignment[-1][2]

        index = int(np.searchsorted(stations, target, side='right')) - 1
        index = max(0, min(index, len(self.denseAlignment) - 2))

        startStation, startLat, startLon = self.denseAlignment[index]
        endStation, endLat, endLon = self.denseAlignment[index + 1]
        span = endStation - startStation
        ratio = 0.0 if span == 0 else (target - startStation) / span

        return startLat + ratio * (endLat - startLat), startLon + ratio * (endLon - startLon)

    def getBearing(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dLon = lon2 - lon1
        y = math.sin(dLon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon)
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360

    # def _draw_stationing(self, m, lxml):
    #     keyLat = lxml.get("keyLat", [])
    #     keyLon = lxml.get("keyLon", [])
    #     keyTypes = lxml.get("keyTypes", [])
    #     keyStations = lxml.get("keyStations", [])
    #     denseAlignment = lxml.get("denseAlignment", [])

    #     if len(keyLat) == 0 or len(denseAlignment) < 2:
    #         return

    #     # Klíčové body ZÚ, KÚ, ZO, KO, ZP, KP
    #     for i in range(len(keyLat)):
    #         lat, lon = keyLat[i], keyLon[i]
    #         ktype = keyTypes[i]
    #         sta = keyStations[i]
            
    #         closest_idx = 0
    #         min_dist = float('inf')
    #         for j, p in enumerate(denseAlignment):
    #             dist = (p[1]-lat)**2 + (p[2]-lon)**2
    #             if dist < min_dist:
    #                 min_dist = dist; closest_idx = j
            
    #         if closest_idx < len(denseAlignment) - 1:
    #             p1 = denseAlignment[closest_idx]; p2 = denseAlignment[closest_idx + 1]
    #         else:
    #             p1 = denseAlignment[closest_idx - 1]; p2 = denseAlignment[closest_idx]
                
    #         bearing = self._get_bearing(p1[1], p1[2], p2[1], p2[2])
            
    #         if ktype in ["ZÚ", "KÚ"]:
    #             angle = bearing - 90
    #             transform_style = f"transform: rotate({angle % 360}deg) translate(15px, -10px);"
    #         else:
    #             angle = bearing
    #             transform_style = f"transform: rotate({angle % 360}deg) translate(5px, -15px);"

    #         angle = angle % 360
    #         if 90 < angle <= 270:
    #             angle += 180
    #             if ktype in ["ZÚ", "KÚ"]: transform_style = f"transform: rotate({angle % 360}deg) translate(-15px, 10px);"
    #             else: transform_style = f"transform: rotate({angle % 360}deg) translate(-5px, 15px);"
            
    #         html = f'''
    #             <div style="font-size: 10pt; color: black; font-weight: bold; text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff; {transform_style} white-space: nowrap;">
    #                 {ktype} {sta:.3f}
    #             </div>
    #         '''
    #         folium.Marker([lat, lon], icon=DivIcon(icon_size=(150, 36), icon_anchor=(0, 0), html=html)).add_to(m)
            
    #         if ktype in ["ZÚ", "KÚ"]:
    #             tick_len = 0.0003
    #             tick_ang = math.radians(bearing - 90)
    #             folium.PolyLine([(lat + tick_len * math.cos(tick_ang), lon + tick_len * math.sin(tick_ang)), 
    #                              (lat - tick_len * math.cos(tick_ang), lon - tick_len * math.sin(tick_ang))], 
    #                             color="black", weight=2).add_to(m)
    #         else:
    #             folium.CircleMarker([lat, lon], radius=3, color='black', fill=True, fill_color='black').add_to(m)

    #     # Kilometrovníky
    #     min_sta = math.ceil(denseAlignment[0][0])
    #     max_sta = math.floor(denseAlignment[-1][0])
        
    #     for km in range(min_sta, max_sta + 1):
    #         p1 = None; p2 = None
    #         for i in range(len(denseAlignment) - 1):
    #             if denseAlignment[i][0] <= km <= denseAlignment[i+1][0]:
    #                 p1 = denseAlignment[i]; p2 = denseAlignment[i+1]
    #                 break
    #         if not p1 or not p2: continue
                
    #         s1, lat1, lon1 = p1
    #         s2, lat2, lon2 = p2
    #         ratio = 0 if s2 == s1 else (km - s1) / (s2 - s1)
                
    #         lat = lat1 + ratio * (lat2 - lat1)
    #         lon = lon1 + ratio * (lon2 - lon1)
            
    #         bearing = self._get_bearing(lat1, lon1, lat2, lon2)
    #         angle = bearing % 360
    #         transform_style = f"transform: rotate({angle}deg) translate(0px, -20px);"
            
    #         if 90 < angle <= 270:
    #             angle += 180
    #             transform_style = f"transform: rotate({angle % 360}deg) translate(0px, 20px);"
            
    #         html = f'''
    #             <div style="font-size: 11pt; color: blue; font-weight: bold; text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff; {transform_style} white-space: nowrap;">
    #                 {km}
    #             </div>
    #         '''
    #         folium.Marker([lat, lon], icon=DivIcon(icon_size=(100, 20), icon_anchor=(0, 0), html=html)).add_to(m)
    #         folium.CircleMarker([lat, lon], radius=4, color='blue', fill=True, fill_color='white').add_to(m)