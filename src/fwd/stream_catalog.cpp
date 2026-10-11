// ps5fwdgen - The PCs and apps a streaming client offers to forwarders.
// Copyright (C) 2026 heydemoura
// SPDX-License-Identifier: GPL-3.0-or-later

#include "fwd/stream_catalog.hpp"

#include "core/json.hpp"

#include <algorithm>
#include <cstdio>
#include <dirent.h>
#include <string_view>
#include <sys/stat.h>

namespace fwd
{

namespace
{

constexpr std::string_view kFormatPrefix = "prosperolight-forwarder-catalog/";

std::string lower(std::string_view text)
{
    std::string out(text);
    for (char &c : out)
        if (c >= 'A' && c <= 'Z')
            c = static_cast<char>(c - 'A' + 'a');
    return out;
}

bool is_file(const std::string &path)
{
    struct stat status;
    return ::stat(path.c_str(), &status) == 0 && S_ISREG(status.st_mode) && status.st_size > 0;
}

// A key names a file and a folder: nothing that leaves the catalog.
bool safe_key(std::string_view key)
{
    return !key.empty() && key.find('/') == std::string_view::npos && key != "." && key != "..";
}

bool read_pc(const std::string &root, const std::string &file, StreamPc &pc)
{
    const std::vector<unsigned char> bytes = read_stream_file(root + "/pcs/" + file, 4u << 20);
    json::Value document;
    if (bytes.empty() ||
        !json::parse(std::string_view(reinterpret_cast<const char *>(bytes.data()), bytes.size()),
                     document) ||
        !document.is_object())
        return false;
    if (document.get("format").as_string().substr(0, kFormatPrefix.size()) != kFormatPrefix)
        return false;
    pc.key = std::string(document.get("key").as_string());
    pc.address = std::string(document.get("address").as_string());
    pc.name = std::string(document.get("name").as_string(pc.address));
    pc.port = static_cast<int>(document.get("port").as_int());
    if (!safe_key(pc.key) || pc.address.empty())
        return false;
    for (const json::Value &entry : document.get("apps").items())
    {
        StreamApp app;
        app.id = entry.get("id").as_int();
        app.name = std::string(entry.get("name").as_string());
        if (app.name.empty())
            continue;
        const std::string poster =
            root + "/posters/" + pc.key + "/" + std::to_string(app.id) + ".png";
        if (is_file(poster))
            app.poster = poster;
        pc.apps.push_back(std::move(app));
    }
    return true;
}

} // namespace

std::vector<unsigned char> read_stream_file(const std::string &path, std::size_t max_bytes)
{
    std::vector<unsigned char> bytes;
    std::FILE *file = std::fopen(path.c_str(), "rb");
    if (file == nullptr)
        return bytes;
    unsigned char block[65536];
    std::size_t got = 0;
    while ((got = std::fread(block, 1, sizeof(block), file)) > 0)
    {
        if (bytes.size() + got > max_bytes)
        {
            bytes.clear();
            break;
        }
        bytes.insert(bytes.end(), block, block + got);
    }
    (void)std::fclose(file);
    return bytes;
}

std::vector<StreamPc> read_stream_catalog(const std::string &root)
{
    std::vector<StreamPc> pcs;
    DIR *directory = ::opendir((root + "/pcs").c_str());
    if (directory == nullptr)
        return pcs;
    while (const dirent *entry = ::readdir(directory))
    {
        const std::string file = entry->d_name;
        if (file.size() <= 5 || file.compare(file.size() - 5, 5, ".json") != 0)
            continue;
        StreamPc pc;
        if (read_pc(root, file, pc))
            pcs.push_back(std::move(pc));
    }
    ::closedir(directory);
    std::sort(pcs.begin(), pcs.end(),
              [](const StreamPc &a, const StreamPc &b)
              {
                  const std::string left = lower(a.name);
                  const std::string right = lower(b.name);
                  return left != right ? left < right : a.key < b.key;
              });
    return pcs;
}

std::string stream_pc_argument(const std::vector<StreamPc> &pcs, const StreamPc &pc)
{
    int same = 0;
    for (const StreamPc &other : pcs)
        if (lower(other.name) == lower(pc.name))
            ++same;
    if (same <= 1 && !pc.name.empty())
        return pc.name;
    // 47989 is Sunshine's default, which the address alone already means.
    return pc.port != 0 && pc.port != 47989 ? pc.address + ":" + std::to_string(pc.port)
                                            : pc.address;
}

int find_stream_pc(const std::vector<StreamPc> &pcs, const std::string &argument)
{
    if (argument.empty())
        return -1;
    const std::string wanted = lower(argument);
    for (std::size_t i = 0; i < pcs.size(); ++i)
        if (wanted == lower(pcs[i].address) ||
            wanted == lower(pcs[i].address + ":" + std::to_string(pcs[i].port)))
            return static_cast<int>(i);
    for (std::size_t i = 0; i < pcs.size(); ++i)
        if (wanted == lower(pcs[i].name))
            return static_cast<int>(i);
    return -1;
}

} // namespace fwd
