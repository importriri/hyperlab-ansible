# Discovered command help retained the previous product name

Status: corrected in source and covered by the product display contract.
Physical presentation on Nitro and Predator remains pending.

## Symptom

Changing the CLI's root description left the previous product name in
`hyperlabctl --help`, under `open`, and in `hyperlabctl doctor --help`,
under `--hardware`.

## Root cause

Commands supply their own help when the parser discovers them. The root
banner does not own those strings, and nested parsers format independently.

## Fix

The shared parser formats human-readable help using the display name from
`tools/product.yml`. Nested parsers inherit that formatter. Command names,
arguments, identifiers and execution remain unchanged.

## Regression proof

`python tests/product_display_name_contract.py` traverses the real parser
and every discovered child, formats their help, and rejects the old display
name. Removing the shared help formatting makes that check fail. The same
contract checks the version banner, QML presentation and notification argv.
An AST guard also rejects new old-name help/description literals, with only
the two existing literals enumerated, so formatting cannot hide source drift.
