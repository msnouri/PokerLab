import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    objectName: "visionStudio"
    width: 1580; height: 1020
    minimumWidth: 1280; minimumHeight: 820
    visible: true
    title: "PokerLab — Vision Studio"
    color: "#0c1418"
    property int page: 0
    property bool overlays: false
    property color mint: "#b6e2c9"
    property color gold: "#e5cb8e"
    property color muted: "#7e969c"
    property var state: studio.info
    property var vals: studio.values
    property var allFields: studio.fields
    property string selected: root.state.selected || "hole_1"
    property string filterGroup: "Cards"
    function value(key) { return vals[key] === undefined || vals[key] === null ? "—" : vals[key].toString() }
    function number(n, unit) { return n === null || n === undefined || n < 0 ? "—" : n.toFixed(n < 10 ? 1 : 0) + unit }
    function field(key) { for (let f of allFields) if (f.key === key) return f; return {} }
    function cardText(key) {
        let v = value(key); if (v === "—") return "—"
        return v[0] + ({s:"♠",h:"♥",d:"♦",c:"♣"}[v[1]] || "")
    }
    component Panel: Rectangle {
        radius: 18; color: "#132126"; border.color: "#263a3e"; border.width: 1
    }
    component Caption: Text { color: root.muted; font.pixelSize: 11; font.letterSpacing: 1.6 }
    component Body: Text { color: "#e2ebe8"; font.pixelSize: 13; wrapMode: Text.WordWrap }
    component Action: Button {
        id: action
        property bool strong: false
        property bool quiet: false
        implicitHeight: 38
        leftPadding: 14; rightPadding: 14
        font.pixelSize: 12; font.weight: Font.DemiBold
        contentItem: Text { text: action.text; color: !action.enabled ? "#5f777c" : action.strong ? "#152c24" : "#d6e5e1"; font: action.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle {
            radius: 8
            color: !action.enabled ? "#17282c" : action.strong ? (action.hovered ? "#d6f1df" : root.mint) : action.quiet ? (action.hovered ? "#20363a" : "transparent") : (action.hovered ? "#2b4246" : "#203337")
            border.color: action.strong ? root.mint : "#365055"; border.width: action.quiet ? 0 : 1
            Behavior on color { ColorAnimation { duration: 120 } }
        }
    }
    component Badge: Rectangle {
        property string label: ""
        property color tint: root.mint
        implicitWidth: badgeText.implicitWidth + 22; implicitHeight: 26
        radius: 13; color: Qt.rgba(tint.r,tint.g,tint.b,0.09); border.color: Qt.rgba(tint.r,tint.g,tint.b,0.30)
        Text { id: badgeText; anchors.centerIn: parent; text: parent.label; color: parent.tint; font.pixelSize: 10; font.letterSpacing: .5 }
    }
    component SeatSpin: SpinBox {
        id: spin
        implicitWidth: 75; implicitHeight: 38
        leftPadding: 22; rightPadding: 22
        contentItem: Text {
            text: spin.value; color: "#dce9df"; font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { radius: 7; color: "#102026"; border.color: "#39524e" }
        up.indicator: Rectangle {
            x: parent.width-width; width: 22; height: parent.height; radius: 6
            color: spin.up.pressed ? "#36534a" : "#203638"
            Text { anchors.centerIn: parent; text: "+"; color: spin.up.enabled ? root.mint : root.muted; font.pixelSize: 16 }
        }
        down.indicator: Rectangle {
            width: 22; height: parent.height; radius: 6
            color: spin.down.pressed ? "#36534a" : "#203638"
            Text { anchors.centerIn: parent; text: "−"; color: spin.down.enabled ? root.mint : root.muted; font.pixelSize: 16 }
        }
    }
    component Choice: ComboBox {
        id: choice
        implicitHeight: 38; leftPadding: 10; rightPadding: 25
        palette.base: "#15292d"; palette.text: "#dce9df"
        palette.button: "#203638"; palette.buttonText: "#dce9df"
        palette.highlight: "#34584b"; palette.highlightedText: "#eff7ef"
        contentItem: Text {
            text: choice.displayText; color: "#dce9df"; font.pixelSize: 11
            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        }
        indicator: Text { x: parent.width-20; y: 10; text: "⌄"; color: root.mint; font.pixelSize: 14 }
        background: Rectangle { radius: 7; color: "#102026"; border.color: "#39524e" }
    }
    component Metric: Panel {
        property string label: ""
        property string amount: ""
        property string detail: ""
        property color tint: root.mint
        implicitHeight: 112
        Column {
            anchors { fill: parent; margins: 17 } spacing: 7
            Caption { text: label }
            Text { text: amount; color: tint; font.pixelSize: 29; font.weight: Font.Medium; font.letterSpacing: -.7 }
            Text { text: detail; color: root.muted; font.pixelSize: 11 }
        }
        Rectangle { anchors { top: parent.top; right: parent.right; margins: 18 } width: 5; height: 5; radius: 3; color: tint }
    }
    component ReadCard: Rectangle {
        property string keyName: ""
        width: 48; height: 62; radius: 7; color: value(keyName) === "—" ? "#203339" : "#e7ece1"
        border.color: value(keyName) === "—" ? "#3c5558" : "#d2dbc9"
        Text { anchors.centerIn: parent; text: cardText(keyName); color: /[hd]/.test(value(keyName)) ? "#b5535c" : value(keyName) === "—" ? "#72918d" : "#1d3437"; font.pixelSize: 20; font.weight: Font.DemiBold }
    }

    Rectangle {
        id: sidebar; width: 196; anchors { left: parent.left; top: parent.top; bottom: parent.bottom } color: "#101d21"
        Rectangle { anchors.right: parent.right; height: parent.height; width: 1; color: "#25383c" }
        Column {
            anchors { top: parent.top; left: parent.left; right: parent.right; margins: 22 } spacing: 7
            Row { spacing: 10
                Rectangle { width: 31; height: 35; radius: 9; color: root.mint
                    Text { anchors.centerIn: parent; text: "P"; color: "#19372c"; font.pixelSize: 23; font.weight: Font.Black }
                }
                Column { spacing: 3
                    Text { text: "POKERLAB"; color: "#e6eee7"; font.pixelSize: 16; font.weight: Font.Bold; font.letterSpacing: 1.2 }
                    Caption { text: "VISION STUDIO"; font.pixelSize: 8; color: root.gold }
                }
            }
            Item { width: 1; height: 35 }
            Caption { text: "WORKSPACE"; font.pixelSize: 9 }
            Repeater {
                model: [{name:"Overview",symbol:"◈"},{name:"Table setup",symbol:"⌖"},{name:"Replay lab",symbol:"↺"},{name:"Diagnostics",symbol:"≋"}]
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: 152; height: 46; radius: 9; color: root.page === index ? "#29463e" : navMouse.containsMouse ? "#192d31" : "transparent"
                    Row { anchors.verticalCenter: parent.verticalCenter; x: 13; spacing: 12
                        Text { text: modelData.symbol; color: root.page === index ? root.mint : root.muted; font.pixelSize: 18 }
                        Text { text: modelData.name; color: root.page === index ? "#d9efe2" : "#8da6aa"; font.pixelSize: 12; font.weight: Font.Medium }
                    }
                    MouseArea { id: navMouse; anchors.fill: parent; hoverEnabled: true; onClicked: { root.page = index; if (index === 1) studio.pause() } }
                    Behavior on color { ColorAnimation { duration: 130 } }
                }
            }
            Item { width: 1; height: 22 }
            Caption { text: "CURRENT LAYOUT"; font.pixelSize: 9 }
            Text { text: root.state.layout || "Untitled"; width: 152; wrapMode: Text.WordWrap; color: "#b8ccc7"; font.pixelSize: 12 }
            Text { text: root.state.seats + " seats  ·  Hero " + (root.state.hero + 1); color: root.muted; font.pixelSize: 10 }
        }
        Panel {
            anchors { bottom: edition.top; left: parent.left; right: parent.right; margins: 18; bottomMargin: 20 } height: 103; color: "#162d2b"; border.color: "#36564a"; radius: 12
            Column { anchors { fill: parent; margins: 13 } spacing: 9
                Caption { text: "VISION FIRST"; color: root.mint; font.pixelSize: 9 }
                Body { width: parent.width; text: "Observed state.\nVisible uncertainty."; font.pixelSize: 12 }
                Text { text: "Strategies are off"; color: "#7eaaa0"; font.pixelSize: 10 }
            }
        }
        Column { id: edition; anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 24 } spacing: 6
            Text { text: "●   macOS edition"; color: root.mint; font.pixelSize: 11 }
            Text { text: "All processing stays local"; color: "#648282"; font.pixelSize: 9 }
        }
    }

    ColumnLayout {
        anchors { left: sidebar.right; right: parent.right; top: parent.top; bottom: parent.bottom; margins: 26 } spacing: 18
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 58
            Column { spacing: 6
                Text { text: ["Vision overview","Guided table setup","Replay laboratory","Performance & trust"][root.page]; color: "#edf2e9"; font.pixelSize: 27; font.weight: Font.Medium; font.letterSpacing: -.7 }
                Text { text: ["Every card. Every change. In view.","Map once. Verify visually. Reuse your layout.","Inspect the pixels behind every observation.","Measured responsiveness, freshness, and reading coverage."][root.page]; color: root.muted; font.pixelSize: 12 }
            }
            Item { Layout.fillWidth: true }
            Badge { label: "MAC / LOCAL"; tint: root.gold }
            Action { objectName: "sourceButton"; text: "Choose source  ⌄"; onClicked: sourcePopup.open() }
            Action { text: root.state.recording ? "● Recording" : "○ Record"; onClicked: studio.toggleRecord() }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 14
            Metric { Layout.fillWidth: true; label: "RECOGNITION"; amount: number(root.state.readMs," ms"); detail: "Latest pass · includes cache" }
            Metric { Layout.fillWidth: true; label: "TABLE COVERAGE"; amount: root.state.read + " / " + root.state.fields; detail: (root.state.required-root.state.missing) + " of " + root.state.required + " critical fields read"; tint: root.gold }
            Metric { Layout.fillWidth: true; label: "SOURCE AGE"; amount: root.state.live ? number(root.state.age," ms") : "Snapshot"; detail: root.state.live ? "Age since this frame was captured" : "Replay / image source"; tint: "#a6c8db" }
            Metric { Layout.fillWidth: true; label: "UI DISPATCH · P95"; amount: number(root.state.metrics.ui_dispatch_p95_ms," ms"); detail: "Queued heartbeat · not click latency"; tint: "#b8b1de" }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 18
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 13
                Panel {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    ColumnLayout {
                        anchors { fill: parent; margins: 16 } spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 7; height: 7; radius: 4; color: root.state.status === "Verified snapshot" ? root.mint : root.gold
                                SequentialAnimation on opacity { running: root.visible; loops: Animation.Infinite; NumberAnimation { to: .3; duration: 1100 } NumberAnimation { to: 1; duration: 1100 } }
                            }
                            Text { text: root.state.source; color: "#d3e3dc"; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                            Badge { label: root.state.status; tint: root.state.status === "Verified snapshot" ? root.mint : root.gold }
                            Action { text: root.overlays || root.page === 1 ? "Regions on" : "Regions off"; quiet: true; onClicked: root.overlays = !root.overlays }
                        }
                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true; color: "#0d1a20"; radius: 12; clip: true
                            Image { id: tableImage; objectName: "tableImage"; anchors.fill: parent; source: studio.imageSource; fillMode: Image.PreserveAspectFit; cache: false; smooth: true }
                            Item {
                                id: mapArea
                                x: (parent.width-tableImage.paintedWidth)/2; y: (parent.height-tableImage.paintedHeight)/2
                                width: tableImage.paintedWidth; height: tableImage.paintedHeight
                                Repeater {
                                    model: root.overlays || root.page === 1 ? studio.regions : []
                                    delegate: Rectangle {
                                        required property var modelData
                                        x: modelData.x*mapArea.width; y: modelData.y*mapArea.height
                                        width: modelData.w*mapArea.width; height: modelData.h*mapArea.height
                                        color: "transparent"; border.width: root.selected === modelData.key ? 2 : 1
                                        border.color: root.selected === modelData.key ? root.gold : modelData.known ? "#93dbb8" : "#c19468"; radius: 2
                                        Text { y: -12; text: modelData.key; color: parent.border.color; font.pixelSize: 8; visible: root.selected === modelData.key }
                                        MouseArea { anchors.fill: parent; enabled: root.page !== 1; onClicked: studio.selectField(modelData.key) }
                                    }
                                }
                                Rectangle {
                                    id: selection; visible: calibrateMouse.pressed; color: "#22dfcb8c"; border.color: root.gold; border.width: 2
                                    x: Math.min(calibrateMouse.startX,calibrateMouse.endX); y: Math.min(calibrateMouse.startY,calibrateMouse.endY)
                                    width: Math.abs(calibrateMouse.endX-calibrateMouse.startX); height: Math.abs(calibrateMouse.endY-calibrateMouse.startY)
                                }
                                MouseArea {
                                    id: calibrateMouse; anchors.fill: parent; enabled: root.page === 1
                                    property real startX: 0; property real startY: 0; property real endX: 0; property real endY: 0
                                    onPressed: function(mouse) { studio.pause(); startX=mouse.x; startY=mouse.y; endX=mouse.x; endY=mouse.y }
                                    onPositionChanged: function(mouse) { endX=Math.max(0,Math.min(width,mouse.x)); endY=Math.max(0,Math.min(height,mouse.y)) }
                                    onReleased: { if (selection.width>5 && selection.height>5) studio.drawRegion(selection.x/width,selection.y/height,selection.width/width,selection.height/height) }
                                }
                            }
                            Rectangle { anchors { bottom: parent.bottom; right: parent.right; margins: 10 } width: 90; height: 23; color: "#cc102024"; radius: 6
                                Text { anchors.centerIn: parent; text: "FRAME  " + root.state.frame; color: "#a1bbb3"; font.pixelSize: 9; font.letterSpacing: 1 }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Caption { text: root.page === 1 ? "DRAG A REGION FOR: " + root.selected.replace(/_/g," ").toUpperCase() : root.state.engine; font.pixelSize: 9; Layout.fillWidth: true }
                            Action { text: root.state.live ? (root.state.playing ? "Pause capture" : "Resume capture") : (root.state.playing ? "Pause" : "Play replay"); quiet: true; onClicked: studio.togglePlay() }
                            Action { text: "Next frame  →"; onClicked: studio.stepForward() }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true; visible: root.page === 1; spacing: 7
                    Action { text: "Detect cards"; strong: true; onClicked: studio.propose() }
                    Action { text: "Set anchor"; onClicked: studio.selectField("__anchor__") }
                    Action { text: "Confirm region"; onClicked: studio.confirmRegion() }
                    Item { Layout.fillWidth: true }
                    Action { text: "Load layout"; onClicked: studio.loadLayout() }
                    Action { text: "Save layout"; onClicked: studio.saveLayout() }
                }
                RowLayout {
                    Layout.fillWidth: true; visible: root.page === 2
                    Action { text: "Open recording"; onClicked: studio.openReplay() }
                    Slider { Layout.fillWidth: true; from: 0; to: Math.max(1,root.state.replayCount-1); stepSize: 1; value: root.state.replayIndex; onMoved: studio.seek(Math.round(value)) }
                    Text { text: (root.state.replayIndex+1) + " / " + root.state.replayCount; color: root.muted; font.pixelSize: 11 }
                }
                RowLayout {
                    Layout.fillWidth: true; visible: root.page === 3
                    Action { text: "Export timing report"; strong: true; onClicked: studio.exportMetrics() }
                    Text { Layout.fillWidth: true; text: "P95 target < 1 s · P99 target < 2 s. Targets are not certification."; color: root.muted; font.pixelSize: 11; wrapMode: Text.WordWrap }
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8; visible: root.page !== 1
                    Repeater {
                        model: studio.players
                        delegate: Panel {
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 91; radius: 11; color: modelData.hero ? "#203e35" : "#13252b"; border.color: modelData.hero ? "#507c61" : "#2a4145"
                            Column { anchors { fill: parent; margins: 11 } spacing: 7
                                Row { spacing: 5
                                    Text { text: modelData.hero ? "YOU" : "SEAT " + modelData.seat; color: modelData.hero ? root.mint : "#a4bfbb"; font.pixelSize: 9; font.letterSpacing: .7 }
                                    Text { text: modelData.dealer ? " D" : ""; color: root.gold; font.pixelSize: 9 }
                                }
                                Text { text: modelData.stack; color: "#e7ede3"; font.pixelSize: 18; font.weight: Font.Medium }
                                Text { text: modelData.status; color: modelData.status === "folded" ? "#718b89" : "#93b6a7"; font.pixelSize: 9 }
                            }
                        }
                    }
                }
            }

            Panel {
                Layout.preferredWidth: 305; Layout.fillHeight: true
                ColumnLayout {
                    anchors { fill: parent; margins: 18 } spacing: 13
                    RowLayout {
                        Layout.fillWidth: true
                        Caption { text: root.page === 1 ? "FIELD INSPECTOR" : root.page === 3 ? "SESSION DIAGNOSTICS" : "OBSERVED TABLE"; Layout.fillWidth: true }
                        Text { text: "●"; color: root.mint; font.pixelSize: 10 }
                    }
                    Row { spacing: 10; visible: root.page !== 1 && root.page !== 3
                        ReadCard { keyName: "hole_1" } ReadCard { keyName: "hole_2" }
                        Column { y: 9; spacing: 8
                            Caption { text: "YOUR HAND"; font.pixelSize: 9 }
                            Body { text: "Pot  " + value("pot"); font.pixelSize: 17 }
                        }
                    }
                    Row { spacing: 6; visible: root.page !== 1 && root.page !== 3
                        Repeater { model: 5; delegate: ReadCard { required property int index; keyName: "board_"+(index+1); width: 43; height: 52 } }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#2b4144" }
                    RowLayout { Layout.fillWidth: true; visible: root.page !== 3
                        Repeater { model: ["Cards","Table","Seats","Controls"]
                            delegate: Action { required property string modelData; text: modelData; implicitHeight: 28; leftPadding: 5; rightPadding: 5; strong: root.filterGroup === modelData; onClicked: root.filterGroup = modelData }
                        }
                    }
                    ListView {
                        id: fieldList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 4
                        visible: root.page !== 3; model: root.allFields.filter(f => f.group === root.filterGroup); reuseItems: true
                        delegate: Rectangle {
                            required property var modelData
                            width: fieldList.width; height: root.page === 1 ? 47 : 42; radius: 6
                            color: root.selected === modelData.key ? "#28423d" : fieldMouse.containsMouse ? "#1d3335" : "transparent"
                            RowLayout { anchors { fill: parent; leftMargin: 9; rightMargin: 8 } spacing: 7
                                Rectangle { width: 4; height: 4; radius: 2; color: modelData.quality === "read" || modelData.quality === "confirmed" ? root.mint : root.gold }
                                Column { Layout.fillWidth: true; spacing: 4
                                    Text { text: modelData.label; color: "#a8c1bb"; font.pixelSize: 10; elide: Text.ElideRight; width: parent.width }
                                    Text { text: root.page === 1 ? (modelData.confirmed ? "Calibrated" : modelData.region ? "Suggested · confirm" : "Draw a region") : modelData.cached ? "Pixels unchanged" : modelData.quality; color: "#64887f"; font.pixelSize: 8 }
                                }
                                Text { text: modelData.display; color: modelData.quality === "unknown" ? root.gold : "#edf1e5"; font.pixelSize: 12; elide: Text.ElideRight; Layout.maximumWidth: 90 }
                            }
                            MouseArea { id: fieldMouse; anchors.fill: parent; hoverEnabled: true; onClicked: studio.selectField(modelData.key) }
                        }
                        ScrollBar.vertical: ScrollBar { }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; visible: root.page === 3; spacing: 14
                        Repeater {
                            model: [{k:"Source frames",v:root.state.metrics.frames},{k:"OCR calls",v:root.state.metrics.ocr_calls},{k:"Cache hits",v:root.state.metrics.cache_hits},{k:"Stale results dropped",v:root.state.metrics.stale_results_discarded},{k:"Timeouts",v:root.state.metrics.timeouts},{k:"Complete snapshots",v:root.state.metrics.complete_snapshots},{k:"Incomplete snapshots",v:root.state.metrics.incomplete_snapshots},{k:"Read P95",v:number(root.state.metrics.read_p95_ms," ms")},{k:"Read P99",v:number(root.state.metrics.read_p99_ms," ms")}]
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Text { text: modelData.k; color: root.muted; font.pixelSize: 11; Layout.fillWidth: true }
                    Text { text: modelData.v === undefined || modelData.v === null ? "—" : modelData.v; color: "#d9e9df"; font.pixelSize: 12 }
                            }
                        }
                        Body { Layout.fillWidth: true; text: "These are live session measurements. Reading speed excludes strategy calculation. Coverage is reported separately from correctness."; color: root.muted; font.pixelSize: 11 }
                        Item { Layout.fillHeight: true }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; visible: root.page === 1; spacing: 8
                        Text { text: root.selected.replace(/_/g," "); color: root.gold; font.pixelSize: 12 }
                        Body { Layout.fillWidth: true; text: field(root.selected).reason || "Draw the selected field on the image."; color: root.muted; font.pixelSize: 10 }
                        TextField { id: exampleText; Layout.fillWidth: true; placeholderText: "As / true / folded / amount"; color: "#dce9df"; font.pixelSize: 11; background: Rectangle { radius: 7; color: "#0c1b20"; border.color: "#39524e" } }
                        RowLayout { Layout.fillWidth: true
                            Action { text: "Teach visual"; onClicked: studio.teach(exampleText.text) }
                            Action { text: "Correct value"; onClicked: studio.correct(exampleText.text) }
                        }
                        RowLayout { Layout.fillWidth: true
                            Action { text: "Learn empty slot"; onClicked: studio.teachBlank() }
                            Action { text: "Remove"; quiet: true; onClicked: studio.removeRegion() }
                        }
                        RowLayout {
                            Caption { text: "SEATS"; font.pixelSize: 8; Layout.preferredWidth: 75 }
                            Caption { text: "YOUR SEAT"; font.pixelSize: 8; Layout.preferredWidth: 75 }
                            Caption { text: "CHIP SCALE"; font.pixelSize: 8; Layout.preferredWidth: 70 }
                        }
                        RowLayout {
                            SeatSpin { id: seatCount; from: 2; to: 9; value: root.state.seats }
                            SeatSpin { id: heroSeat; from: 1; to: seatCount.value; value: root.state.hero+1 }
                            Choice { id: units; model: ["×1","×100"]; implicitWidth: 70 }
                        }
                        Action { text: "Apply seats / hero / units"; Layout.fillWidth: true; onClicked: studio.configure(seatCount.value,heroSeat.value-1,units.currentIndex === 0 ? 1 : 100) }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; visible: root.page !== 1 && root.page !== 3; spacing: 9
                        Caption { text: "OBSERVED CHANGES"; font.pixelSize: 9 }
                        ListView {
                            Layout.fillWidth: true; Layout.preferredHeight: 100; clip: true; spacing: 10
                            model: studio.events
                            delegate: RowLayout { required property var modelData; width: 260
                                Text { text: "·"; color: root.gold; font.pixelSize: 18 }
                                Text { text: modelData.message; color: "#99b4a8"; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            }
                        }
                        Text { text: "Action history completeness: unknown"; color: "#b69e73"; font.pixelSize: 9 }
                    }
                    Action { text: "Export observed state  ↗"; Layout.fillWidth: true; onClicked: studio.exportState() }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 32
            Rectangle { width: 5; height: 5; radius: 3; color: root.gold }
            Text { text: root.state.note; color: "#93ada5"; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight }
            Text { text: "Scores ≠ probabilities  ·  Live use only where permitted"; color: "#536f71"; font.pixelSize: 9 }
        }
    }

    Popup {
        id: sourcePopup; x: root.width-width-30; y: 88; width: 460; height: 410; padding: 22; modal: false; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Panel { color: "#1a2d30"; border.color: "#476055" }
        ColumnLayout { anchors.fill: parent; spacing: 14
            Text { text: "Choose your source"; color: "#e3eee4"; font.pixelSize: 20 }
            Body { Layout.fillWidth: true; text: "Capture a single Mac window, inspect an image, or replay a recorded session."; color: root.muted; font.pixelSize: 12 }
            RowLayout {
                Action { text: "Practice demo"; strong: true; onClicked: { studio.loadDemo(); sourcePopup.close() } }
                Action { text: "Open image"; onClicked: { sourcePopup.close(); studio.openImage() } }
                Action { text: "Open replay"; onClicked: { sourcePopup.close(); studio.openReplay() } }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#3b5553" }
            Caption { text: "MAC WINDOW CAPTURE"; color: root.gold }
            RowLayout {
                Action { text: "Screen Recording access"; onClicked: studio.requestPermission() }
                Action { text: "Refresh windows"; onClicked: studio.refreshWindows() }
            }
            Choice { id: windowChoice; Layout.fillWidth: true; textRole: "title"; model: studio.windowRows; displayText: count ? currentText : "Refresh to discover windows" }
            Action { text: "Capture selected window"; strong: true; Layout.fillWidth: true; enabled: windowChoice.count > 0; onClicked: { studio.useWindow(windowChoice.currentIndex); sourcePopup.close(); root.page=1 } }
            Text { text: root.state.note; color: root.muted; font.pixelSize: 10; Layout.fillWidth: true; wrapMode: Text.WordWrap }
        }
    }
}
