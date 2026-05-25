# dxbridge.py (ver5.9 - Modular refactored version)
# DXSpider → WaveLog → Flex Spots Bridge
# @2025 Oliver Bross OM0RX
#
# This is the main entry point. The application has been split into modules:
# - config_manager.py: Configuration file management
# - utils.py: Utility functions (logging, band detection, mode inference)
# - ui_dialogs.py: Dialog windows (About, Config, FlexInfo)
# - config_manager.py: Config read/write utilities
# - classifier.py: QSO classification logic
# - ui_components.py: Reusable UI components (MultiCheckDropdown)
# - cty_resolvers.py: Country/DXCC resolution (CtyResolver, CtyDatResolver, CtyHybridResolver)
# - flex_radio.py: FlexRadio SmartSDR API client (FlexSpots, FlexCtl)
# - spot_ui.py: Main spot display UI
# - bridge_runtime.py: Main runtime loop and async functions

import asyncio
import sys

try:
    import mysql.connector as mysql
except ImportError:
    print("Missing dependency: mysql-connector-python (pip install mysql-connector-python)")
    sys.exit(1)

# Initialize logging as early as possible
from utils import setup_flex_logging
setup_flex_logging()

# Import and run the main function from bridge_runtime
from bridge_runtime import main, DX_RE

# Re-export FlexCtl for backward compatibility with backend/main.py
from flex_radio import FlexCtl, FlexSpots

# Re-export other commonly used items
__all__ = ['main', 'DX_RE', 'FlexCtl', 'FlexSpots']

if __name__=="__main__":
    try: 
        asyncio.run(main())
    except KeyboardInterrupt: 
        pass
