import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import zipfile
import re

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
HEADER_FONT_PATH = './fonts/GoogleSans-Bold.ttf'
BODY_FONT_PATH = './fonts/GoogleSans-Regular.ttf'
EMOJI_FONT_PATHS = [
    './fonts/NotoEmoji-Regular.ttf',
    './fonts/NotoColorEmoji.ttf',
    '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
    '/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf',
]
WM_FONT_SIZE = 26
WM_ALPHA = 130
FW, FH = 1080, 1350
ACCENT = "#3B82F6"


# ─────────────────────────────────────────────
# THEME CSS
# ─────────────────────────────────────────────
def inject_css():
    st.markdown(f"""
    <style>
        :root {{
            --accent: {ACCENT};
        }}
        .block-container {{
            padding-top: 1.2rem;
            padding-bottom: 1rem;
        }}

        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"] {{
            background-color: {ACCENT} !important;
            border-color: {ACCENT} !important;
        }}
        .stButton > button[kind="primary"]:hover,
        .stDownloadButton > button[kind="primary"]:hover {{
            background-color: #2563EB !important;
            border-color: #2563EB !important;
        }}

        /* right column sticky */
        @media (min-width: 768px) {{
            [data-testid="stColumns"] > div:last-child {{
                position: sticky;
                top: 1rem;
                align-self: flex-start;
                max-height: 98vh;
                overflow-y: auto;
            }}
        }}

        h3 {{ font-size: 1rem !important; margin-top: 0.8rem !important; margin-bottom: 0.3rem !important; }}
        .stSlider label {{ font-size: 0.82rem; }}
        .stDivider {{ margin: 0.5rem 0 !important; }}
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────
def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def is_emoji(ch):
    cp = ord(ch)
    return (
        0x1F600 <= cp <= 0x1F64F or 0x1F300 <= cp <= 0x1F5FF or
        0x1F680 <= cp <= 0x1F6FF or 0x1F1E0 <= cp <= 0x1F1FF or
        0x2600 <= cp <= 0x26FF or 0x2700 <= cp <= 0x27BF or
        0x1F900 <= cp <= 0x1F9FF or 0x1FA00 <= cp <= 0x1FAFF or
        0x1FA70 <= cp <= 0x1FAFF or 0xFE00 <= cp <= 0xFE0F or
        cp == 0x200D or cp == 0x2764 or cp == 0x2B50 or
        cp == 0x20E3 or 0x231A <= cp <= 0x231B or
        0x23E9 <= cp <= 0x23F3 or 0x25AA <= cp <= 0x25FE or
        0x2614 <= cp <= 0x2615 or 0x2648 <= cp <= 0x2653 or
        0x26A1 <= cp <= 0x26FD or 0x2702 <= cp <= 0x27BF or
        0x2934 <= cp <= 0x2935 or 0x2B05 <= cp <= 0x2B07 or
        0x2B1B <= cp <= 0x2B55 or cp == 0x3030 or cp == 0x303D or
        cp > 0x1F000
    )


def load_emoji_font(size):
    for p in EMOJI_FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return None


def parse_bold(text):
    """Split text by *bold* markers."""
    parts = re.split(r'(\*[^*]+\*)', text)
    segs = []
    for p in parts:
        if p.startswith('*') and p.endswith('*') and len(p) > 2:
            segs.append((p[1:-1], True))
        elif p:
            segs.append((p, False))
    return segs


def strip_markers(text):
    return text.replace('*', '')


def wrap_pixels(text, font, max_w, draw):
    """Wrap by pixel width – whole words only, never breaks a word."""
    words = text.split()
    if not words:
        return ['']
    lines, cur = [], [words[0]]
    for w in words[1:]:
        test = ' '.join(cur + [w])
        tw = draw.textlength(strip_markers(test), font=font)
        if tw <= max_w:
            cur.append(w)
        else:
            lines.append(' '.join(cur))
            cur = [w]
    lines.append(' '.join(cur))
    return lines


def _draw_chunk(draw_obj, x, y, text, font, color, shadow):
    if shadow:
        draw_obj.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0, 128))
    draw_obj.text((x, y), text, font=font, fill=color)


def draw_rich_line(draw_obj, x, y, text, f_reg, f_bold, f_emoji, color, shadow):
    """Render one line with *bold* + emoji support."""
    segs = parse_bold(text)
    cx = x
    for txt, is_bold in segs:
        font = f_bold if is_bold else f_reg
        if f_emoji:
            buf = ''
            for ch in txt:
                if is_emoji(ch):
                    if buf:
                        _draw_chunk(draw_obj, cx, y, buf, font, color, shadow)
                        cx += draw_obj.textlength(buf, font=font)
                        buf = ''
                    _draw_chunk(draw_obj, cx, y, ch, f_emoji, color, shadow)
                    cx += draw_obj.textlength(ch, font=f_emoji)
                else:
                    buf += ch
            if buf:
                _draw_chunk(draw_obj, cx, y, buf, font, color, shadow)
                cx += draw_obj.textlength(buf, font=font)
        else:
            _draw_chunk(draw_obj, cx, y, txt, font, color, shadow)
            cx += draw_obj.textlength(txt, font=font)


# ─────────────────────────────────────────────
# SLIDES
# ─────────────────────────────────────────────
def parse_slides(content):
    blocks = content.split('---')
    slides = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        lines = b.split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[1:]).strip()
        slides.append({"title": title, "text": body})
    return slides


def prepare_bg(f, darken):
    img = Image.open(f).convert("RGB")
    w, h = img.size
    r = FW / FH
    ir = w / h
    if ir > r:
        nw = int(h * r)
        l = (w - nw) // 2
        c = img.crop((l, 0, l + nw, h))
    else:
        nh = int(w / r)
        t = (h - nh) // 2
        c = img.crop((0, t, w, t + nh))
    base = c.resize((FW, FH), Image.Resampling.LANCZOS).convert("RGBA")
    if darken > 0:
        a = int(255 * darken / 100)
        base.alpha_composite(Image.new('RGBA', (FW, FH), (0, 0, 0, a)))
    return base


def render_slide(slide, base, cfg):
    img = base.copy()
    draw = ImageDraw.Draw(img)

    hf, tf, bf, wf, ef = cfg['hf'], cfg['tf'], cfg['bf'], cfg['wf'], cfg['ef']
    color = cfg['color']
    shadow = cfg['shadow']

    # wrap
    h_lines = wrap_pixels(slide['title'], hf, cfg['hw'], draw)

    body_lines = []
    for para in slide['text'].split('\n'):
        para = para.strip()
        if para:
            body_lines.extend(wrap_pixels(para, tf, cfg['bw'], draw))
        else:
            body_lines.append('')

    title_lh = int(cfg['hs'] * 1.25)
    text_lh = int(cfg['ts'] * 1.55)

    tx, ty = cfg['tx'], cfg['ty']
    cur_y = ty

    for line in h_lines:
        draw_rich_line(draw, tx, cur_y, line, hf, hf, ef, color, shadow)
        cur_y += title_lh

    cur_y += cfg['gap']

    for line in body_lines:
        if line:
            draw_rich_line(draw, tx, cur_y, line, tf, bf, ef, color, shadow)
        cur_y += text_lh

    # watermark
    wm = cfg.get('wm')
    if wm and (wm['text'] or wm['avatar']):
        _draw_watermark(img, draw, wm, wf, color)

    return img.convert("RGB")


def _draw_watermark(img, draw, wm, wf, color):
    wm_text = wm['text']
    av_img = wm['avatar']
    av_sz = wm['av_size']

    text_w, text_h = 0, 0
    if wm_text:
        bb = draw.textbbox((0, 0), wm_text, font=wf)
        text_w = bb[2] - bb[0]
        text_h = bb[3] - bb[1]

    total_w = text_w + (av_sz + 12 if av_img else 0)
    block_h = max(text_h, av_sz if av_img else 0)
    wm_y = FH - 80 + wm['oy']

    if wm['pos'] == 'Слева':
        wm_x = 60 + wm['ox']
    elif wm['pos'] == 'Справа':
        wm_x = FW - total_w - 60 + wm['ox']
    else:
        wm_x = (FW - total_w) // 2 + wm['ox']

    cx = int(wm_x)

    if av_img and av_sz > 0:
        av = av_img.copy().resize((av_sz, av_sz), Image.Resampling.LANCZOS).convert("RGBA")
        mask = Image.new('L', (av_sz, av_sz), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, av_sz - 1, av_sz - 1), fill=255)
        av.putalpha(mask)
        av_y = int(wm_y + (block_h - av_sz) // 2)
        img.alpha_composite(av, (cx, av_y))
        cx += av_sz + 12
        draw = ImageDraw.Draw(img)  # refresh after composite

    if wm_text:
        text_y = int(wm_y + (block_h - text_h) // 2)
        draw.text((cx, text_y), wm_text, font=wf, fill=(*color[:3], WM_ALPHA))


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────
st.set_page_config(page_title="Carousel Gen", page_icon="⬛", layout="wide")
inject_css()

left, right = st.columns([5, 4], gap="large")

# ═══════════════════════════════════════════
# LEFT – SETTINGS
# ═══════════════════════════════════════════
with left:

    with st.container(border=True):
        st.markdown("### Фоны")
        uploaded_bgs = st.file_uploader(
            "bg", type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True, label_visibility="collapsed"
        )
        bg_darken = st.slider("Затемнение", 0, 100, 0, format="%d%%")

    with st.container(border=True):
        st.markdown("### Никнейм")
        wm_text = st.text_input("wm", value="", placeholder="@username", label_visibility="collapsed")
        c1, c2 = st.columns(2)
        with c1:
            wm_pos = st.selectbox("Позиция", ["Слева", "По центру", "Справа"], index=0)
        with c2:
            wm_avatar_file = st.file_uploader("Аватарка", type=['png', 'jpg', 'jpeg'])
        c3, c4, c5 = st.columns(3)
        with c3:
            wm_av_size = st.slider("Аватарка px", 20, 80, 40, step=2)
        with c4:
            wm_ox = st.slider("Сдвиг X", -200, 200, 0, step=5, key="wmox")
        with c5:
            wm_oy = st.slider("Сдвиг Y", -200, 200, 0, step=5, key="wmoy")

    with st.container(border=True):
        st.markdown("### Типографика")
        tc1, tc2 = st.columns(2)
        with tc1:
            text_color_hex = st.color_picker("Цвет текста", "#FFFFFF")
        with tc2:
            add_shadow = st.toggle("Тень текста", value=False)
        tc3, tc4 = st.columns(2)
        with tc3:
            header_size = st.slider("Размер заголовка", 30, 120, 70, step=2)
        with tc4:
            text_size = st.slider("Размер текста", 20, 80, 40, step=2)
        space_between = st.slider("Отступ заголовок → текст", 10, 250, 100, step=10)

    with st.container(border=True):
        st.markdown("### Контейнер текста")
        st.caption("Ширина области переноса (px)")
        kc1, kc2 = st.columns(2)
        with kc1:
            header_w = st.slider("Ширина заголовка", 300, 1040, 900, step=10)
        with kc2:
            body_w = st.slider("Ширина текста", 300, 1040, 900, step=10)
        st.caption("Позиция на слайде")
        pc1, pc2 = st.columns(2)
        with pc1:
            text_x = st.slider("X (горизонталь)", 20, 500, 90, step=5)
        with pc2:
            text_y = st.slider("Y (вертикаль)", 50, 1100, 350, step=10)

    with st.container(border=True):
        st.markdown("### Контент")
        st.caption("Слайды через `---` · первая строка = заголовок · `*жирный*` · пустая строка = абзац")
        default_text = """ЗАГОЛОВОК 1
Текст первого слайда.

Второй абзац с *жирным* словом.
---
ЗАГОЛОВОК 2
Текст второго слайда.
---
ЗАГОЛОВОК 3
Текст третьего слайда."""
        text_input = st.text_area("content", value=default_text, height=260, label_visibility="collapsed")


# ═══════════════════════════════════════════
# RIGHT – PREVIEW & GENERATE
# ═══════════════════════════════════════════
with right:

    fonts_ok = True
    try:
        hf = ImageFont.truetype(HEADER_FONT_PATH, header_size)
        tf = ImageFont.truetype(BODY_FONT_PATH, text_size)
        bf = ImageFont.truetype(HEADER_FONT_PATH, text_size)
        wf = ImageFont.truetype(BODY_FONT_PATH, WM_FONT_SIZE)
    except IOError:
        fonts_ok = False
        st.error("Шрифты не найдены в ./fonts/")

    ef = load_emoji_font(text_size) if fonts_ok else None
    if fonts_ok and not ef:
        st.caption("ℹ️ Для эмодзи положи NotoEmoji-Regular.ttf в ./fonts/")

    avatar_img = None
    if wm_avatar_file:
        avatar_img = Image.open(wm_avatar_file).convert("RGBA")

    cfg = {
        'hf': hf if fonts_ok else None,
        'tf': tf if fonts_ok else None,
        'bf': bf if fonts_ok else None,
        'wf': wf if fonts_ok else None,
        'ef': ef,
        'color': hex_to_rgb(text_color_hex),
        'hs': header_size, 'ts': text_size,
        'hw': header_w, 'bw': body_w,
        'tx': text_x, 'ty': text_y,
        'gap': space_between,
        'shadow': add_shadow,
        'wm': {
            'text': wm_text, 'pos': wm_pos,
            'ox': wm_ox, 'oy': wm_oy,
            'avatar': avatar_img, 'av_size': wm_av_size,
        },
    }

    slides_data = parse_slides(text_input) if text_input.strip() else []

    with st.container(border=True):
        st.markdown("### Превью")
        if uploaded_bgs and fonts_ok and slides_data:
            bg = prepare_bg(uploaded_bgs[0], bg_darken)
            preview = render_slide(slides_data[0], bg, cfg)
            st.image(preview, width=380)
        elif not uploaded_bgs:
            st.info("Загрузи фон слева")
        elif not slides_data:
            st.info("Добавь контент")

    btn = st.button("Сгенерировать карусель", type="primary", use_container_width=True)

    if btn:
        if not uploaded_bgs:
            st.error("Загрузи фоны!")
        elif not slides_data:
            st.error("Добавь контент!")
        elif not fonts_ok:
            st.error("Шрифты не найдены!")
        else:
            with st.spinner("Генерация..."):
                images = []
                for i, slide in enumerate(slides_data):
                    bg = prepare_bg(uploaded_bgs[i % len(uploaded_bgs)], bg_darken)
                    images.append(render_slide(slide, bg, cfg))

            st.success(f"Готово – {len(images)} слайд(ов)")
            cols = st.columns(2)
            for idx, im in enumerate(images):
                cols[idx % 2].image(im, caption=f"Слайд {idx + 1}", use_container_width=True)

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
                for idx, im in enumerate(images):
                    b = io.BytesIO()
                    im.save(b, format='JPEG', quality=95)
                    zf.writestr(f"slide_{idx + 1}.jpg", b.getvalue())

            st.download_button(
                "Скачать карусель (ZIP)",
                data=buf.getvalue(),
                file_name="carousel.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
            )
