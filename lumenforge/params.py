# SPDX-License-Identifier: MIT
"""Parameter model: defaults, slider specs, groups and export formats."""

from .engine import CG_RANGES, HR, HSL_BANDS


DEF = {"exposure":0,"contrast":0,"gamma":1,"temperature":0,"tint":0,
       "saturation":100,"vibrance":0,"highlights":0,"shadows":0,
       "whites":0,"blacks":0,"clarity":0,"texture":0,"dehaze":0,"distortion":0,"defringe":0,"sharpen":0,"sharpen_radius":1.0,"sharpen_masking":0,"nr_luma":0,"nr_color":0,
       "grain":0,"grain_size":.45,"grain_profile":"tgrain","halation":0,
       "halation_color":list(HR),"bloom":0,"highlight_rolloff":0,"fade":0,
       "vignette":0,"vignette_feather":.72,"monochrome":False,
       "mono_weights":None,"film_curve_contrast":1,"film_shoulder":.12,
       "scene_prep":True,"print_stock":False,"print_strength":1,
       "skin_warmth":0,"skin_brightness":0,"skin_saturation":0,
       "skin_tan":0,"skin_smooth":0,"skin_clarity":0,
       "tone_curve_pts":{"rgb":[(0.0,0.0),(1.0,1.0)],"r":[(0.0,0.0),(1.0,1.0)],
                        "g":[(0.0,0.0),(1.0,1.0)],"b":[(0.0,0.0),(1.0,1.0)]},
       **{f"hsl_{b}_{c}":0 for b in HSL_BANDS for c in ("hue","sat","lum")},
       **{f"cg_{r}_hue":0 for r in CG_RANGES},
       **{f"cg_{r}_sat":0 for r in CG_RANGES},
       **{f"cg_{r}_lum":0 for r in CG_RANGES},
       "cg_global_hue":0,"cg_global_sat":0,"cg_global_lum":0,
       "cg_blending":50}


SPEC = [
("exposure","Exposure",-3,3,"{:+.2f}"),("contrast","Contrast",-100,100,"{:+.0f}"),
("gamma","Gamma",.2,3,"{:.2f}"),("highlights","Highlights",-100,100,"{:+.0f}"),
("shadows","Shadows",-100,100,"{:+.0f}"),("whites","Whites",-100,100,"{:+.0f}"),
("blacks","Blacks",-100,100,"{:+.0f}"),("temperature","Temperature",-100,100,"{:+.0f}"),
("tint","Tint",-100,100,"{:+.0f}"),("saturation","Saturation",0,200,"{:.0f}"),
("vibrance","Vibrance",-100,100,"{:+.0f}"),
("skin_warmth","Skin Warmth",-100,100,"{:+.0f}"),
("skin_brightness","Skin Brightness",-100,100,"{:+.0f}"),
("skin_saturation","Skin Saturation",-100,100,"{:+.0f}"),
("skin_tan","Skin Tan",-100,100,"{:+.0f}"),
("skin_smooth","Skin Smoothness",0,100,"{:.0f}"),
("skin_clarity","Skin Clarity",-100,100,"{:+.0f}"),
("clarity","Clarity",-100,100,"{:+.0f}"),("texture","Texture",-100,100,"{:+.0f}"),
("dehaze","Dehaze",-100,100,"{:+.0f}"),("distortion","Distortion",-100,100,"{:+.0f}"),("defringe","Defringe",0,100,"{:.0f}"),("sharpen","Sharpening",0,150,"{:.0f}"),("sharpen_radius","Sharp Radius",0.5,3.0,"{:.1f}"),("sharpen_masking","Sharp Masking",0,100,"{:.0f}"),("nr_luma","Noise Reduction",0,100,"{:.0f}"),("nr_color","Color Noise",0,100,"{:.0f}"),
("highlight_rolloff","Highlight Rolloff",0,100,"{:.0f}"),
("halation","Halation",0,100,"{:.0f}"),("bloom","Bloom",0,100,"{:.0f}"),
("fade","Fade",0,100,"{:.0f}"),("grain","Grain",0,100,"{:.0f}"),
("grain_size","Grain Size",.20,.90,"{:.2f}"),
("vignette","Vignette",-100,100,"{:+.0f}"),
("vignette_feather","Vignette Feather",.35,1,"{:.2f}")]


_HSL_LABELS = {"red":"Red","orange":"Orange","yellow":"Yellow",
              "green":"Green","aqua":"Aqua","blue":"Blue",
              "purple":"Purple","magenta":"Magenta"}


for _b in HSL_BANDS:
    for _c, _cl in (("hue","Hue"),("sat","Saturation"),("lum","Luminance")):
        SPEC.append((f"hsl_{_b}_{_c}", f"{_HSL_LABELS[_b]} {_cl}",
                    -100, 100, "{:+.0f}"))


_CG_LABELS = {"shadow":"Shadows","midtone":"Midtones","highlight":"Highlights"}


for _r in CG_RANGES:
    SPEC.append((f"cg_{_r}_hue", f"{_CG_LABELS[_r]} Hue", 0, 360, "{:.0f}"))
    SPEC.append((f"cg_{_r}_sat", f"{_CG_LABELS[_r]} Saturation", 0, 100, "{:.0f}"))
    SPEC.append((f"cg_{_r}_lum", f"{_CG_LABELS[_r]} Luminance", -100, 100, "{:+.0f}"))


SPEC.append(("cg_global_hue", "Global Hue", 0, 360, "{:.0f}"))


SPEC.append(("cg_global_sat", "Global Saturation", 0, 100, "{:.0f}"))


SPEC.append(("cg_global_lum", "Global Luminance", -100, 100, "{:+.0f}"))


SPEC.append(("cg_blending", "Blending", 0, 100, "{:.0f}"))


PARAM_INFO = {
    "exposure": "روشنایی کلی تصویر را مثل دیافراگم دوربین تغییر می‌دهد. "
                "مقدار مثبت عکس را روشن‌تر و مقدار منفی تیره‌تر می‌کند؛ "
                "این تنظیم به‌صورت یکنواخت روی همه‌ی تون‌ها (سایه، میان‌تون، هایلایت) اثر می‌گذارد.",
    "contrast": "فاصله‌ی بین تیره‌ترین و روشن‌ترین نقاط تصویر را حول نقطه‌ی "
                "خاکستری میانی تنظیم می‌کند. مقدار مثبت تصویر را پرکنتراست‌تر "
                "(سایه‌ها تیره‌تر، هایلایت‌ها روشن‌تر) و مقدار منفی آن را نرم‌تر و صاف‌تر می‌کند.",
    "gamma": "منحنی روشنایی تصویر را به‌صورت توانی (gamma) خم می‌کند. "
             "عدد کمتر از ۱ میان‌تون‌ها را روشن‌تر و عدد بیشتر از ۱ آن‌ها را "
             "تیره‌تر نشان می‌دهد، بدون اینکه سیاه و سفید مطلق تصویر تغییر کند.",
    "highlights": "فقط روی روشن‌ترین قسمت‌های تصویر (هایلایت‌ها) اثر می‌گذارد. "
                  "مقدار منفی برای بازگرداندن جزئیات نواحی سوخته و روشن استفاده می‌شود؛ "
                  "مقدار مثبت آن‌ها را روشن‌تر می‌کند.",
    "shadows": "فقط روی تیره‌ترین قسمت‌های تصویر (سایه‌ها) اثر می‌گذارد. "
               "مقدار مثبت جزئیات پنهان در سایه‌ها را باز می‌کند؛ مقدار منفی "
               "سایه‌ها را عمیق‌تر و تیره‌تر می‌کند.",
    "whites": "نقطه‌ی سفید مطلق تصویر را تنظیم می‌کند — یعنی مشخص می‌کند از "
              "کجا به بعد یک ناحیه کاملاً سفید و بدون جزئیات دیده شود. برای "
              "کنترل دقیق‌تر روشن‌ترین لبه‌ی تصویر به‌کار می‌رود.",
    "blacks": "نقطه‌ی سیاه مطلق تصویر را تنظیم می‌کند — یعنی مشخص می‌کند از "
              "کجا به بعد یک ناحیه کاملاً سیاه و بدون جزئیات دیده شود. برای "
              "کنترل دقیق‌تر عمق سایه‌های تصویر به‌کار می‌رود.",
    "temperature": "دمای رنگ تصویر (وایت بالانس) را روی محور آبی↔نارنجی تنظیم "
                   "می‌کند. مقدار منفی تصویر را سردتر و آبی‌تر، مقدار مثبت آن "
                   "را گرم‌تر و نارنجی‌تر می‌کند. از دکمه‌های Pick Gray Point یا "
                   "Auto WB هم می‌توان برای تنظیم خودکار آن استفاده کرد.",
    "tint": "رنگ تصویر را روی محور سبز↔بنفش (مکمل Temperature) تنظیم می‌کند. "
            "معمولاً برای خنثی کردن کست رنگی سبز یا بنفش نور مصنوعی "
            "(مثل نور فلورسنت) به‌کار می‌رود.",
    "saturation": "میزان اشباع رنگ در کل تصویر را به‌صورت یکنواخت تغییر می‌دهد. "
                  "۱۰۰ حالت خنثی است؛ عدد بیشتر رنگ‌ها را پررنگ‌تر و عدد کمتر "
                  "آن‌ها را کم‌رنگ‌تر (تا سیاه‌وسفید کامل در صفر) می‌کند.",
    "vibrance": "مثل Saturation رنگ‌ها را پررنگ‌تر می‌کند، اما هوشمندتر عمل "
                "می‌کند: رنگ‌های کم‌رنگ را بیشتر تقویت می‌کند و رنگ‌هایی که از "
                "قبل اشباع هستند (و به‌خصوص تن پوست) را کمتر دستکاری می‌کند، "
                "تا از غیرطبیعی شدن رنگ پوست جلوگیری شود.",
    "skin_warmth": "گرمای رنگ فقط در ناحیه‌ی تشخیص‌داده‌شده‌ی پوست را تنظیم "
                   "می‌کند، بدون تاثیر روی بقیه‌ی تصویر. مقدار مثبت پوست را "
                   "گرم‌تر (مایل به نارنجی) و منفی آن را سردتر می‌کند.",
    "skin_brightness": "روشنایی فقط ناحیه‌ی پوست را تغییر می‌دهد، مستقل از "
                        "بقیه‌ی تصویر — برای روشن یا تیره کردن ملایم صورت و "
                        "بدن بدون تغییر نور پس‌زمینه.",
    "skin_saturation": "میزان اشباع رنگ فقط در ناحیه‌ی پوست را تنظیم می‌کند. "
                        "مقدار منفی معمولاً برای طبیعی‌تر و کم‌رنگ‌تر کردن "
                        "پوست در پرتره استفاده می‌شود.",
    "skin_tan": "تعادل رنگ پوست را بین زرد و صورتی/قرمز جابه‌جا می‌کند — "
                "شبیه شبیه‌سازی برنزه شدن پوست یا اصلاح رنگ‌پریدگی آن.",
    "skin_smooth": "میزان صاف‌کردن نرم بافت پوست (کاهش دانه‌دانگی و "
                   "نایکنواختی سطح پوست) را کنترل می‌کند، بدون تاثیر روی لبه‌ها "
                   "و جزئیات مهم چهره مثل چشم و مو.",
    "skin_clarity": "وضوح میکروکنتراست فقط در ناحیه‌ی پوست را تنظیم می‌کند؛ "
                    "مقدار منفی پوست را نرم‌تر و مقدار مثبت آن را شفاف‌تر و "
                    "دارای بافت بیشتر نشان می‌دهد.",
    "clarity": "میکروکنتراست تصویر (کنتراست در جزئیات ریز و لبه‌های میان‌تون) "
               "را تنظیم می‌کند. مقدار مثبت تصویر را شفاف‌تر و دارای عمق بیشتر "
               "نشان می‌دهد؛ مقدار منفی جلوه‌ای نرم و رویایی ایجاد می‌کند.",
    "texture": "جزئیات ریز سطحی تصویر (مثل بافت پارچه، پوست، چوب) را بدون "
               "تاثیر زیاد روی لبه‌های بزرگ تقویت یا کاهش می‌دهد.",
    "distortion": "اعوجاج شکمی یا بالشتکی لنز را اصلاح می‌کند؛ مقدار مثبت لبه‌ها را به داخل می‌کشد.",
    "defringe": "هاله‌های بنفش و سبز کنار لبه‌های پرکنتراست (انحراف رنگی لنز) را کم‌رنگ می‌کند.",
    "sharpen": "وضوح لبه‌ها را با تیز کردن روشنایی بالا می‌برد؛ مقدار زیاد باعث هاله دور لبه‌ها می‌شود.",
    "sharpen_radius": "شعاع تیزسازی؛ مقدار کم برای جزئیات ریز و مقدار زیاد برای لبه‌های درشت‌تر.",
    "sharpen_masking": "تیزسازی را فقط روی لبه‌ها نگه می‌دارد تا نویز نواحی صاف تیز نشود.",
    "nr_luma": "نویز روشنایی (دانه‌دانه شدن) را کم می‌کند؛ مقدار زیاد جزئیات را نرم می‌کند.",
    "nr_color": "لکه‌های رنگی نویز، به‌ویژه در سایه‌ها، را حذف می‌کند.",
    "dehaze": "اثر مه، غبار یا افت کنتراست اتمسفری را کاهش یا افزایش می‌دهد. "
              "مقدار مثبت مه را از تصویر می‌زداید و کنتراست دوردست را افزایش "
              "می‌دهد؛ مقدار منفی جلوه‌ی مه‌آلود ایجاد می‌کند.",
    "highlight_rolloff": "نحوه‌ی نرم شدن هایلایت‌های خیلی روشن را کنترل "
                          "می‌کند، شبیه رفتار طبیعی فیلم آنالوگ در برابر نور "
                          "زیاد. مقدار بیشتر باعث می‌شود هایلایت‌ها به‌جای "
                          "سوختن ناگهانی، به‌آرامی محو شوند.",
    "halation": "هاله‌ی نورانی رنگی دور منابع نور شدید یا لبه‌های پرکنتراست "
                "ایجاد می‌کند — جلوه‌ای که در فیلم‌های آنالوگ (به‌خصوص فیلم‌های "
                "بدون لایه‌ی remjet) دیده می‌شود.",
    "bloom": "درخشش نرم و پخش‌شده دور نواحی خیلی روشن تصویر ایجاد می‌کند، "
             "شبیه پخش نور در لنزهای دوربین‌های سینمایی یا وینتیج.",
    "fade": "کنتراست سیاه‌های تصویر را کاهش می‌دهد و آن‌ها را به‌سمت خاکستری "
            "می‌برد — جلوه‌ی رایج فیلم‌های آنالوگ کهنه یا اسکن‌شده با کنتراست پایین.",
    "grain": "میزان دانه‌ی فیلم (نویز شبیه‌سازی‌شده) که روی تصویر اضافه "
             "می‌شود را کنترل می‌کند؛ برای بافت آنالوگ و جلوگیری از ظاهر بیش از حد صاف دیجیتال.",
    "grain_size": "اندازه‌ی فیزیکی دانه‌های اضافه‌شده توسط Grain را تنظیم "
                  "می‌کند. عدد کمتر دانه‌ی ریزتر و ظریف‌تر، عدد بیشتر دانه‌ی "
                  "درشت‌تر و چشمگیرتر ایجاد می‌کند.",
    "vignette": "روشنایی گوشه‌ها و لبه‌های کادر را نسبت به مرکز تصویر تغییر "
                "می‌دهد. مقدار منفی گوشه‌ها را تیره می‌کند (تمرکز روی سوژه‌ی "
                "مرکزی)، مقدار مثبت گوشه‌ها را روشن‌تر می‌کند.",
    "vignette_feather": "میزان نرمی و پخش‌شدگی مرز وینیت را کنترل می‌کند. "
                        "عدد کمتر یعنی گذار محسوس‌تر و نزدیک‌تر به مرکز؛ عدد "
                        "بیشتر یعنی گذاری بسیار تدریجی و نرم تا لبه‌ی کادر.",
}


GRP = {"exposure":"LIGHT","contrast":"LIGHT","gamma":"LIGHT",
       "highlights":"LIGHT","shadows":"LIGHT","whites":"LIGHT","blacks":"LIGHT",
       "temperature":"WHITE BALANCE","tint":"WHITE BALANCE",
       "saturation":"COLOUR","vibrance":"COLOUR","clarity":"DETAIL","texture":"DETAIL",
       "dehaze":"DETAIL","distortion":"DETAIL","defringe":"DETAIL","sharpen":"DETAIL","sharpen_radius":"DETAIL","sharpen_masking":"DETAIL","nr_luma":"DETAIL","nr_color":"DETAIL","skin_warmth":"SKIN","skin_brightness":"SKIN",
       "skin_saturation":"SKIN","skin_tan":"SKIN","skin_smooth":"SKIN",
       "skin_clarity":"SKIN","highlight_rolloff":"FILM","halation":"FILM",
       "bloom":"FILM","fade":"FILM","grain":"FILM","grain_size":"FILM",
       "vignette":"LENS","vignette_feather":"LENS",
       **{f"hsl_{b}_{c}":"HSL" for b in HSL_BANDS
          for c in ("hue","sat","lum")},
       **{f"cg_{r}_{c}":"COLOR GRADE" for r in CG_RANGES
          for c in ("hue","sat","lum")},
       "cg_global_hue":"COLOR GRADE","cg_global_sat":"COLOR GRADE",
       "cg_global_lum":"COLOR GRADE","cg_blending":"COLOR GRADE"}


GORD = ("LIGHT","WHITE BALANCE","COLOUR","HSL","COLOR GRADE","DETAIL","SKIN","FILM","LENS")


FMTS = [("JPEG — quality 95",("jpg",95)),("JPEG — quality 90",("jpg",90)),
        ("JPEG — quality 80",("jpg",80)),("PNG — lossless",("png",None)),
        ("TIFF — lossless",("tif",None))]


def sanitize_params(p):
    """Return a copy of a parameter dict that is safe to render: unknown scalar
    keys are kept (masks, curves, spots), numeric sliders are clamped to their
    SPEC range, and non-numeric slider values fall back to defaults."""
    out = dict(p or {})
    for k, _, lo, hi, _ in SPEC:
        if k not in out:
            continue
        try:
            out[k] = min(max(float(out[k]), lo), hi)
        except (TypeError, ValueError):
            out[k] = DEF.get(k, 0)
    return out


from typing import Any, TypedDict  # noqa: E402

RenderParams = TypedDict(
    "RenderParams",
    {**{k: Any for k in DEF},
     "masks": list, "spots": list, "aces_display": bool, "lut3d_path": str,
     "lut3d_strength": float, "cm_enabled": bool},
    total=False,
)
RenderParams.__doc__ = "Every key the renderer understands (all optional); see DEF for defaults."
