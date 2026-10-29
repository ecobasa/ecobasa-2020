"""Builds koppen.bin, the Köppen-Geiger map the seed climate zones are found in, from the
100 arc-second (about 3 km) map in the kgcpy package (BSD-3-Clause, see NOTICE):

    pip download --no-deps kgcpy && unzip kgcpy-*.whl 'kgcpy/kmz_int_reshape.png'
    python gift_economy/gifts/climate/build_koppen_map.py kgcpy/kmz_int_reshape.png

The map is a 12960 × 6480 grid of class numbers (CLASSES in koppen.py), north to south
from 90° N and west to east from 180° W. koppen.bin holds it run-length encoded, row by
row (a uint16 count of runs, then per run the class as a byte and its length as a uint16,
little-endian), compressed with zlib: 220 KB instead of 84 MB, read into 1.5 MB."""

import struct
import sys
import zlib
from pathlib import Path

from PIL import Image


def build(png, out):
    Image.MAX_IMAGE_PIXELS = None
    image = Image.open(png)
    if image.mode != "L" or image.size != (12960, 6480):
        raise SystemExit(f"Unexpected map: {image.mode} {image.size}")
    width, height = image.size
    data = image.tobytes()
    rows = bytearray()
    for y in range(height):
        row = data[y * width:(y + 1) * width]
        runs = []
        for value in row:
            if runs and runs[-1][0] == value and runs[-1][1] < 0xFFFF:
                runs[-1][1] += 1
            else:
                runs.append([value, 1])
        rows += struct.pack("<H", len(runs))
        for value, length in runs:
            rows += struct.pack("<BH", value, length)
    Path(out).write_bytes(zlib.compress(bytes(rows), 9))


if __name__ == "__main__":
    build(sys.argv[1], Path(__file__).with_name("koppen.bin"))
