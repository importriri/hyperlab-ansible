# Quickshell stand-ins for offscreen QML contracts

These modules imitate the small part of the Quickshell API that the guest
Workspace Shell uses, so its real QML can be instantiated by a plain Qt 6
`qmlscene` with no compositor, no PipeWire and no processes.

Every stand-in is deliberately dumb: processes answer from fixtures in
`QsHarness`, files are read from `QsHarness.files`, and layer-shell windows
become ordinary items placed by their anchors, so one scene can hold the
whole desktop and be captured as an image.

They prove that the shell instantiates, binds and behaves against the
fixtures. They do not prove the real Quickshell runtime, layer-shell focus or
compositor behaviour; that remains physical acceptance on a guest.
