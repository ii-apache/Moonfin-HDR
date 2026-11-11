"""org.freedesktop.Notifications server (Qt). Without the Plasma shell
nothing shows desktop notifications, so the home screen does: they appear as
banners on top of whatever is on screen."""
from PySide6.QtCore import ClassInfo, QObject, Signal, Slot


@ClassInfo({"D-Bus Interface": "org.freedesktop.Notifications"})
class NotificationServer(QObject):
    banner = Signal(str, str, str)  # title, body, icon
    NotificationClosed = Signal("uint", "uint")
    ActionInvoked = Signal("uint", str)

    def __init__(self):
        super().__init__()
        self._next = 1

    @Slot(result="QStringList")
    def GetCapabilities(self):
        return ["body"]

    @Slot(str, "uint", str, str, str, "QStringList", "QVariantMap", int, result="uint")
    def Notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, timeout):
        nid = replaces_id or self._next
        if not replaces_id:
            self._next += 1
        self.banner.emit(summary or app_name, body, app_icon)
        return nid

    @Slot("uint")
    def CloseNotification(self, nid):
        pass

    @Slot(result=str)
    def GetServerInformation(self):
        # Spec returns (name, vendor, version, spec_version); one string is
        # what PySide can export, and callers only log it.
        return "LSBox Home"
