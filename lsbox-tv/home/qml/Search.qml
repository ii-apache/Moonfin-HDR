// Search your Jellyfin library. Type with the arrows + OK on the keyboard,
// or from the phone remote. Down goes to the results, OK opens one in
// Moonfin, Play starts it.
import QtQuick

Rectangle {
    id: root
    property bool shown: false
    property string text: ""
    property string area: "keys"    // keys | results
    property int keyIndex: 0
    property int resIndex: 0
    readonly property int cols: 12
    readonly property var keyList: "abcdefghijklmnopqrstuvwxyz1234567890".split("").concat(["space", "delete", "clear"])
    readonly property var results: home.searchResults
    anchors.fill: parent
    color: theme.bgSolid
    visible: opacity > 0
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 180 } }

    onShownChanged: if (shown) { area = "keys"; keyIndex = 0 }
    onTextChanged: debounce.restart()
    onResultsChanged: if (resIndex >= results.length) resIndex = 0
    Timer { id: debounce; interval: 450; onTriggered: home.search(root.text) }

    function append(t) { text = (text + t).slice(0, 60) }
    function press(k) {
        if (k === "space") append(" ")
        else if (k === "delete") text = text.slice(0, -1)
        else if (k === "clear") text = ""
        else append(k)
    }

    function key(e) {
        var k = e.key
        if (keys.isBack(k)) {
            if (area === "results") area = "keys"
            else if (text !== "" && k === Qt.Key_Backspace) text = text.slice(0, -1)
            else win.overlay = ""
            return
        }
        if (e.text && e.text.length === 1 && /[a-z0-9 ]/i.test(e.text) && k !== Qt.Key_Space) { append(e.text.toLowerCase()); return }
        if (area === "keys") {
            var n = keyList.length
            if (k === Qt.Key_Left) { if (keyIndex > 0 && layout[keyIndex - 1].row === layout[keyIndex].row) keyIndex-- }
            else if (k === Qt.Key_Right) { if (keyIndex < n - 1 && layout[keyIndex + 1].row === layout[keyIndex].row) keyIndex++ }
            else if (k === Qt.Key_Up) moveVert(-1)
            else if (k === Qt.Key_Down) { if (!moveVert(1) && results.length) area = "results" }
            else if (keys.isOk(k) && !e.isAutoRepeat) press(keyList[keyIndex])
            else return
            home.feedback()
        } else {
            if (k === Qt.Key_Left) resIndex = Math.max(0, resIndex - 1)
            else if (k === Qt.Key_Right) resIndex = Math.min(results.length - 1, resIndex + 1)
            else if (k === Qt.Key_Up) area = "keys"
            else if (keys.isOk(k) && !e.isAutoRepeat && results[resIndex]) home.openCard(results[resIndex], false)
            else if (keys.isPlay(k) && results[resIndex]) home.openCard(results[resIndex], true)
            else return
            home.feedback()
        }
    }

    Text {
        x: win.margin; y: win.height * 0.07
        text: "Search"
        color: theme.ink; font.pixelSize: 52 * win.u; font.weight: Font.Bold
    }
    Rectangle {
        id: field
        x: win.margin; y: win.height * 0.07 + 90 * win.u
        width: win.width - 2 * win.margin; height: 92 * win.u; radius: 20 * win.u
        color: theme.rowBg
        Text {
            x: 32 * win.u; anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 64 * win.u
            text: root.text !== "" ? root.text : "Movies, shows, episodes, people"
            color: root.text !== "" ? theme.ink : theme.inkDim
            font.pixelSize: 38 * win.u
            elide: Text.ElideLeft
        }
        Rectangle {  // caret
            x: 32 * win.u + Math.min(caretProbe.implicitWidth, parent.width - 70 * win.u) + 4 * win.u
            anchors.verticalCenter: parent.verticalCenter
            width: 3 * win.u; height: 44 * win.u
            color: theme.ink
            visible: root.text !== "" && root.shown
            SequentialAnimation on opacity {
                running: root.shown; loops: Animation.Infinite
                NumberAnimation { to: 0; duration: 500 } NumberAnimation { to: 1; duration: 500 }
            }
        }
        Text { id: caretProbe; visible: false; text: root.text; font.pixelSize: 38 * win.u }
    }

    // Keyboard: 12 keys a row; Space, Delete and Clear are two keys wide.
    readonly property real cell: 92 * win.u
    readonly property var layout: {
        var out = [], col = 0, row = 0
        for (var i = 0; i < keyList.length; i++) {
            var w = keyList[i].length > 1 ? 2 : 1
            if (col + w > cols) { col = 0; row++ }
            out.push({ col: col, row: row, w: w })
            col += w
        }
        return out
    }
    function moveVert(dir) {
        var cur = layout[keyIndex], cx = cur.col + cur.w / 2, best = -1, bd = 1e9
        for (var i = 0; i < layout.length; i++) {
            if (layout[i].row !== cur.row + dir) continue
            var d = Math.abs(layout[i].col + layout[i].w / 2 - cx)
            if (d < bd) { bd = d; best = i }
        }
        if (best >= 0) { keyIndex = best; return true }
        return false
    }

    Item {
        id: kb
        x: win.margin; y: field.y + field.height + 40 * win.u
        width: root.cols * root.cell
        height: (root.layout[root.layout.length - 1].row + 1) * root.cell
        Repeater {
            model: root.keyList
            Rectangle {
                required property var modelData
                required property int index
                readonly property var pos: root.layout[index]
                readonly property bool sel: root.area === "keys" && index === root.keyIndex
                x: pos.col * root.cell
                y: pos.row * root.cell
                width: pos.w * root.cell - 12 * win.u
                height: root.cell - 16 * win.u
                radius: 14 * win.u
                color: sel ? theme.selBg : theme.rowBg
                scale: sel ? 1.08 : 1
                Behavior on scale { NumberAnimation { duration: 100 } }
                Text {
                    anchors.centerIn: parent
                    text: modelData === "space" ? "Space" : modelData === "delete" ? "Delete" : modelData === "clear" ? "Clear" : modelData.toUpperCase()
                    color: parent.sel ? theme.selText : theme.ink
                    font.pixelSize: (modelData.length > 1 ? 26 : 32) * win.u
                    font.weight: Font.DemiBold
                }
            }
        }
    }

    Text {
        x: win.margin; y: kb.y + kb.height + 46 * win.u
        text: home.searchBusy ? "Searching..." : (root.text === "" ? "Tip: the phone remote can type here too"
              : (root.results.length ? root.results.length + (root.results.length === 1 ? " result" : " results") : "Nothing found"))
        color: theme.inkDim; font.pixelSize: 26 * win.u
    }

    ListView {
        id: resList
        y: kb.y + kb.height + 100 * win.u
        width: win.width
        height: win.cardH * 1.45
        orientation: ListView.Horizontal
        spacing: 30 * win.u
        leftMargin: win.margin; rightMargin: win.margin
        interactive: false
        model: root.results
        currentIndex: root.resIndex
        highlightMoveDuration: 200
        preferredHighlightBegin: win.margin
        preferredHighlightEnd: win.width - win.margin - win.cardW
        highlightRangeMode: ListView.ApplyRange
        delegate: Card {
            required property var modelData
            required property int index
            item: modelData
            textColor: theme.ink
            subColor: theme.inkDim
            focused: root.area === "results" && index === root.resIndex
            showTitle: true
        }
    }
}
