# SPDX-License-Identifier: MIT
"""Modern Looks: genre-oriented presets built on the full control set
(tone, HSL, colour grading, detail, skin). Pure data, no imports."""

_BW = [0.26, 0.55, 0.19]


def _p(name, family, description, **kw):
    d = {"name": name, "family": family, "process": "Modern Look", "description": description}
    d.update(kw)
    return d


def _bw(name, description, **kw):
    kw.setdefault("grain_profile", "cubic")
    return _p(name, "B&W Modern", description, monochrome=True, mono_weights=_BW, saturation=100, **kw)


MODERN_PRESETS = [
    # Portrait
    _p("Clean Portrait", "Portrait", "Natural skin, gentle contrast, crisp eyes.",
       contrast=6, highlights=-18, shadows=12, vibrance=8, temperature=4, clarity=-6,
       skin_smooth=18, skin_warmth=6, hsl_orange_sat=-6, hsl_orange_lum=6, hsl_red_sat=-8,
       sharpen=38, sharpen_masking=55, nr_luma=12),
    _p("Warm Editorial", "Portrait", "Warm magazine tones with a soft matte lift.",
       temperature=12, tint=3, contrast=12, saturation=96, fade=6, hsl_orange_sat=-4,
       cg_shadow_hue=28, cg_shadow_sat=14, cg_highlight_hue=42, cg_highlight_sat=10,
       sharpen=30, sharpen_masking=40, grain=6),
    _p("Soft Glow Beauty", "Portrait", "Dreamy, flattering skin with a gentle bloom.",
       clarity=-14, bloom=10, highlights=-22, shadows=18, skin_smooth=28, vibrance=6, fade=4,
       highlight_rolloff=40, sharpen=25, sharpen_masking=60),
    _p("Moody Dark Portrait", "Portrait", "Low-key skin, cool shadows, warm highlights.",
       exposure=-0.25, contrast=22, blacks=-14, shadows=-6, saturation=90, clarity=8, vignette=18,
       cg_shadow_hue=200, cg_shadow_sat=18, cg_highlight_hue=38, cg_highlight_sat=12, hsl_orange_lum=-4,
       sharpen=34, sharpen_masking=50),
    _p("Studio High Key", "Portrait", "Bright, clean and airy studio look.",
       exposure=0.35, contrast=4, whites=14, blacks=10, highlights=-10, shadows=24, saturation=94,
       skin_brightness=4, sharpen=30, sharpen_masking=45),
    _p("Golden Hour Skin", "Portrait", "Sun-kissed warmth with luminous highlights.",
       temperature=18, exposure=0.1, highlights=-20, vibrance=10, bloom=6,
       cg_highlight_hue=38, cg_highlight_sat=22, cg_shadow_hue=15, cg_shadow_sat=10,
       hsl_orange_sat=6, hsl_yellow_hue=-8, sharpen=28, sharpen_masking=45),
    # Landscape
    _p("Vivid Landscape", "Landscape", "Punchy colour and detail with controlled highlights.",
       contrast=14, clarity=16, dehaze=12, vibrance=20, saturation=104, highlights=-24, shadows=20,
       hsl_green_hue=-8, hsl_green_sat=8, hsl_blue_sat=10, hsl_blue_lum=-8,
       sharpen=60, sharpen_radius=1.0, sharpen_masking=35, nr_luma=8, defringe=25),
    _p("Alpine Cool", "Landscape", "Crisp cool mountain light.",
       temperature=-12, tint=-2, contrast=12, dehaze=14, clarity=14, hsl_blue_sat=12, hsl_aqua_sat=10,
       hsl_green_sat=-6, cg_shadow_hue=215, cg_shadow_sat=16, cg_highlight_hue=200, cg_highlight_sat=6,
       sharpen=55, sharpen_masking=35, defringe=20),
    _p("Desert Warm", "Landscape", "Sun-baked earth tones against deep skies.",
       temperature=20, tint=4, contrast=10, dehaze=10, hsl_orange_sat=10, hsl_yellow_sat=6,
       hsl_blue_lum=-10, hsl_blue_sat=8, cg_shadow_hue=20, cg_shadow_sat=12,
       sharpen=50, sharpen_masking=35),
    _p("Forest Green Rich", "Landscape", "Deep, natural greens with lifted shadows.",
       contrast=10, clarity=10, shadows=14, vibrance=12, hsl_green_sat=10, hsl_green_lum=-8,
       hsl_yellow_hue=-10, hsl_yellow_sat=4, cg_shadow_hue=160, cg_shadow_sat=10,
       sharpen=50, sharpen_masking=35),
    _p("Misty Morning", "Landscape", "Soft, low-contrast haze with cool shadows.",
       dehaze=-14, contrast=-8, highlights=-10, shadows=16, fade=10, saturation=90, temperature=-4,
       cg_shadow_hue=210, cg_shadow_sat=8, cg_highlight_hue=45, cg_highlight_sat=6, clarity=-4, bloom=8),
    _p("Golden Hour Landscape", "Landscape", "Warm light, teal-leaning shadows.",
       temperature=16, contrast=12, highlights=-22, shadows=16, dehaze=8, vibrance=14, bloom=5,
       cg_highlight_hue=38, cg_highlight_sat=18, cg_shadow_hue=240, cg_shadow_sat=12, hsl_blue_lum=-6,
       sharpen=48, sharpen_masking=35),
    # Street / city
    _p("Gritty Street", "Street", "High-contrast documentary texture.",
       contrast=24, clarity=18, texture=14, saturation=86, blacks=-10, highlights=-10, grain=18,
       grain_size=0.5, vignette=14, sharpen=62, sharpen_radius=1.1, sharpen_masking=25),
    _p("Muted Urban", "Street", "Desaturated city tones with a cool-warm split.",
       saturation=78, contrast=14, vibrance=-4, fade=8, clarity=10, grain=8,
       cg_shadow_hue=190, cg_shadow_sat=10, cg_highlight_hue=40, cg_highlight_sat=8,
       sharpen=45, sharpen_masking=30),
    _p("Neon Night City", "Street", "Electric blues and magentas with glowing lights.",
       contrast=16, saturation=108, vibrance=14, blacks=-12, bloom=12, halation=10, grain=10,
       cg_shadow_hue=235, cg_shadow_sat=24, cg_highlight_hue=320, cg_highlight_sat=14,
       hsl_magenta_sat=10, hsl_blue_sat=12, nr_luma=25, nr_color=25, sharpen=36, sharpen_masking=40),
    _p("Blue Hour", "Street", "Deep twilight blues with warm window light.",
       temperature=-10, tint=-2, contrast=14, exposure=0.1, bloom=8,
       cg_shadow_hue=225, cg_shadow_sat=20, cg_highlight_hue=30, cg_highlight_sat=10,
       nr_luma=20, nr_color=20, sharpen=38, sharpen_masking=40),
    # Product / food / interiors
    _p("Food Fresh", "Product & Food", "Appetising colour, clean light and texture.",
       temperature=6, vibrance=18, saturation=106, contrast=10, clarity=12, shadows=12, texture=10,
       hsl_red_sat=8, hsl_orange_sat=8, hsl_yellow_sat=8, hsl_green_sat=6,
       sharpen=55, sharpen_masking=30),
    _p("Product Clean", "Product & Food", "Neutral, bright and razor sharp.",
       contrast=8, whites=12, blacks=-4, saturation=98, clarity=14, texture=16, dehaze=4,
       sharpen=70, sharpen_radius=0.9, sharpen_masking=30, defringe=30),
    _p("Cafe Warm", "Product & Food", "Cosy warm interior with a soft fade.",
       temperature=10, saturation=92, fade=8, contrast=8, vignette=10, clarity=-2, grain=8,
       cg_shadow_hue=25, cg_shadow_sat=12, cg_highlight_hue=40, cg_highlight_sat=10),
    _p("Clean Real Estate", "Product & Food", "Bright, level interiors with open shadows.",
       exposure=0.25, whites=12, shadows=26, highlights=-18, contrast=10, clarity=12, dehaze=8,
       saturation=104, temperature=2, sharpen=60, sharpen_masking=25, defringe=20),
    # Wedding
    _p("Airy Wedding", "Wedding", "Light, romantic and soft.",
       exposure=0.3, contrast=-2, highlights=-14, shadows=22, whites=8, blacks=6, saturation=90,
       vibrance=4, fade=6, temperature=3, bloom=8, skin_smooth=14,
       cg_shadow_hue=200, cg_shadow_sat=6, cg_highlight_hue=40, cg_highlight_sat=8,
       sharpen=28, sharpen_masking=50),
    _p("Timeless Wedding", "Wedding", "Classic, natural colour with gentle depth.",
       contrast=10, saturation=92, highlights=-16, shadows=14, fade=5, vignette=8, grain=6,
       skin_smooth=12, cg_highlight_hue=40, cg_highlight_sat=10, sharpen=32, sharpen_masking=45),
    # Cinematic / colour
    _p("Teal & Orange Blockbuster", "Cinematic Grade", "Classic complementary grade.",
       contrast=16, vibrance=6, vignette=12, grain=6, halation=6,
       cg_shadow_hue=190, cg_shadow_sat=26, cg_highlight_hue=35, cg_highlight_sat=22,
       hsl_orange_sat=6, sharpen=35, sharpen_masking=40),
    _p("Pastel Dream", "Cinematic Grade", "Soft pastels with a lifted, dreamy bloom.",
       exposure=0.2, saturation=86, contrast=-6, fade=12, bloom=10, highlights=-10, shadows=14,
       cg_shadow_hue=280, cg_shadow_sat=10, cg_highlight_hue=20, cg_highlight_sat=8),
    _p("Autumn Amber", "Cinematic Grade", "Rich ambers and rusts.",
       temperature=14, contrast=12, vibrance=10, hsl_orange_sat=12, hsl_yellow_sat=10, hsl_red_sat=6,
       hsl_green_hue=-14, cg_shadow_hue=15, cg_shadow_sat=14, sharpen=45, sharpen_masking=35),
    _p("Matte Film Fade", "Cinematic Grade", "Lifted blacks and a gentle film grain.",
       fade=18, contrast=8, blacks=10, saturation=94, grain=10,
       cg_shadow_hue=210, cg_shadow_sat=8, cg_highlight_hue=45, cg_highlight_sat=8),
    # B&W
    _bw("Silver Documentary", "Classic punchy black and white.", contrast=20, clarity=14, grain=16,
        blacks=-8, vignette=12, sharpen=55, sharpen_masking=30),
    _bw("Soft Fine Art B&W", "Gentle tonality for portraits and still life.", contrast=6, highlights=-18,
        shadows=16, fade=8, grain=6, bloom=6, clarity=-6),
    _bw("High Contrast Noir", "Deep blacks and bright highlights.", contrast=40, blacks=-16, whites=10,
        clarity=16, vignette=22, grain=14),
    _bw("Matte Mono", "Lifted blacks, calm and modern.", fade=14, contrast=10, highlights=-8, grain=8),
]
