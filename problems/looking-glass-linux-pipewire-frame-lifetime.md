# Looking Glass Linux PipeWire frame lifetime

## Symptom

The experimental Linux Looking Glass sender could initially capture the
managed `HEADLESS-0` output, then turn the client black under a real fullscreen
GPU workload. The sender terminated with `SIGSEGV` while copying a PipeWire
frame.

The failure was reproduced with the pinned Looking Glass build
`B7-263-g0140a3f6fb`, PipeWire 1.6.8 and the existing GCC 16 compatibility
patch.

## Evidence boundary

The guest compositor and workload were healthy at the failure boundary:
`HEADLESS-0` remained 1920x1080 at 144 Hz, `glmark2-wayland` was mapped
fullscreen and the RTX 3060 remained active.

The sender backtrace reached `pipewire_getFrame` and then
`framebuffer_write_avx2`. The faulting instruction read from the source frame
while another PipeWire thread was observed in `__munmap`.

The sender also repeatedly reported `pw_stream_disconnect called from wrong
context` during stream teardown and restart.

## Root cause

The pinned PipeWire backend used the threaded-loop wait/signal handshake
without keeping the thread-loop lock across the consumer frame lifetime.
`pipewire_getFrame` could therefore copy from the mapped PipeWire frame while
stream state or backing storage changed concurrently.

Stream disconnect and teardown were also performed outside the reviewed
thread-loop locking boundary.

## Fix

Keep the existing upstream commit pin and apply the reviewed
`pipewire-thread-loop-runtime.patch` only during the sender build.

The patch:

- holds the PipeWire thread-loop lock from the capture wait through
  `framebuffer_write`;
- acknowledges the producer and releases the lock only after the frame copy;
- serializes stream disconnect with the same loop lock;
- preserves the existing PipeWire-only and XCB-disabled build;
- does not add another per-frame staging copy;
- restores the pinned source after each build.

The exact reviewed runtime patch SHA256 is
`47e5ded356d684362b1b488c53203263879f231d330727cd379f551e7357c239`.

## Regression proof

The out-of-tree patched sender completed three fullscreen `glmark2-wayland`
runs with scores 6007, 6001 and 5716. Median score was 6001 and the observed
spread was 4.926 percent.

During the stress run:

- the sender remained alive through all three workloads;
- three independently captured Looking Glass window frames had distinct
  SHA256 values;
- no `called from wrong context` warning appeared;
- no `SIGSEGV` or fatal sender crash appeared;
- the sender completed a graceful shutdown;
- the guest lock and idle policy were restored after the transaction.

The production `/usr/local/bin/looking-glass-host` and the Ansible candidate
were intentionally left unchanged until this regression proof passed.

## Policy

The sender remains experimental and disabled by default. The runtime patch is
part of the pinned build provenance and must be hash-verified, checked against
the pinned source before application, recorded in `built-from.yml` and covered
by the guest hardware gate.
