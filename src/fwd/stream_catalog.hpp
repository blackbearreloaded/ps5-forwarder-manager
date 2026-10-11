// ps5fwdgen - The PCs and apps a streaming client offers to forwarders.
// Copyright (C) 2026 heydemoura
// SPDX-License-Identifier: GPL-3.0-or-later
//
// ProsperoLight keeps the PCs it has paired, the apps each one lists and their
// box art under /data/prosperolight/forwarder (its docs/FORWARDER.md):
//
//   pcs/<key>.json            {"format", "key", "name", "address", "port",
//                              "apps": [{"id", "name"}]}
//   posters/<key>/<id>.png    one app's box art
//
// This reads them, so the edit screen can offer a choice instead of asking for
// names. A client that publishes nothing leaves the list empty and the form
// asks for the names as text.
#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace fwd
{

struct StreamApp
{
    long id = 0;
    std::string name;
    std::string poster; // the box art file; empty when the client has none yet
};

struct StreamPc
{
    std::string key;
    std::string name;
    std::string address;
    int port = 0;
    std::vector<StreamApp> apps;
};

inline constexpr char kStreamCatalogRoot[] = "/data/prosperolight/forwarder";

// Every PC with a readable file, by name. Empty when there is none.
std::vector<StreamPc> read_stream_catalog(const std::string &root = kStreamCatalogRoot);

// What --pc carries for this PC: its name, or its address when another PC in
// the list has the same name.
std::string stream_pc_argument(const std::vector<StreamPc> &pcs, const StreamPc &pc);

// The PC a --pc value names (by name or address, capitals ignored); -1 if none.
int find_stream_pc(const std::vector<StreamPc> &pcs, const std::string &argument);

// A whole file; empty when it is missing, unreadable or larger than max_bytes.
std::vector<unsigned char> read_stream_file(const std::string &path,
                                            std::size_t max_bytes = 16u << 20);

} // namespace fwd
