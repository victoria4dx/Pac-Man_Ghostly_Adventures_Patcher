"""
Patch logic for PAC-MAN and the Ghostly Adventures (PC, Steam build, SHA-256 a279a2d6...32d9d).

No GUI code here, so it can be tested on its own. Every option is rebuilt from the original
bytes on each apply, so options can be switched freely in any order. Nothing is written unless
the file is exactly the supported build (allowing only this tool's own patch sites to differ).
"""
import hashlib
import os
import struct
from dataclasses import dataclass

ORIG_SHA256 = "a279a2d634e7a34fc6f619ae185333d3bc3f6e8d3c6b94a69dd5258220232d9d"
ORIG_SIZE = 3639296
TICK_RATE = 600            # the game's fixed logic clock, in Hz
FPS_CHOICES = (30, 60, 120, 300, 600)   # 30 = original; each divides 600 so game speed stays correct
POOL_MB = 1024
FOV_MIN, FOV_MAX = 0.75, 1.50

# (file offset, original bytes, bytes that must sit immediately before it)
POOL_SITES = [  # imm32 of: mov esi/eax, 0x01400000   (20 MiB render-target budget)
    (0x027FDB, "00004001", "be"),
    (0x070ADC, "00004001", "b8"),
    (0x070B03, "00004001", "b8"),
]
FORCE_SITES = [  # mov eax,[0x6E9B50] -> jmp past the game's own (overwritten) budget values
    (0x070ACD, "a150", "751e"),
    (0x070AF4, "a150", "751e"),
]
FORCE_ON = bytes.fromhex("eb0c")
PERIOD_SITES = [  # doubles: seconds per frame for the game's three pacing modes
    (0x276410, "ad66d6aa7015a13f", ""),  # 1/29.97
    (0x276418, "ad66d6aa7015913f", ""),  # 1/59.94
    (0x276420, "039a410029a0a93f", ""),  # 1/19.98
]
TICK_SITES = [  # imm32 of: mov dword [0x689848], N   (logic ticks per rendered frame)
    (0x028D0C, "1e000000", "c70548986800"),
    (0x028D23, "0a000000", "c70548986800"),
    (0x028D3A, "14000000", "c70548986800"),
    (0x19784F, "1e000000", "c70548986800"),
    (0x197861, "0a000000", "c70548986800"),
    (0x197873, "14000000", "c70548986800"),
    (0x198E1A, "1e000000", "c70548986800"),
    (0x198E2C, "0a000000", "c70548986800"),
    (0x198E3E, "14000000", "c70548986800"),
]
# PresentationInterval = (fullscreen ? 0x80000001 : 0) + 0x80000000  ->  ONE in fullscreen,
# IMMEDIATE in windowed. "and" imm 0 + "add" imm 0x80000000 = always off; "add" imm 1 = always on.
VSYNC_AND_SITES = [(0x073199, "01000080", "25"), (0x073486, "01000080", "25")]
VSYNC_ADD_SITES = [(0x0731A7, "00000080", "05"), (0x07348B, "00000080", "05")]
BORDERLESS_SITES = [  # caption style 0x00CA0000 -> WS_POPUP, skip the border/caption enlargement
    (0x072EB5, "0000ca00", "81e2", "00000080"),
    (0x072EBE, "75", "84c0", "eb"),
    (0x073354, "75", "89442418", "eb"),
    (0x0733AF, "0000ca00", "0d", "00000080"),
    (0x073931, "75", "84db", "eb"),
    (0x073995, "0000ca00", "0d", "00000080"),
]
TOPMOST_SITES = [(0x072F07, "00", "68dc0166006a", "08")]   # only ever reverted by this tool

# Camera FOV routine at VA 0x419400 is redirected into unused padding at the end of .text.
# Cave layout (VA 0x65B610 / file 0x25AA10): float fov_scale, dword hp_enable, then code.
FOV_ENTRY_SITE = (0x018800, "558bec83e4", "")
CAVE_OFF, CAVE_LEN = 0x25AA10, 0x1F0
ENTRY_NEW = bytes.fromhex("e913222400")    # jmp 0x65B618
ENTRY_OLD = bytes.fromhex("e90b222400")    # jmp 0x65B610 (Hor+ routine from the earlier script)
CAVE_CODE = bytes.fromhex(
    "0000803f010000005589e583ec108b0883e140894df8d9e87408ddd8db4010da7014d95dfc837df8007445817d047b"
    "934100743cd90510b66500d9e8dff1ddd8742ed945086835fa0e3cd80c2483c404e80b2effffd80d10b66500e88036"
    "ffffdcc068e12e6542d80c2483c404d95d08d945086835fa0e3cd80c2483c404e8dd2dffffd95df4837df8007470d9"
    "45fcd9e8dff1ddd87365817d047b934100741fd945fc68398ee33fd8342483c404d9e8dff17309833d14b665000075"
    "09ddd8d94508d91feb1ad84df4d955f4e80f36ffffdcc068e12e6542d80c2483c404d91fd945f4d875fce8f535ffff"
    "dcc068e12e6542d80c2483c404d91eeb1fd945f4d84dfce8d935ffffdcc068e12e6542d80c2483c404d91fd94508d9"
    "1e89ec5dc20800")
ALL_SIMPLE_SITES = (POOL_SITES + FORCE_SITES + PERIOD_SITES + TICK_SITES + VSYNC_AND_SITES
                    + VSYNC_ADD_SITES + [t[:3] for t in BORDERLESS_SITES + TOPMOST_SITES]
                    + [FOV_ENTRY_SITE])


class UnsupportedBuild(Exception):
    pass


@dataclass
class Options:
    fps: int = 30
    borderless: bool = False
    vsync: str = "default"        # "default" (on in fullscreen only), "on", "off"
    hires_fix: bool = False
    hor_plus: bool = False
    fov_scale: float = 1.0


def _restore(data: bytes) -> bytes:
    buf = bytearray(data)
    for off, orig, _ in ALL_SIMPLE_SITES:
        ob = bytes.fromhex(orig)
        buf[off:off + len(ob)] = ob
    buf[CAVE_OFF:CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    return bytes(buf)


def validate(data: bytes) -> bytes:
    """Return the original bytes for data, or raise UnsupportedBuild."""
    if len(data) != ORIG_SIZE:
        raise UnsupportedBuild("This is not the supported PacMan.exe (size %d bytes, expected %d)."
                               % (len(data), ORIG_SIZE))
    for off, _, pre in ALL_SIMPLE_SITES:
        if pre and data[off - len(pre) // 2:off] != bytes.fromhex(pre):
            raise UnsupportedBuild("Unexpected code near offset 0x%X: this build is not supported." % off)
    base = _restore(data)
    if hashlib.sha256(base).hexdigest() != ORIG_SHA256:
        raise UnsupportedBuild("This PacMan.exe is a different build, or has changes this tool "
                               "did not make. Use Steam's \"Verify integrity of game files\" "
                               "to get a clean copy.")
    return base


def read_state(data: bytes) -> Options:
    o = Options()
    ticks = struct.unpack_from("<I", data, TICK_SITES[0][0])[0]
    if data[TICK_SITES[0][0]:TICK_SITES[0][0] + 4] != bytes.fromhex(TICK_SITES[0][1]) and ticks:
        o.fps = TICK_RATE // ticks
    o.borderless = all(data[off:off + len(new) // 2] == bytes.fromhex(new)
                       for off, _, _, new in BORDERLESS_SITES)
    and_imm = data[VSYNC_AND_SITES[0][0]:VSYNC_AND_SITES[0][0] + 4]
    add_imm = struct.unpack_from("<I", data, VSYNC_ADD_SITES[0][0])[0]
    if and_imm == bytes(4):
        o.vsync = "on" if add_imm == 1 else "off"
    o.hires_fix = struct.unpack_from("<I", data, POOL_SITES[0][0])[0] != 0x01400000
    entry = data[FOV_ENTRY_SITE[0]:FOV_ENTRY_SITE[0] + 5]
    if entry == ENTRY_NEW:
        o.fov_scale = round(struct.unpack_from("<f", data, CAVE_OFF)[0], 2)
        o.hor_plus = struct.unpack_from("<I", data, CAVE_OFF + 4)[0] != 0
    elif entry == ENTRY_OLD:
        o.hor_plus = True
    return o


def build(base: bytes, o: Options) -> bytes:
    if o.fps not in FPS_CHOICES:
        raise ValueError("Unsupported frame rate %r" % o.fps)
    if o.vsync not in ("default", "on", "off"):
        raise ValueError("Unsupported vsync mode %r" % o.vsync)
    fov = min(max(float(o.fov_scale), FOV_MIN), FOV_MAX)
    buf = bytearray(base)
    if o.fps != 30:
        for off, _, _ in PERIOD_SITES:
            struct.pack_into("<d", buf, off, 1.0 / o.fps)
        for off, _, _ in TICK_SITES:
            struct.pack_into("<I", buf, off, TICK_RATE // o.fps)
    if o.hires_fix:
        for off, _, _ in POOL_SITES:
            struct.pack_into("<I", buf, off, POOL_MB << 20)
        for off, _, _ in FORCE_SITES:
            buf[off:off + 2] = FORCE_ON
    if o.borderless:
        for off, _, _, new in BORDERLESS_SITES:
            nb = bytes.fromhex(new)
            buf[off:off + len(nb)] = nb
    if o.vsync != "default":
        for off, _, _ in VSYNC_AND_SITES:
            buf[off:off + 4] = bytes(4)
        if o.vsync == "on":
            for off, _, _ in VSYNC_ADD_SITES:
                struct.pack_into("<I", buf, off, 1)
    if o.hor_plus or abs(fov - 1.0) > 1e-6:
        buf[CAVE_OFF:CAVE_OFF + len(CAVE_CODE)] = CAVE_CODE
        struct.pack_into("<f", buf, CAVE_OFF, fov)
        struct.pack_into("<I", buf, CAVE_OFF + 4, 1 if o.hor_plus else 0)
        buf[FOV_ENTRY_SITE[0]:FOV_ENTRY_SITE[0] + 5] = ENTRY_NEW
    return bytes(buf)


def load(path: str):
    """Return (current bytes, original bytes, current Options)."""
    with open(path, "rb") as f:
        data = f.read()
    base = validate(data)
    return data, base, read_state(data)


def _write(path: str, content: bytes):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(content)
    try:
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def apply(path: str, o: Options) -> str:
    data, base, _ = load(path)
    backup = path + ".orig"
    if not os.path.exists(backup):
        with open(backup, "wb") as f:
            f.write(base)
    new = build(base, o)
    if new != data:
        _write(path, new)
    return backup


def restore(path: str) -> bool:
    data, base, _ = load(path)
    if data == base:
        return False
    _write(path, base)
    return True
