"""A small QR code encoder (byte mode, error correction level M, versions 1–6) that returns SVG.

Enough for the pairing link a tablet scans; written here so runboard needs no extra dependency.
"""
from __future__ import annotations

# Level M: (error-correction codewords per block, blocks, data codewords per block); versions 1–6 have equal blocks.
BLOCKS = {1: (10, 1, 16), 2: (16, 1, 28), 3: (26, 1, 44), 4: (18, 2, 32), 5: (24, 2, 43), 6: (16, 4, 27)}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}

EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i], LOG[_x] = _x, _i
    _x = (_x << 1) ^ (0x11D if _x & 0x80 else 0)
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    return EXP[LOG[a] + LOG[b]] if a and b else 0


def _ecc(data: list[int], n: int) -> list[int]:
    gen = [1]
    for i in range(n):  # (x - a^0)(x - a^1)…(x - a^(n-1))
        gen = [a ^ _mul(b, EXP[i]) for a, b in zip(gen + [0], [0] + gen)]
    rem = list(data) + [0] * n
    for i in range(len(data)):
        c = rem[i]
        if c:
            for j, g in enumerate(gen):
                rem[i + j] ^= _mul(g, c)
    return rem[len(data):]


def _codewords(text: bytes, version: int) -> list[int]:
    ec, nblocks, per = BLOCKS[version]
    cap = nblocks * per
    bits = [0, 1, 0, 0] + [(len(text) >> i) & 1 for i in range(7, -1, -1)]
    for b in text:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    data = (data + [0xEC, 0x11] * cap)[:cap]
    blocks = [data[i * per:(i + 1) * per] for i in range(nblocks)]
    eccs = [_ecc(b, ec) for b in blocks]
    return [b[i] for i in range(per) for b in blocks] + [e[i] for i in range(ec) for e in eccs]


def _format_bits(mask: int) -> int:
    bits = mask  # level M is 00
    rem = bits
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (bits << 10 | rem) ^ 0x5412


def _matrix(version: int, words: list[int], mask: int) -> list[list[bool]]:
    n = 17 + 4 * version
    m = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(x, y, v):
        m[y][x], fn[y][x] = v, True

    for i in range(n):  # timing patterns
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # finders with their separators
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    d = max(abs(dx), abs(dy))
                    put(x, y, d not in (2, 4))
    pos = ALIGN[version]
    for i, ax in enumerate(pos):
        for j, ay in enumerate(pos):
            if (i, j) in ((0, 0), (0, len(pos) - 1), (len(pos) - 1, 0)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    f = _format_bits(mask)
    bit = lambda i: (f >> i) & 1 == 1
    for i in range(6):
        put(8, i, bit(i))
    put(8, 7, bit(6))
    put(8, 8, bit(7))
    put(7, 8, bit(8))
    for i in range(9, 15):
        put(14 - i, 8, bit(i))
    for i in range(8):
        put(n - 1 - i, 8, bit(i))
    for i in range(8, 15):
        put(8, n - 15 + i, bit(i))
    put(8, n - 8, True)  # dark module

    i, total = 0, len(words) * 8
    right = n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fn[y][x] and i < total:
                    m[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2
    rule = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0][mask]
    for y in range(n):
        for x in range(n):
            if not fn[y][x] and rule(x, y):
                m[y][x] = not m[y][x]
    return m


def _penalty(m: list[list[bool]]) -> int:
    n, p = len(m), 0
    finder = [(True, False, True, True, True, False, True, False, False, False, False)]
    finder.append(finder[0][::-1])
    for line in m + [list(c) for c in zip(*m)]:  # runs of five or more, finder look-alikes that confuse readers
        p += 40 * sum(tuple(line[i:i + 11]) in finder for i in range(n - 10))
        run = 1
        for a, b in zip(line, line[1:]):
            run = run + 1 if a == b else 1
            p += 3 if run == 5 else 1 if run > 5 else 0
    p += 3 * sum(m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1] for y in range(n - 1) for x in range(n - 1))
    dark = sum(map(sum, m)) * 100 // (n * n)
    return p + abs(dark - 50) // 5 * 10


def matrix(text: str) -> list[list[bool]]:
    data = text.encode("utf-8")
    version = next((v for v, (_, nb, per) in BLOCKS.items() if len(data) + 2 <= nb * per), None)
    if version is None:
        raise ValueError("Text too long for a pairing QR code")
    words = _codewords(data, version)
    return min((_matrix(version, words, k) for k in range(8)), key=_penalty)


def svg(text: str, scale: int = 6, quiet: int = 4) -> str:
    m = matrix(text)
    n = len(m) + 2 * quiet
    path = "".join(f"M{x + quiet},{y + quiet}h1v1h-1z" for y, row in enumerate(m) for x, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * scale}" height="{n * scale}" '
            f'shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
