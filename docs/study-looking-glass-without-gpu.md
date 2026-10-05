# Study: Looking Glass as the everyday window without a GPU

Roadmap milestone 11 asks whether Looking Glass could be the everyday window
for Linux Machines that have no passed-through GPU, with SPICE kept for
recovery. This page records what the repository and its pinned build allow
today, what would change, and the experiment that would decide it. Nothing
here is built.

## What exists

- One Looking Glass transport for VFIO Machines: the guest's Linux sender
  captures the Hyprland session through PipeWire and writes frames into an
  IVSHMEM region; on the host that region is `/dev/kvmfr0`, one static
  device of `hyperlab_looking_glass_shm_mb` (64 MiB for 1920×1080, from
  width × height × 4 bytes × 2 frames + 10 MiB, rounded up to a power of
  two; `group_vars/all/looking-glass.yml`).
- The client reads frames from that device and sends keyboard and pointer
  input over the domain's own SPICE UNIX socket (`spice:input=yes`,
  `input:captureOnly=yes`). SPICE therefore stays even for VFIO Machines:
  as the input channel, not as the picture.
- A Machine without a GPU (`workstation-dev-standard`) is shown today through
  the SPICE console (virt-viewer), labelled the recovery console.

## What a GPU-less Machine would need

1. **A frame source in the guest.** The Linux sender captures the
   compositor's output, not the GPU: on a virtio-gpu or emulated VGA guest,
   Hyprland renders with virgl or llvmpipe and PipeWire capture still
   works. Rendering cost moves to the host CPU; a desktop at 60 Hz is the
   question, not whether it works.
2. **One shared-memory region per running Machine.** `kvmfr` creates one
   device per entry of `static_size_mb` (for example `64,64,64` gives
   `/dev/kvmfr0` to `/dev/kvmfr2`). Each Machine's domain must name its own
   device and its client must open only that one. The host would assign a
   device index per running Machine, under the same lock that assigns the
   GPU, and the domain projection would carry it.
3. **The same host frame.** The window is a Looking Glass client like
   today's, so the focused-surface resolver already names it by PID; the
   frame and provenance need no new mechanism.
4. **Memory.** 64 MiB of locked shared memory per running Machine, beside
   its guest RAM.

## Windows

The Windows host application captures through DXGI desktop duplication,
which needs a display adapter with a desktop. Without a GPU this means an
indirect display driver, which upstream treats as experimental. Windows
Machines stay on the GPU path.

## The experiment

On Nitro, with the GPU left to `dev-01`:

1. give `kvmfr` two devices (`static_size_mb=64,64`) and a standard
   `arch-dev` domain an IVSHMEM device on `/dev/kvmfr1`;
2. start the Linux sender in that guest and the client on `/dev/kvmfr1`;
3. measure host CPU and frame rate for an idle desktop, a terminal scrolling
   and a browser video, against the SPICE console of the same Machine.

If the client stays smooth at a CPU cost the operator accepts, the change is
a per-Machine device index in the projection and the domain template, and
SPICE becomes recovery and input only. If not, SPICE stays the window for
GPU-less Machines.
