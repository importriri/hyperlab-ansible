import QtQuick

QtObject {
    enum Precision { Hours, Minutes, Seconds }

    property int precision: SystemClock.Minutes
    property date date: QsHarness.now
}
