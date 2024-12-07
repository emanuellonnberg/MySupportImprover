# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from . import MySupportImprover

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("cura")

def getMetaData():
    return {
        "tool": {
            "name": i18n_catalog.i18nc("@label", "My Support Improver"),
            "description": i18n_catalog.i18nc("@info:tooltip", "Create a volume where support settings can be changed to affect support generation."),
            "icon": "SupportBlocker",
            "weight": 4
        }
    }

def register(app):
    return { "tool": MySupportImprover.SupportImprover() }
