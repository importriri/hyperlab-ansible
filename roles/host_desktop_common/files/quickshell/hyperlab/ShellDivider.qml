// HyperLab shell separator (V447-C9.3).
//
// A separator is structure, not decoration: it stays a hairline and is used
// only between semantic groups. A vertical divider is a rail-height rule; a
// horizontal one spans the width it is given.

import QtQuick

Rectangle {
    id: divider

    required property var tokens
    required property var theme

    property bool vertical: true

    implicitWidth: divider.vertical ? 1 : divider.tokens.dividerHeight
    implicitHeight: divider.vertical ? divider.tokens.dividerHeight : 1

    color: divider.theme.hairline

    Accessible.ignored: true
}
