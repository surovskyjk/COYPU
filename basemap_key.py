# CARTO basemap key storage, kept in the operating system credential vault and never in a project
import os
import re

try:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError
except ImportError:
    keyring = None
    KeyringError = PasswordDeleteError = Exception

# Credential vault entry the key is stored under, Windows Credential Manager on Windows
KEYRING_SERVICE = "COYPU"
KEYRING_ENTRY = "cartoBasemapKey"

# Fallback for development and scripted runs, read only when the vault holds nothing
ENVIRONMENT_VARIABLE = "COYPU_MAP_API_KEY"

# Settings entry older versions wrote the key to, which also landed in every saved project
LEGACY_SETTINGS_KEY = "mapBasemapApiKey"

# Where a user without a key of their own can ask the author for one
AUTHOR_CONTACT_URL = "https://github.com/surovskyjk"

# Where anyone can register a free key of their own
CARTO_KEY_SIGNUP_URL = "https://carto.com/basemaps/apikey/"

# Value of a key query parameter in any URL, masked before a message reaches the interface
KEY_PARAMETER_PATTERN = re.compile(r"([?&]key=)[^&\s\"'#]+")


# Stored key first, the environment second, an empty string when neither has one
def loadKey():
    storedKey = ""
    if keyring is not None:
        try:
            storedKey = keyring.get_password(KEYRING_SERVICE, KEYRING_ENTRY) or ""
        except KeyringError:
            storedKey = ""
    return (storedKey or os.environ.get(ENVIRONMENT_VARIABLE, "")).strip()


# Keep the key in the vault, reporting whether it actually got there
def saveKey(apiKey):
    if keyring is None:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_ENTRY, apiKey)
    except KeyringError:
        return False
    return True


# Remove the key from the vault, a key that was never stored counts as removed
def deleteKey():
    if keyring is None:
        return False
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_ENTRY)
    except PasswordDeleteError:
        return True
    except KeyringError:
        return False
    return True


# Mask every key query value in a text, so an error message never shows the key itself
def redactKey(text):
    return KEY_PARAMETER_PATTERN.sub(r"\1***", str(text))
