// ps5fwdgen - Picks one of a PC's apps for a streaming forwarder.
// Copyright (C) 2026 heydemoura
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "app/screen.hpp"
#include "fwd/stream_catalog.hpp"

#include <functional>
#include <memory>

namespace fwd
{
struct Context;

// Lists the PC's apps with their box art. on_pick gets the chosen app, or
// nullptr when the player would rather type a name.
std::unique_ptr<Screen> make_app_picker_screen(Context &context, StreamPc pc,
                                               std::function<void(const StreamApp *)> on_pick);
} // namespace fwd
