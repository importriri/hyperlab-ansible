// Text that changes with a short lift instead of a jump.

import QtQuick

UiText {
    id: swap

    property string value: ""

    text: value

    onValueChanged: {
        if (theme.normal > 0)
            lift.restart();
    }

    transform: Translate { id: shift }

    ParallelAnimation {
        id: lift

        NumberAnimation {
            target: shift; property: "y"; from: 6; to: 0
            duration: swap.theme.normal; easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: swap; property: "opacity"; from: 0; to: 1
            duration: swap.theme.normal; easing.type: Easing.OutCubic
        }
    }
}
