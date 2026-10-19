# Builds and applies one portable JSON snapshot of layout, shortcuts, theme, units and default vehicles
import base64

from PySide6.QtCore import QByteArray

import project_file
import theme_manager

PRESET_VERSION = 1


class PresetManager:
    # Collect every currently live preference into one portable dictionary
    def buildPresetPayload(self, mainWindow):
        return {
            "presetVersion": PRESET_VERSION,
            "layoutGeometry": self.encodeBytes(mainWindow.saveGeometry()),
            "layoutState": self.encodeBytes(mainWindow.saveState()),
            "themeMode": mainWindow.themeManager.currentMode,
            "unitsKmh": mainWindow.toggleUnitsAction.isChecked(),
            "commands": list(mainWindow.shortcutManager.commands),
            "floatingCommandInputEnabled": mainWindow.shortcutManager.floatingInputEnabled,
            "defaultVehiclePaths": self.collectDefaultVehiclePaths(mainWindow),
        }

    def encodeBytes(self, byteData):
        return base64.b64encode(bytes(byteData)).decode("ascii")

    def decodeBytes(self, encodedText):
        return QByteArray(base64.b64decode(encodedText.encode("ascii")))

    # Selected catalog vehicle name per active vehicle slot, None for manually edited or unmatched slots
    def collectDefaultVehiclePaths(self, mainWindow):
        vehicles = mainWindow.dataStorage.get("settingsData", {}).get("vehicles", [])
        paths = []
        for vehicleData in vehicles:
            try:
                vehicleName = str(vehicleData["trainParam"][0][0]).strip()
            except (IndexError, KeyError, TypeError):
                vehicleName = ""
            catalogEntry = mainWindow.vehicleCatalog.vehicleByName(vehicleName) if vehicleName else None
            paths.append(catalogEntry.vehicleName if catalogEntry else None)
        return paths

    # Re-apply every preference from a previously exported payload
    def applyPresetPayload(self, mainWindow, payload):
        layoutGeometry = payload.get("layoutGeometry")
        if layoutGeometry:
            mainWindow.restoreGeometry(self.decodeBytes(layoutGeometry))

        layoutState = payload.get("layoutState")
        if layoutState:
            mainWindow.restoreState(self.decodeBytes(layoutState))

        themeMode = payload.get("themeMode", theme_manager.MODE_AUTO)
        if themeMode not in (theme_manager.MODE_AUTO, theme_manager.MODE_LIGHT, theme_manager.MODE_DARK):
            themeMode = theme_manager.MODE_AUTO
        for action in mainWindow.themeGroup.actions():
            action.setChecked(action.data() == themeMode)
        mainWindow.themeManager.applyTheme(themeMode)

        # setChecked emits toggled only on an actual change, which refreshes the label and every plot
        mainWindow.toggleUnitsAction.setChecked(bool(payload.get("unitsKmh", False)))

        commands = payload.get("commands")
        if commands:
            mainWindow.shortcutManager.saveCommands(
                commands, payload.get("floatingCommandInputEnabled", True))
            mainWindow.shortcutManager.applyShortcuts(mainWindow)

        self.applyDefaultVehiclePaths(mainWindow, payload.get("defaultVehiclePaths", []))
        mainWindow.rebuildVehicleReportMenus()

    # Re-select each preset's catalog vehicle into the matching settingsData vehicle slot
    def applyDefaultVehiclePaths(self, mainWindow, vehiclePaths):
        if not vehiclePaths:
            return
        settingsData = mainWindow.dataStorage.setdefault("settingsData", {})
        vehicles = settingsData.setdefault("vehicles", [])
        for index, vehicleName in enumerate(vehiclePaths):
            if not vehicleName:
                continue
            catalogVehicle = mainWindow.vehicleCatalog.vehicleByName(vehicleName)
            if catalogVehicle is None:
                continue
            while len(vehicles) <= index:
                vehicles.append({})
            vehicles[index] = catalogVehicle.toVehicleSettings(vehicles[index])
        # An imported vehicle must carry every key the newer schema added
        project_file.upgradeSettingsData(settingsData)
