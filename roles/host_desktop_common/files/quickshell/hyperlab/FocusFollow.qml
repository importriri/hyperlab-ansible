// HyperLab focus-follow scrolling (V447-C9.3).
//
// A control that is reachable with Tab has to be visible when it gets there.
// A plain Flickable does not scroll to its focused child, so every scrolled
// region in the shell carries one of these: when keyboard focus lands on an
// item inside the region's content, the region scrolls just far enough to
// show it, with a small margin, and never past its own bounds.
//
// Presentation only: it moves a viewport and nothing else.

import QtQuick

Item {
    id: follow

    required property Flickable flickable

    property real margin: 8

    visible: false

    function contains(item) {
        const content = follow.flickable.contentItem;

        for (let node = item; node; node = node.parent) {
            if (node === content)
                return true;
        }

        return false;
    }

    function reveal(item) {
        const view = follow.flickable;

        if (!item || !view.visible || !follow.contains(item))
            return;

        const point = item.mapToItem(view.contentItem, 0, 0);
        const maxY = Math.max(0, view.contentHeight - view.height);
        const maxX = Math.max(0, view.contentWidth - view.width);

        if (point.y < view.contentY)
            view.contentY = Math.max(0, point.y - follow.margin);
        else if (point.y + item.height > view.contentY + view.height)
            view.contentY = Math.min(
                maxY,
                point.y + item.height - view.height + follow.margin
            );

        if (point.x < view.contentX)
            view.contentX = Math.max(0, point.x - follow.margin);
        else if (point.x + item.width > view.contentX + view.width)
            view.contentX = Math.min(
                maxX,
                point.x + item.width - view.width + follow.margin
            );
    }

    Connections {
        target: follow.Window.window

        function onActiveFocusItemChanged() {
            follow.reveal(follow.Window.window.activeFocusItem);
        }
    }
}
