# Windows GUI station selection

Open Agent Settings > Connections and security and click **Refresh** beside
**GUI station name**. The dropdown lists GUI clients currently connected to the
configured FLEX host and TCP port, including Maestro, SmartSDR and AetherSDR.
Choose a name, then save and restart the Agent to apply it. A name can also be
entered manually. Refresh preserves the current selection until you choose.

Discovery runs in a hidden background process and sends only `sub client all`
on a temporary FLEX connection. It does not bind to a GUI, start a controller,
change settings, or send station/RF commands. It works with the Agent stopped.
Empty results and connection failures are shown in the Settings window.

Cancel and Escape close Settings without saving. Discovery is stopped if the
window closes. Cancel explicitly closes this nonmodal application window;
setting a dialog result alone did not close it.

Validation on Windows: deployed Agent/discovery/tray gate 76 passed; original
repository discovery/tray gate 25 passed; Python lint and PowerShell parsing
passed. The application `-PickerSmokeTest` exercises Refresh, dropdown results,
and Cancel in the native Windows message loop without saving configuration.
Live receive-only discovery also returned the connected AetherSDR GUI client.

The deployed mirror is `C:\Projects\OM0RX-xCat\WindowsAgent`; its matching
settings script is under `scripts`, while this repository uses
`scripts/remote_agent`. Reopen Settings to load the update; an Agent restart
is needed only when applying a newly saved station selection.
