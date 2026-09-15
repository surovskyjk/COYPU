# Single source of truth for the active design speed profile shared by every profile selector
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget

from vehicle_catalog import DEFAULT_MAX_CANT_DEFICIENCY_MM

# Profile tiers offered by every synchronised selector, in display order
PROFILE_KEYS = ("TTP", "100", "130", "150", "K")

# Tier selected until the user picks another one, matching the historical speedLimitPlot default
DEFAULT_PROFILE_KEY = "150"

# Storage key pair each tier resolves to, consumed as a vehicle's speedLimitPlot
PROFILE_STORAGE_KEYS = {
    "TTP": ["stationSpeedLimits", "speedLimits"],
    "100": ["stationSpeed100", "speedLimits100"],
    "130": ["stationSpeed130", "speedLimits130"],
    "150": ["stationSpeed150", "speedLimits150"],
    "K": ["stationSpeedK", "speedLimitsK"],
}

# Translation key of each tier's caption, all of them already present in the three locales
PROFILE_LABEL_KEYS = {
    "TTP": "speed_lim_ttp",
    "100": "speed_lim_100",
    "130": "speed_lim_130",
    "150": "speed_lim_150",
    "K": "speed_lim_K",
}

# Cant deficiency ceiling each tier designs against, copied from the geometry engine's profileI switch
PROFILE_CANT_DEFICIENCY_MM = {"TTP": None, "100": 100.0, "130": 130.0, "150": 150.0, "K": 240.0}

# Per vehicle speedLimitPlot selections that opt that vehicle out of the shared tier entirely
VEHICLE_OVERRIDE_KEYS = ("manualSpeedLimits", "unlimited")

# Unit free tier names, used in messages where the full caption would read awkwardly
PROFILE_SHORT_NAMES = {"TTP": "TTP", "100": "V100", "130": "V130", "150": "V150", "K": "VK"}


# Short unit free name of one tier, suitable for inline use in a sentence
def profileShortName(profileKey):
    return PROFILE_SHORT_NAMES.get(profileKey, str(profileKey))


# Storage key pair of one tier, falling back to the default tier for an unknown key
def storageKeysFor(profileKey):
    return list(PROFILE_STORAGE_KEYS.get(profileKey, PROFILE_STORAGE_KEYS[DEFAULT_PROFILE_KEY]))


# Tier a stored speedLimitPlot pair belongs to, None for the manual and unlimited overrides
def profileKeyFromStorageKeys(speedLimitPlot):
    for profileKey, storageKeys in PROFILE_STORAGE_KEYS.items():
        if list(speedLimitPlot or []) == storageKeys:
            return profileKey
    return None


# True when a vehicle pins its own speed limits and therefore ignores the shared tier
def isVehicleOverridden(vehicleSettings):
    speedLimitPlot = (vehicleSettings or {}).get("speedLimitPlot") or []
    return bool(speedLimitPlot) and speedLimitPlot[0] in VEHICLE_OVERRIDE_KEYS


# Certified cant deficiency of one vehicle, defaulting to the conventional ceiling when unstated
def vehicleMaxCantDeficiency(vehicleSettings):
    try:
        return float((vehicleSettings or {}).get("maxCantDeficiencyMm",
                                                 DEFAULT_MAX_CANT_DEFICIENCY_MM))
    except (TypeError, ValueError):
        return DEFAULT_MAX_CANT_DEFICIENCY_MM


# True when both of a tier's storage arrays carry usable data
def hasProfileData(dataStorage, profileKey):
    for storageKey in storageKeysFor(profileKey):
        values = (dataStorage or {}).get(storageKey)
        if values is None or len(values) == 0:
            return False
    return True


# A tier is permitted when it is the universally exempt TTP or sits at or below the vehicle's ceiling
def isProfilePermitted(profileKey, vehicleSettings):
    tierCeilingMm = PROFILE_CANT_DEFICIENCY_MM.get(profileKey)
    # TTP is the published line speed, so any train may drive it whatever its catalog certifies
    if tierCeilingMm is None:
        return True
    # A vehicle running its own manual or unlimited profile is never gated by a tier's ceiling
    if isVehicleOverridden(vehicleSettings):
        return True
    return vehicleMaxCantDeficiency(vehicleSettings) >= tierCeilingMm


# Vehicle settings dictionaries of the current project, always at least one entry
def vehicleSettingsList(dataStorage):
    vehicles = (dataStorage or {}).get("settingsData", {}).get("vehicles") or []
    return list(vehicles) if vehicles else [{}]


# Every vehicle that is not certified for one tier, reported by its one based number
def blockingVehicleNumbers(profileKey, vehicles):
    return [index + 1 for index, vehicleSettings in enumerate(vehicles)
            if not isProfilePermitted(profileKey, vehicleSettings)]


# Tiers that both carry data and are certified for at least one configured vehicle
def permittedProfileKeys(dataStorage, vehicles):
    permitted = []
    for profileKey in PROFILE_KEYS:
        if not hasProfileData(dataStorage, profileKey):
            continue
        if any(isProfilePermitted(profileKey, vehicleSettings) for vehicleSettings in vehicles):
            permitted.append(profileKey)
    return permitted


# Enable only the permitted tiers of one selector and explain every blocked entry in its tooltip
def applyProfileAvailability(comboBox, permittedKeys, reasonTextByKey):
    itemModel = comboBox.model()
    if not isinstance(itemModel, QStandardItemModel):
        return
    for row in range(comboBox.count()):
        profileKey = comboBox.itemData(row)
        isPermitted = profileKey in permittedKeys
        itemModel.item(row).setEnabled(isPermitted)
        comboBox.setItemData(row, reasonTextByKey.get(profileKey, "") if not isPermitted else "",
                             Qt.ItemDataRole.ToolTipRole)


class ProfileStateManager(QObject):
    # Emitted with the new tier key whenever the shared active profile actually changes
    activeProfileChanged = Signal(str)

    # Emitted whenever the permitted tier set changes, after a TTP import, a cant run or a vehicle edit
    availableProfilesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.activeProfileKey = DEFAULT_PROFILE_KEY
        self.permittedProfileKeys = list(PROFILE_KEYS)

    # Adopt a tier, refusing anything the current data or the configured vehicles do not permit
    def setActiveProfile(self, profileKey):
        if profileKey not in PROFILE_KEYS or profileKey not in self.permittedProfileKeys:
            return False
        # Idempotence is the loop guard, an echoing selector terminates the chain after one hop
        if profileKey == self.activeProfileKey:
            return False
        self.activeProfileKey = profileKey
        self.activeProfileChanged.emit(profileKey)
        return True

    # Recompute the permitted set from the current data and vehicles, demoting a now blocked tier
    def refreshAvailability(self, dataStorage):
        vehicles = vehicleSettingsList(dataStorage)
        self.permittedProfileKeys = permittedProfileKeys(dataStorage, vehicles)
        self.availableProfilesChanged.emit()

        if self.activeProfileKey in self.permittedProfileKeys or not self.permittedProfileKeys:
            return
        # Falling back in display order puts TTP first, which is the only tier a bare import can drive
        self.activeProfileKey = self.permittedProfileKeys[0]
        self.activeProfileChanged.emit(self.activeProfileKey)

    # Storage key pair of the currently active tier, ready to be written as a speedLimitPlot
    def activeStorageKeys(self):
        return storageKeysFor(self.activeProfileKey)


class ProfileSelectorBar(QWidget):
    # Emitted with the tier key when the user picks a profile from this selector
    profileSelectionRequested = Signal(str)

    def __init__(self, lan, isCompact=False, parent=None):
        super().__init__(parent)

        self.lan = lan or {}
        self.isCompact = bool(isCompact)

        rootLayout = QHBoxLayout(self)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        rootLayout.setSpacing(4)

        self.captionLabel = QLabel()
        self.profileCombo = QComboBox()
        # An explicit model removes the dependency on whichever model QComboBox happens to default to
        self.profileCombo.setModel(QStandardItemModel(self.profileCombo))
        for profileKey in PROFILE_KEYS:
            self.profileCombo.addItem(self.profileCaption(profileKey), profileKey)
        self.profileCombo.setCurrentIndex(max(0, self.profileCombo.findData(DEFAULT_PROFILE_KEY)))
        self.profileCombo.currentIndexChanged.connect(self.onProfileSelected)

        rootLayout.addWidget(self.captionLabel)
        rootLayout.addWidget(self.profileCombo, 0 if self.isCompact else 1)
        if self.isCompact:
            self.profileCombo.setMinimumWidth(150)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        else:
            rootLayout.addStretch(1)

        self.updateTexts(self.lan)

    # Caption of one tier, falling back to the bare key when a locale is missing the entry
    def profileCaption(self, profileKey):
        labelKey = PROFILE_LABEL_KEYS.get(profileKey, profileKey)
        return self.lan.get(labelKey, profileKey)

    # The user picked a tier, the shared state decides whether it is actually allowed
    def onProfileSelected(self, index):
        profileKey = self.profileCombo.itemData(index)
        if profileKey is not None:
            self.profileSelectionRequested.emit(profileKey)

    # Mirror the shared active tier without echoing a selection back into the state manager
    def applyActiveProfile(self, profileKey):
        row = self.profileCombo.findData(profileKey)
        if row < 0:
            return
        self.profileCombo.blockSignals(True)
        self.profileCombo.setCurrentIndex(row)
        self.profileCombo.blockSignals(False)

    # Grey out and explain every tier this project or its vehicles cannot drive
    def applyAvailability(self, permittedKeys, reasonTextByKey):
        applyProfileAvailability(self.profileCombo, permittedKeys, reasonTextByKey or {})

    # Refresh the caption and every tier entry after a language change
    def updateTexts(self, lan):
        self.lan = lan or {}
        self.captionLabel.setText(self.lan.get("profileSelectorLabel", "Speed profile"))
        self.profileCombo.setToolTip(self.lan.get(
            "profileSelectorTip",
            "Design speed profile driving the simulation, the plots and the statistics"))
        for row in range(self.profileCombo.count()):
            self.profileCombo.setItemText(row, self.profileCaption(self.profileCombo.itemData(row)))

    # Follow the active theme, the caption would otherwise fall back to an unreadable palette default
    def applyTheme(self, isDark, tokens=None):
        mutedColor = (tokens or {}).get("mutedText", "#9a9a9a" if isDark else "#5a5a5a")
        self.captionLabel.setStyleSheet(f"font-size: 10px; color: {mutedColor};")
