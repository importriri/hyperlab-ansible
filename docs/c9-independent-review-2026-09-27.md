> **Historical review snapshot — superseded by final C9 evidence.**
>
> This document records the state observed on 2026-09-27 while C9 was still
> changing. Status values such as `VERIFY=FAIL` and `RUNTIME_REQUIRED=YES`
> below are intentionally preserved as historical evidence; they are not the
> current release status. Subsequent work closed the false reboot/power-cycle
> presentation completion issue, completed physical focused-surface provenance
> acceptance, physically accepted the Linux Looking Glass SDR correction,
> localized the Valley artefact upstream as application-specific/non-blocking,
> and obtained a complete green repository verification outside the restricted
> chat bridge.

Independent C9 review, 2026-09-27

Reviewed the local candidate at `53489ee` with uncommitted C9 changes. Concurrent implementation continued during this review: the initial terminal-owned runner was replaced with a worker/observer design, and a guest colour patch arrived. Results below distinguish reproduced initial defects, fixes verified against the revised source, and outstanding runtime evidence. No branch, commit, push, reset, deployment, VM operation, or destructive cleanup was performed by this reviewer.

```text
C9.3_LIFECYCLE=PARTIAL
TRUST_CLASSIFICATION=PASS
TRUST_LEVEL_MODEL=CONSISTENT
LOOKING_GLASS_COLOR=ROOT_CAUSE_FOUND
VERIFY=FAIL
RUNTIME_REQUIRED=YES
```

PASS for classification is a software assessment. The operation helper installed at `/usr/local/bin/privatestack-operation` differed from the reviewed checkout when inspected. No active operation units were listed. Source tests cannot certify the deployed host.

```text
FINDING=terminal-owned-operation
SEVERITY=high
EVIDENCE=privatestack-operation.py launch()/run(); independent terminal-hangup regression
WHY=The initial unit owned Foot, and runner SIGHUP handling terminated its child. Closing the terminal could stop accepted work.
FIX=The implementation replaced that hierarchy with a systemd worker owning the command/PTY and a separate observer unit. Worker ignores SIGHUP; explicit unit stop still interrupts.
TEST=test_terminal_hangup_does_not_terminate_execution failed before the revision and passes after it. Revised host_operation_lifecycle_contract.py also exercises real PTY authentication, detach, and reattach.
```

```text
FINDING=dispatch-timeout-is-not-failure
SEVERITY=high
EVIDENCE=privatestack-operation.py launch(); timeout-after-acceptance regression
WHY=systemd-run can time out after acceptance. The initial handler wrote an immutable failed record; the worker then refused that accepted operation and a retry could launch another unit.
FIX=The implementation now leaves the operation dispatched on timeout; backend unit recovery resolves its status.
TEST=test_timeout_after_unit_acceptance_is_not_a_terminal_failure failed initially and now passes, including duplicate refusal while the accepted unit is active.
```

```text
FINDING=observer-backpressure-stalls-worker
SEVERITY=high
EVIDENCE=privatestack-operation.py relay(), blocking accepted sockets and sendall(); bounded non-reading-observer test
WHY=A suspended or stalled observer could block the relay, then command output and completion. Execution was still dependent on observer behaviour despite separate process lifetimes.
FIX=Reviewer changed accepted observer sockets to nonblocking. Existing send-error handling disconnects a slow observer so execution continues; it can reattach for replay.
TEST=test_stalled_observer_cannot_block_worker_completion failed with the worker stuck at its deadline, then passed after the fix.
```

```text
FINDING=unreadable-domain-inherits-clean-label
SEVERITY=medium
EVIDENCE=providers/domains.py resolve_trust(); failed dumpxml for GPU-mapped win11clean-valley
WHY=managed=None was treated as unmanaged by `is not True`, allowing the GPU map to manufacture a clean identity when domain metadata was unreadable.
FIX=Reviewer changed the legacy fallback to require `managed is False` explicitly.
TEST=test_unreadable_gpu_mapped_domain_has_no_network_identity failed with trust_profile=clean and now passes with None.
```

```text
FINDING=reboot-completion-evidence-gap
SEVERITY=medium
EVIDENCE=roles/guest/tasks/reboot.yml non-QGA branch and guest_wait_for_qga condition; OperationTracker.qml reconcile()
WHY=An ACPI reboot request followed by domstate=running does not prove reboot. QGA=true with guest_wait_for_qga=false also skips the boundary check. The operation can exit zero and QML can call it completed without observing a guest restart.
FIX=Before universal lifecycle acceptance, either refuse unsupported proof paths or expose an explicit unverified/requested outcome from the backend. Keep the existing default QGA disconnect/reconnect proof.
TEST=Outstanding: inert ACPI request that succeeds while the guest never reboots must not produce verified completion. Current default guest_wait_for_qga=true avoids the QGA opt-out path; this review did not change reboot semantics.
```

```text
FINDING=SDR-marked-as-HDR-PQ
SEVERITY=medium
EVIDENCE=installed Looking Glass source at 0140a3f6fb616c5636d6c430eb71b8a7d5338e39, PipeWire streamParamChangedCallback; client main.c and Wayland/gl.c; installed SPA headers
WHY=The sender bitmasks sequential format enum values and always sets hdrPQ=true. RGBx=7, BGRx=8, RGBA=11 and BGRA=12 all falsely test as HDR. The client separately emits PQ/BT.2020 Wayland metadata; disabling EGL tone mapping does not disable this metadata path.
FIX=The sender patch uses format equality and only asserts PQ for its selected HDR formats. Rebuild/deploy and verify SDR output before claiming the live issue fixed. Genuine HDR/FP16 transfer semantics remain outside this SDR fix.
TEST=An independent compiled check against installed SPA headers reproduced all four false positives and their correction. Linux capture and hardware-gate source contracts pass. Live frame/protocol evidence remains required.
```

```text
FINDING=verification-discovers-bytecode-as-shell
SEVERITY=medium
EVIDENCE=verify.sh shell-script discovery; both full verifier logs selected tests/__pycache__/host_quickshell_runtime_contract.cpython-314.pyc
WHY=Recursive grep matched an embedded shebang in generated Python bytecode and sent it to ShellCheck. Repeated verification depended on cache presence.
FIX=Reviewer added grep -I so discovery ignores binary files, without deleting caches.
TEST=test_shell_discovery_ignores_generated_binary_files reproduces the failure using the actual verify.sh discovery command, then passes with a real shell script retained and bytecode excluded. Full discovered ShellCheck is rerun after the fix.
```

The historical mitigation `egl:mapHDRtoSDR=no` entered the managed Linux launch path in `49f5c9c` and is still present. No removal of that mitigation was found. `bc28941` addressed PipeWire frame lifetime, a separate defect. The source supports a compositor colour-management path exposing the existing metadata defect; this review did not establish which deployment first exposed it. This diagnosis concerns the Linux PipeWire sender, not the Windows capture stack.

For runtime colour verification, record the actual client argv, sender build/patch stamp, host output format and colour preset, and a real received frame's `Format: ... hdr:0 pq:0` line. For that SDR frame, verify the Wayland trace does not request ST2084 PQ/BT.2020. Repeat after guest reboot and sender reconnect. Merely finding no PQ request is insufficient if no frame arrived. The new diagnostic script can report PASS after seeing the colour-manager advertisement without proving a frame arrived; require the frame evidence alongside its result. Do not infer visual correctness from source tokens or disable compositor colour management globally.

The revised lifecycle has strong software evidence for allowlisted command resolution, private 0700 directories/0600 records, no-follow record reads with ownership/type checks, atomic replacement, exclusive dispatch locking, one-time worker claims, terminal-result preservation, exit-code propagation, and shell rehydration. Operation unit names derive from 128-bit random IDs rather than machine names. No shell interpolation is used. Same-UID modification of this user-owned checkout is not treated as a new privilege boundary. Random-ID collision speculation does not justify extra machinery here.

Records and transcripts are boot/session runtime data under XDG_RUNTIME_DIR, not a durable cross-reboot audit store. Transcript output is capped at 1 MiB and late replay at 64 KiB; after that cap, replay cannot show the newest output. Recovery uses unit liveness and does not invent success from an absent unit. QML maps execution success to verification and checks fresh inventory, but its verb-to-target-state mapping remains presentation-side completion policy. A future typed backend outcome should own that policy, especially for reboot. Reset correctly means recreating a shut-off disposable guest, not a hardware reboot; no reset change was warranted.

The implemented authority graph is:

- Managed VM spec `network_profile` becomes libvirt `network-profile` metadata through the guest XML template. Domain telemetry accepts it only when declared and consistent with attached networks; shell machine badges consume the backend identity.
- `gpu_domain_profiles` remains the GPU admission/ownership map. Domain diagnostics use the separate `gpu_trust_profile` when checking missing VFIO guards. The CLI start gate and handoff hook still require the GPU map; a network identity does not grant GPU access.
- The GPU hook consumes rendered domain/profile and profile/level maps and rejects upward transitions within a boot. The trust provider reads the boot claim; render.py publishes typed claim data.
- Focused surface colour uses host-owned registration plus spec identity/digest, not guest window titles. Focus RGB uses that provenance; system RGB uses the GPU trust claim. These represent different facts and must retain their distinct labels.

`arch-dev` is explicitly standard/dev in its checked-in spec. The new trust_identity tests classify it without a GPU entry, cover metadata disagreement and legacy metadata, and retain the missing-VFIO-mapping error. Relevant VFIO and trust-model contracts pass. No GPU hook, trust rank, or admission rule was changed by this reviewer.

The rank model is intentional and consistent in available code/history: `clean=3, dev=2, dirty=1, lab=0` already appears in original scaffold `3fffa81`, survived the variables split `12284ce`, and matches current configuration, fixtures and the downward-only hook. ADR 0009 documents same/lower transitions until reboot. No evidence was found for an implemented clean/dev equivalence; no rank changes were made.

Reproducibility is not established for the requested complete pipeline. `tools/release_acceptance.py` executable repository proof requires exact planned HEADs and clean worktrees; current uncommitted C9 changes cannot meet that contract. The current Windows manifest is `not-built`, has no artifact digest or observed Looking Glass host build, and explicitly requires a private manually built/sealed singleton master. Arch's cloud image has pinned source/artifact digests, but that alone does not prove post-reboot guest SSH, graphical session, capture, and driver persistence. Existing August hardware receipts describe older commits and explicitly leave reboot/reconnect and post-reboot idempotence open; they do not certify this tree. No fresh ISO installation, guest reboot, host reboot, image sealing, or hardware convergence was performed here.

The remaining Nitro acceptance sequence is small but concrete:

1. Resolve or explicitly type the reboot proof gap; deploy the reviewed worker and verify authentication, observer close/reopen, shell restart, duplicate dispatch, explicit stop and truthful terminal status on real managed shutdown/reboot operations.
2. Rebuild the Linux sender with the reviewed colour patch; capture actual SDR frame flags and Wayland metadata, then verify guest reboot/reconnect, SSH/session persistence, input and audio.
3. Supply/seal the private Windows image and record its digest/build evidence; exercise the clean-before-dev GPU sequence, refusal of upward reuse, host reboot recovery, and host state after VM shutdown.
4. Complete render verification with authorized sudo credentials, rerun final host/guest convergence to changed=0, and perform the frozen-commit ISO/bootstrap replay. Exact commit freezing/publication remains the primary engineer's task; this review makes no Git mutations.

Large central files remain review risks: the GTK domain manager is roughly 4,941 lines, focused provenance 876, focus accent 1,107, and the connection opener 848 at inspection. The actionable process-lifetime defect above was fixed without refactoring them. Private legacy `privatestack-*` paths remain widespread across binaries, runtime/state interfaces and release tooling. They are compatibility debt, not a naming migration performed here.

Reviewer-authored changes only:

- `tools/hyperlabctl/hyperlabctl/providers/domains.py`: require known-unmanaged status for the legacy GPU identity fallback.
- `roles/host_desktop_common/files/privatestack-operation.py`: nonblocking observer sockets and explanatory comment.
- `tests/c9_independent_review_contract.py`: five behavioural regressions, using inert children and temporary sockets, no guest mutation.
- `verify.sh`: ignore binary files during shell-script discovery.
- `docs/c9-independent-review-2026-09-27.md`: this report.

The other uncommitted lifecycle, trust, RGB, UI and colour changes belong to the concurrent implementation work.

Validation: independent regressions 5/5 pass; revised lifecycle, integration and QML contracts pass; hyperlabctl custom harness reports 1,295 passed, zero failed; relevant VFIO, trust-model, desktop-action, Linux capture, headless-picker and hardware-gate contracts pass. Targeted Ruff passes. Both full verifier runs failed on generated bytecode sent to ShellCheck and on missing sudo credentials for render. The discovery defect was subsequently reproduced and fixed; the complete discovered ShellCheck set and five independent tests were rerun successfully. All other stages in the last full run passed. VERIFY remains FAIL because render is unverified, not because a render assertion failed. The last full log, preceding the discovery fix, is `/tmp/hyperlab-independent-review-verify-final.log`. `git diff --check` also reports a whitespace-only context line inside the nested colour patch; this reviewer did not rewrite that patch or its checksum.

Local evidence: `/tmp/hyperlab-independent-review-regressions-final.log`, `/tmp/hyperlab-independent-review-hyperlabctl.log`, `/tmp/hyperlab-colour-enum-evidence.txt`, and the verifier logs. Since the shared worktree changed during review, rerun the relevant gates after any subsequent implementation edits.
