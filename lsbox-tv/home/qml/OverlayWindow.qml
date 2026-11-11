// A small see-through window that sits above apps (KWin keeps it on top,
// top right, and never gives it focus) so banners and the volume bar show
// while you watch. Only mapped while it has something to show.
import QtQuick
import QtQuick.Window

Window {
    id: ow
    title: "LSBox Overlay"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    transientParent: null
    width: 700 * win.u
    height: 360 * win.u
    property alias toasts: t
    visible: !home.demo && t.busy
    Toasts { id: t; anchors.fill: parent; active: !home.launcherActive && !home.demo }
}
