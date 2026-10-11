// ps5fwdgen - Picks one of a PC's apps for a streaming forwarder.
// Copyright (C) 2026 heydemoura
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The list is what the streaming client published (fwd/stream_catalog.hpp):
// one row per app with its box art, and the focused app's art at full size on
// the right. Box art is decoded a little at a time, only around the focus.

#include "app/screens/app_picker_screen.hpp"

#include "app/context.hpp"
#include "app/tile.hpp"
#include "ui/components/list.hpp"
#include "ui/fonts.hpp"

#include <GL/glcorearb.h>

#include <cstdint>
#include <cstdlib>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace fwd
{

namespace
{

constexpr hui::gfx::Rect kListBounds{96.0f, 300.0f, 1120.0f, 660.0f};
constexpr hui::gfx::Rect kArtBounds{1340.0f, 300.0f, 420.0f, 560.0f};
constexpr hui::gfx::Color kPlain{1.0f, 1.0f, 1.0f, 1.0f};
// Box art kept decoded on each side of the focus; each is a few megabytes.
constexpr int kArtWindow = 10;

class AppPickerScreen final : public Screen
{
  public:
    AppPickerScreen(Context &context, StreamPc pc, std::function<void(const StreamApp *)> on_pick)
        : pc_(std::move(pc)), on_pick_(std::move(on_pick))
    {
        restyle(context);
        list_.set_bounds(kListBounds);
        list_.set_active(true);
        list_.style.row_height = 92.0f;
        list_.style.leading_width = 76.0f;
        list_.leading = [this, &context](hui::ui::Canvas &canvas, const hui::gfx::Rect &row,
                                         const hui::ui::ListItem &item, int index, float focus)
        {
            (void)item;
            (void)focus;
            const hui::gfx::Rect art{row.x + 14.0f, row.y + 8.0f, 57.0f, row.h - 16.0f};
            const std::uint32_t texture = texture_at(index - 1);
            if (texture != 0)
                canvas.list.image(texture, art, hui::gfx::kFullUv, kPlain, 6.0f);
            else
                canvas.list.rounded_rect(art, 6.0f, context.theme.text_muted.with_alpha(0.18f));
        };

        std::vector<hui::ui::ListItem> items;
        hui::ui::ListItem typed;
        typed.title = "Type a name instead";
        typed.subtitle = "For an app added since ProsperoLight last listed this PC";
        typed.chevron = true;
        items.push_back(std::move(typed));
        for (const StreamApp &app : pc_.apps)
        {
            hui::ui::ListItem item;
            item.title = app.name;
            if (app.poster.empty())
                item.value = "no box art yet";
            items.push_back(std::move(item));
        }
        list_.set_items(std::move(items));
        list_.set_focus(pc_.apps.empty() ? 0 : 1, true);
    }

    ~AppPickerScreen() override
    {
        for (auto &[index, texture] : textures_)
            if (texture != 0)
                glDeleteTextures(1, &texture);
    }

    void restyle(Context &context) override
    {
        list_.style.theme = context.theme;
        list_.style.dividers = true;
    }

    void update(Context &context, const hui::InputFrame &input, float dt,
                hui::ui::Feedback &feedback) override
    {
        if (input.is_pressed(hui::Action::back))
        {
            context.pop();
            return;
        }
        if (list_.handle(input, feedback) == hui::ui::Event::activated)
        {
            const int index = list_.focus() - 1;
            if (on_pick_)
                on_pick_(index >= 0 && index < static_cast<int>(pc_.apps.size())
                             ? &pc_.apps[static_cast<std::size_t>(index)]
                             : nullptr);
            feedback.play(hui::audio::Cue::select);
            context.pop();
            return;
        }
        list_.update(dt);
        load_art(context);
    }

    bool draw(Context &context, hui::ui::Canvas &scene, hui::ui::Canvas &overlay) const override
    {
        (void)overlay;
        const hui::ui::Theme &theme = context.theme;
        const hui::gfx::Color text = theme.page_text.a > 0.0f ? theme.page_text : theme.text;
        const hui::gfx::Color muted =
            theme.page_text_muted.a > 0.0f ? theme.page_text_muted : theme.text_muted;
        hui::ui::text(scene.list, context.fonts.display, "Pick an app", 96.0f, 150.0f, 46.0f, text);
        hui::ui::text(scene.list, context.fonts.regular,
                      pc_.name + "  -  " + std::to_string(pc_.apps.size()) +
                          (pc_.apps.size() == 1 ? " app" : " apps") +
                          ", as ProsperoLight lists them",
                      96.0f, 214.0f, 26.0f, muted);
        list_.draw(scene);

        const int index = list_.focus() - 1;
        const std::uint32_t texture = texture_at(index);
        if (texture != 0)
            scene.list.image(texture, kArtBounds, hui::gfx::kFullUv, kPlain, 18.0f);
        else
        {
            scene.list.rounded_rect(kArtBounds, 18.0f, theme.text_muted.with_alpha(0.12f));
            hui::ui::text(scene.list, context.fonts.regular, index < 0 ? "" : "no box art yet",
                          kArtBounds.x + 110.0f, kArtBounds.y + kArtBounds.h * 0.5f, 26.0f, muted);
        }
        if (index >= 0 && index < static_cast<int>(pc_.apps.size()))
            hui::ui::text(scene.list, context.fonts.regular,
                          context.fonts.regular.font->fit(
                              pc_.apps[static_cast<std::size_t>(index)].name, 28.0f, kArtBounds.w),
                          kArtBounds.x, kArtBounds.y + kArtBounds.h + 44.0f, 28.0f, text);
        return false;
    }

    std::span<const hui::ui::Hint> hints() const override
    {
        static const hui::ui::Hint kHints[] = {
            {hui::ui::Button::cross, "Pick"},
            {hui::ui::Button::circle, "Back"},
        };
        return kHints;
    }

  private:
    std::uint32_t texture_at(int index) const
    {
        const auto found = textures_.find(index);
        return found == textures_.end() ? 0 : found->second;
    }

    // One picture a frame: the focused app first, then outwards. Pictures far
    // from the focus are let go.
    void load_art(Context &context)
    {
        const int focus = list_.focus() - 1;
        for (auto it = textures_.begin(); it != textures_.end();)
        {
            if (std::abs(it->first - focus) > kArtWindow)
            {
                if (it->second != 0)
                    glDeleteTextures(1, &it->second);
                it = textures_.erase(it);
            }
            else
                ++it;
        }
        for (int distance = 0; distance <= kArtWindow; ++distance)
            for (const int index : {focus + distance, focus - distance})
            {
                if (index < 0 || index >= static_cast<int>(pc_.apps.size()) ||
                    textures_.count(index) != 0)
                    continue;
                const StreamApp &app = pc_.apps[static_cast<std::size_t>(index)];
                std::uint32_t texture = 0;
                if (!app.poster.empty())
                {
                    const std::vector<unsigned char> bytes = read_stream_file(app.poster);
                    if (!bytes.empty())
                        texture =
                            upload_image_texture(context.renderer, bytes.data(), bytes.size());
                }
                textures_[index] = texture; // 0: tried, nothing to show
                if (!app.poster.empty())
                    return;
            }
    }

    StreamPc pc_;
    std::function<void(const StreamApp *)> on_pick_;
    mutable hui::ui::ListView list_;
    std::map<int, std::uint32_t> textures_;
};

} // namespace

std::unique_ptr<Screen> make_app_picker_screen(Context &context, StreamPc pc,
                                               std::function<void(const StreamApp *)> on_pick)
{
    return std::make_unique<AppPickerScreen>(context, std::move(pc), std::move(on_pick));
}

} // namespace fwd
