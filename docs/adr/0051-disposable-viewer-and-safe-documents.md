# ADR 0051 - A disposable viewer, and documents rebuilt from pixels

Status: proposed.

## Context

A document that arrives in a Machine (an attachment, a download) can attack
the program that opens it: a PDF carries JavaScript, forms, links, fonts and
embedded files, and its parser is large. Opening it where it arrived gives
that attack the Machine's files and network. Qubes OS answers with a
disposable VM to view it and with converting it to pixels and back. HyperLab
has disposable Machines (ADR 0018), a Machine without a network (the key
vault, ADR 0048), and a host-assigned vsock channel.

## Options

**A. A disposable viewer without a network, and a pixel-only rebuild
(recommended).**

- **View.** The Machine asks the host, over its vsock port, to open one
  file in a disposable viewer. The host confirms with the operator (which
  Machine, which file name and size), starts the viewer, a predefined
  disposable Machine without a network whose disk is discarded at every
  stop, and passes the file's bytes to it over vsock. The host never writes
  them to its own disk and never parses them. The operator sees the viewer
  in its own window. Closing it stops the Machine, and its disk goes with
  it.
- **Make safe.** The same path, but the viewer renders every page with
  `pdftoppm` and sends back only a pixel stream: a fixed header, then per
  page its width, height and exactly width × height × 3 bytes. The
  requesting Machine rebuilds a PDF of one image per page
  (`hyperlab-safe-pdf from-pixels`). The reader trusts none of the stream:
  every number has a limit, and anything outside the format writes
  nothing. The result has the pages' picture and nothing else: no text
  layer, no links, no scripts, no forms, no embedded files.

**B. Convert in the Machine that received the file, in a sandbox
(bubblewrap, seccomp).** No second Machine, but the parser still runs next
to the Machine's files, behind a sandbox HyperLab would have to keep
correct.

**C. Convert on the host.** Rejected: it puts the attacker's parser in the
domain that decides everything.

## Recommendation

A. Built in this order:

1. `hyperlab-safe-pdf` (`roles/guest_safe_documents`): `to-pixels` and
   `from-pixels`, with the stream reader's limits and a test that a PDF
   carrying JavaScript, an embedded file, a link and a form comes back with
   the same picture and none of them. Done first.
2. The viewer Machine: a disposable, standard Linux Machine without a
   network (the reserved `none` network, so far the vault's alone, is
   extended to it), and a vsock receiver that accepts only the host.
3. The host relay: confirmation, viewer start, bytes over vsock in both
   directions, viewer stopped at the end, one request at a time.
4. The request command in a Machine (`hyperlab-open-disposable FILE`,
   `--safe` for the rebuild), and a menu entry in the guest file manager.

## What this does not cover

- The rebuilt PDF has no text layer: it cannot be searched or copied from,
  and it is larger than the original. OCR inside the disposable viewer
  would give text back, and text is a channel; it is not offered.
- Formats other than PDF. Images could follow the same path; office
  documents would first be converted to PDF inside the disposable viewer.
- An attack on the viewer's own display path (SPICE) while it shows the
  document. The viewer has no network and no files of the operator, and it
  is discarded, but its display reaches the host's SPICE client.
- A pixel stream that is valid but shows misleading content: the rebuild
  removes active content, not lies.

## Hardware test

In the lab host, then on Nitro: from `dev-01`, a crafted PDF (JavaScript
`app.alert`, an embedded file, a URI link) opened with
`hyperlab-open-disposable --safe` asks for confirmation on the host, starts
the viewer, returns a PDF that `pdfinfo` reports with `JavaScript: no` and
`Form: none` and that looks the same; `virsh domiflist` on the viewer is
empty; after the request the viewer is shut off and its transient disk is
gone.
