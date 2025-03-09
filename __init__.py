# Copyright (c) 2024 Emanuel Lönnberg.
# This tool is released under the terms of the LGPLv3 or higher.

from . import MySupportImprover

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("mysupportimprover")

def getMetaData():
    return {
        "tool": {
            "name": i18n_catalog.i18nc("@label", "My Support Improver"),
            "description": i18n_catalog.i18nc("@info:tooltip", "Create a volume where support settings can be changed to affect support generation."),
            "icon": "down.svg",
            "tool_panel": "qt6/SupportImprover.qml",
            "weight": 4,
            "button_style": "tool_button",
            "visible": True,
            "version": 2
        }
    }

def register(app):
    # Create the tool instance
    tool = MySupportImprover.MySupportImprover()
    return { "tool": tool }
