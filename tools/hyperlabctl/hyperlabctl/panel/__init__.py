"""The full-screen cockpit. Split deliberately in two.

model.py turns a status document into a screen of plain data and holds every
decision; ui.py only paints it. That is what makes a TUI testable: the suite
asserts on the model, and never has to drive a terminal.
"""
