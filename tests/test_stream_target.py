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

    def test_a_saved_forwarder_reads_back(self):
        store = (ROOT / "src/fwd/store.cpp").read_text()
        self.assertIn('(key == "--pc" ? out.pc : out.app) = info.argv[i + 1];', store)
        self.assertIn('key == "--exit-after-game" || key == "--exit-after-stream"', store)


if __name__ == "__main__":
    unittest.main()
