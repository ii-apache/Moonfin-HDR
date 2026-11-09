// Two images that cross-fade when the source changes.
import QtQuick

Item {
    id: root
    property string source: ""
    property bool showA: false
    clip: true

    onSourceChanged: {
        if (showA) { b.source = source; showA = false }
        else { a.source = source; showA = true }
    }
    Image {
        id: a
        anchors.fill: parent
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize.width: 1920
        opacity: root.showA && root.source !== "" && status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 450 } }
    }
    Image {
        id: b
        anchors.fill: parent
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize.width: 1920
        opacity: !root.showA && root.source !== "" && status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 450 } }
    }
}
