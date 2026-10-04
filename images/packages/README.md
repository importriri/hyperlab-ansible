# Package lists of Workbench images

One file per image the Workbench captured or derived, named after the image
id: every installed package as `name version`, sorted, read from the image
by libguestfs inspection without booting it. The image manifest's
`build.packages` names the file and pins its sha256, so a changed list is a
reviewed change; `tests/schema_validate.py` refuses a list that no longer
matches its manifest. Comparing two versions of an image is a diff of two of
these files.
