// A picture card on the top shelf or in search results.
import QtQuick
import QtQuick.Effects

Item {
    id: card
    property var item
    property bool focused: false
    property bool showTitle: false     // title always (search) or only when focused (shelf)
    property bool dim: false
    property color textColor: theme.text
    property color subColor: theme.dim
    readonly property bool square: item && item.square === true
    width: square ? win.cardH : win.cardW
    height: win.cardH
    z: focused ? 5 : 0
    scale: focused ? 1.12 : (dim ? 0.94 : 1.0)
    Behavior on scale { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }

    Shadow { anchors.fill: art; strong: card.focused }
    Item {
        id: art
        anchors.fill: parent
        layer.enabled: true
        layer.effect: MultiEffect { maskEnabled: true; maskSource: cardMask; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }
        Rectangle { anchors.fill: parent; color: card.item && card.item.tint ? card.item.tint : "#1d2230" }
        Text {  // no picture: the title
            visible: pic.status !== Image.Ready
            anchors.centerIn: parent
            width: parent.width * 0.85
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            text: card.item ? card.item.title : ""
            color: "#ddffffff"
            font.pixelSize: 26 * win.u
            font.weight: Font.DemiBold
        }
        Image {
            id: pic
            anchors.fill: parent
            source: card.item ? (card.item.thumb || card.item.backdrop || "") : ""
            sourceSize.width: 800
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
        Rectangle {
            visible: card.item && card.item.progress > 0.01
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: parent.height * 0.5
            gradient: Gradient {
                GradientStop { position: 0; color: "#00000000" }
                GradientStop { position: 1; color: "#cc000000" }
            }
        }
        Rectangle {  // progress bar
            visible: card.item && card.item.progress > 0.01
            x: parent.width * 0.06; y: parent.height - 18 * win.u
            width: parent.width * 0.88; height: 6 * win.u; radius: 3 * win.u
            color: "#55ffffff"
            Rectangle { width: parent.width * (card.item ? card.item.progress : 0); height: parent.height; radius: parent.radius; color: "white" }
        }
        Sheen { active: card.focused }
    }
    Rectangle { id: cardMask; anchors.fill: art; radius: 14 * win.u; visible: false; layer.enabled: true; color: "black" }
    Column {
        anchors.top: parent.bottom; anchors.topMargin: 16 * win.u
        width: parent.width
        opacity: card.focused || card.showTitle ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 150 } }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: card.item ? card.item.title : ""
            color: card.textColor
            font.pixelSize: 24 * win.u
            elide: Text.ElideRight
        }
        Text {
            visible: card.showTitle && text !== ""
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: card.item ? (card.item.subtitle || "") : ""
            color: card.subColor
            font.pixelSize: 20 * win.u
            elide: Text.ElideRight
        }
    }
}
