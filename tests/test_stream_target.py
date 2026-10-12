#!/usr/bin/env python3
# ps5fwdgen - A streaming target's arguments and the lists its client publishes.
# Copyright (C) 2026 heydemoura
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = r"""
#include "fwd/forwarder.hpp"
#include "fwd/stream_catalog.hpp"
#include <cassert>
using namespace fwd;
static std::string joined(const Forwarder &forwarder)
{
    std::string out;
    for (const Argument &argument : forwarder.resolved_args())
        out += argument.key + (argument.value.empty() ? "" : "=" + argument.value) + ";";
    return out;
}
int main(int, char **argv)
{
    assert(is_stream_target("PPSA99002") && !is_stream_target("PPSA99008") && !is_stream_target(""));
    Forwarder stream;
    stream.target = "PPSA99002";
    stream.pc = "Gaming-PC";
    stream.app = "Steam Big Picture";
    stream.rom = "ignored.nsp";
    stream.exit_after_game = true;
    assert(joined(stream) == "--pc=Gaming-PC;--app=Steam Big Picture;--exit-after-stream;");
    stream.pc.clear();
    stream.exit_after_game = false;
    assert(joined(stream) == "--app=Steam Big Picture;");
    Forwarder game;
    game.target = "PPSA99008";
    game.rom = "game.nsp";
    game.app = "ignored";
    game.exit_after_game = true;
    assert(joined(game) == "--rom=game.nsp;--exit-after-game;");

    const std::vector<StreamPc> pcs = read_stream_catalog(argv[1]);
    assert(pcs.size() == 3); // the broken and the foreign file are left out
    assert(pcs[0].name == "gaming-pc" && pcs[0].address == "192.168.1.50" && pcs[0].port == 47989);
    assert(pcs[0].apps.size() == 2 && pcs[0].apps[0].name == "Desktop");
    assert(pcs[0].apps[0].id == 1298491830 && pcs[0].apps[0].poster.empty());
    assert(pcs[0].apps[1].poster == std::string(argv[1]) + "/posters/192.168.1.50_47989/7.png");
    assert(read_stream_file(pcs[0].apps[1].poster).size() == 4);
    assert(read_stream_file(pcs[0].apps[1].poster, 3).empty());
    // Two PCs share a name: they are told apart by address, with the port when it is not the default.
    assert(pcs[1].name == "Office" && pcs[2].name == "Office");
    assert(stream_pc_argument(pcs, pcs[0]) == "gaming-pc");
    assert(stream_pc_argument(pcs, pcs[1]) == "192.168.1.60");
    assert(stream_pc_argument(pcs, pcs[2]) == "192.168.1.61:48989");
    assert(find_stream_pc(pcs, "Gaming-PC") == 0 && find_stream_pc(pcs, "192.168.1.61:48989") == 2);
    assert(find_stream_pc(pcs, "192.168.1.60") == 1 && find_stream_pc(pcs, "") == -1);
    assert(find_stream_pc(pcs, "Nowhere") == -1);
    assert(read_stream_catalog(std::string(argv[1]) + "/missing").empty());
    return 0;
}
"""


ICON_PROGRAM = r"""
#include "fwd/image.hpp"
#include <cassert>
#include <cstring>
#include <vector>
// A 24-bit BMP, 60 wide and 80 tall: plain grey with a white band on rows first..last.
static std::vector<unsigned char> poster(int first, int last)
{
    const int w = 60, h = 80;
    std::vector<unsigned char> bmp(54 + w * h * 3, 0);
    bmp[0] = 'B'; bmp[1] = 'M';
    const unsigned size = static_cast<unsigned>(bmp.size());
    std::memcpy(&bmp[2], &size, 4);
    bmp[10] = 54; bmp[14] = 40; bmp[18] = w; bmp[22] = h; bmp[26] = 1; bmp[28] = 24;
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x)
        {
            // Stripes inside the band, so the band is detail and not just a lighter area.
            const bool band = y >= first && y <= last;
            const unsigned char value = band ? (x % 6 < 3 ? 255 : 0) : 90;
            unsigned char *p = &bmp[54 + ((h - 1 - y) * w + x) * 3];
            p[0] = p[1] = p[2] = value;
        }
    return bmp;
}
// The middle row of the band in the 512-pixel icon: where its column 1 is brightest.
static int band_middle(const std::vector<unsigned char> &bmp)
{
    const std::vector<unsigned char> png = fwd::make_poster_icon_png(bmp.data(), bmp.size());
    int w = 0, h = 0;
    std::vector<unsigned char> rgba;
    assert(!png.empty() && fwd::decode_image(png.data(), png.size(), w, h, rgba));
    assert(w == 512 && h == 512);
    int first = -1, last = -1;
    for (int y = 0; y < h; ++y)
        if (rgba[(y * w + 8) * 4] > 200)
        {
            if (first < 0)
                first = y;
            last = y;
        }
    assert(first >= 0);
    return (first + last) / 2;
}
int main()
{
    // Artwork above the middle of a plain poster ends up in the middle of the tile. A cut
    // from the middle would leave it a third of the way down.
    const int high = band_middle(poster(26, 35));
    assert(high > 256 - 24 && high < 256 + 24);
    // Artwork low on the poster too.
    const int low = band_middle(poster(45, 54));
    assert(low > 256 - 24 && low < 256 + 24);
    // Artwork over the whole poster: cut from the middle, as before.
    const std::vector<unsigned char> full = poster(0, 79);
    assert(fwd::make_poster_icon_png(full.data(), full.size()) ==
           fwd::make_icon_png(full.data(), full.size()));
    assert(fwd::make_poster_icon_png(nullptr, 0).empty());
    return 0;
}
"""


def pc(key, name, address, port, apps):
    return json.dumps({"format": "prosperolight-forwarder-catalog/1", "key": key, "name": name,
                       "address": address, "port": port, "apps": apps})


class StreamTargetTests(unittest.TestCase):
    def test_arguments_and_published_lists(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            catalog = folder / "forwarder"
            (catalog / "pcs").mkdir(parents=True)
            (catalog / "posters/192.168.1.50_47989").mkdir(parents=True)
            (catalog / "posters/192.168.1.50_47989/7.png").write_bytes(b"\x89PNG")
            (catalog / "pcs/192.168.1.50_47989.json").write_text(pc(
                "192.168.1.50_47989", "gaming-pc", "192.168.1.50", 47989,
                [{"id": 1298491830, "name": "Desktop"}, {"id": 7, "name": "Steam Big Picture"},
                 {"id": 9, "name": ""}]))
            (catalog / "pcs/192.168.1.60_47989.json").write_text(
                pc("192.168.1.60_47989", "Office", "192.168.1.60", 47989, []))
            (catalog / "pcs/192.168.1.61_48989.json").write_text(
                pc("192.168.1.61_48989", "Office", "192.168.1.61", 48989, []))
            (catalog / "pcs/broken.json").write_text("{\"format\": ")
            (catalog / "pcs/foreign.json").write_text(json.dumps({"format": "other/1"}))
            (catalog / "pcs/escape.json").write_text(pc("../x", "Bad", "10.0.0.1", 1, []))
            (catalog / "pcs/notes.txt").write_text("not a PC")
            (folder / "check.cpp").write_text(PROGRAM)
            include = ROOT / "external/ps5-forwarder-format/include"
            subprocess.run([compiler, "-std=c++20", "-I" + str(ROOT / "src"), "-I" + str(include),
                            "-c", str(ROOT / "src/fwd/forwarder.cpp"), "-o",
                            str(folder / "forwarder.o")], check=True)
            subprocess.run([shutil.which("clang") or "gcc", "-I" + str(include), "-c",
                            str(ROOT / "external/ps5-forwarder-format/src/psfwd.c"), "-o",
                            str(folder / "psfwd.o")], check=True)
            subprocess.run([compiler, "-std=c++20", "-I" + str(ROOT / "src"), "-I" + str(include),
                            str(folder / "check.cpp"), str(folder / "forwarder.o"),
                            str(folder / "psfwd.o"),
                            str(ROOT / "src/fwd/stream_catalog.cpp"), str(ROOT / "src/core/json.cpp"),
                            "-o", str(folder / "check")],
                           check=True)
            subprocess.run([str(folder / "check"), str(catalog)], check=True)

    def test_box_art_icon_is_cut_around_the_artwork(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "check.cpp").write_text(ICON_PROGRAM)
            subprocess.run([compiler, "-std=c++20", "-w", "-I" + str(ROOT / "src"), "-I" + str(ROOT),
                            str(folder / "check.cpp"), str(ROOT / "src/fwd/image.cpp"), "-o",
                            str(folder / "check")], check=True)
            subprocess.run([str(folder / "check")], check=True)

    def test_a_saved_forwarder_reads_back(self):
        store = (ROOT / "src/fwd/store.cpp").read_text()
        self.assertIn('(key == "--pc" ? out.pc : out.app) = info.argv[i + 1];', store)
        self.assertIn('key == "--exit-after-game" || key == "--exit-after-stream"', store)


if __name__ == "__main__":
    unittest.main()
