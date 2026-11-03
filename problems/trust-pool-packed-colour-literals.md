# A packed colour bypassed the trust pool source contract

Author: [importriri](https://github.com/importriri).

Status: corrected in the source contract; software verification only.

## Symptom

A renderer could replace DEV's palette-derived tint with the packed integer
`0x5b8cff` and still pass the generated pool contract. The constant produced
the same current images but stopped following future palette changes.

## Root cause

The source check rejected colour strings and RGB triples, but did not compare
numeric literals with packed palette values. Python integers and numbers
inside the QML scene could both escape it. Exact rendering cannot expose a
duplicated constant while the palette still has the same value.

## Fix

Compare numeric values from the Python AST and numeric literal tokens in
its QML strings with each domain's packed RGB value. Recognize base-prefixed
and decimal spellings, including uppercase prefixes and digit separators.
The palette supplies the comparison values, so the contract stores no second
table of identity colours. The renderer and its images remain unchanged.

## Regression proof

`tests/MUTATIONS.md` records used Python and QML packed-colour substitutions.
Both passed the full generated contract before this correction. They now fail
at its source stage with `hardcoded packed identity RGB: dev`; restoration
passes exact regeneration of all twelve images and their manifest. Additional
source-stage mutations cover alternate numeric spellings for all identities.
