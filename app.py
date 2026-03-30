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
BOLD_FONT_PATH = './fonts/GoogleSans-Bold.ttf'
EMOJI_FONT_PATHS = [
    './fonts/NotoColorEmoji.ttf',
    '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
]
FW, FH = 1080, 1350
ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"


# ─────────────────────────────────────────────
# STYLES + STICKY JS
# ─────────────────────────────────────────────
def inject_ui():
    st.markdown(f"""
    <style>
        .block-container {{
            padding-top: 1rem !important;
            padding-bottom: 0.5rem !important;
        }}

        /* ── blue accent ── */
        .stButton > button[kind="primary"],
        .stDownloadButton > button[kind="primary"],
        button[kind="primary"] {{
            background-color: {ACCENT} !important;
            border-color: {ACCENT} !important;
            color: white !important;
            font-weight: 600 !important;
            padding: 0.55rem 1rem !important;
            border-radius: 10px !important;
        }}
        .stButton > button[kind="primary"]:hover,
        .stDownloadButton > button[kind="primary"]:hover,
        button[kind="primary"]:hover {{
            background-color: {ACCENT_HOVER} !important;
            border-color: {ACCENT_HOVER} !important;
        }}

        /* ── toggle accent ── */
        [data-testid="stToggle"] label span[data-checked="true"] {{
            background-color: {ACCENT} !important;
        }}

        /* ── containers ── */
        [data-testid="stExpander"] {{
            border-color: rgba(59, 130, 246, 0.2) !important;
            border-radius: 12px !important;
        }}
        div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 12px !important;
            border-color: rgba(59, 130, 246, 0.15) !important;
        }}

        /* ── typography ── */
        h3 {{
            font-size: 0.95rem !important;
            margin-top: 0.6rem !important;
            margin-bottom: 0.25rem !important;
            color: {ACCENT} !important;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }}
        .stSlider label {{ font-size: 0.82rem; }}
        .stCaption {{ font-size: 0.75rem !important; opacity: 0.7; }}

        /* ── right col sticky ── */
        #sticky-preview-anchor {{
            position: sticky;
            top: 0.5rem;
            z-index: 50;
        }}
    </style>
    """, unsafe_allow_html=True)

    # JS: force right column to be sticky
    st.markdown("""
    <script>
    (function() {
        function makeSticky() {
            const cols = document.querySelectorAll('[data-testid="stColumns"] > [data-testid="column"]');
            if (cols.length >= 2) {
                const rightCol = cols[cols.length - 1];
                rightCol.style.position = 'sticky';
                rightCol.style.top = '0.5rem';
                rightCol.style.alignSelf = 'flex-start';
                rightCol.style.maxHeight = '99vh';
                rightCol.style.overflowY = 'auto';
            }
        }
        // run on load and after streamlit rerenders
        makeSticky();
        const observer = new MutationObserver(makeSticky);
        observer.observe(document.body, { childList: true, subtree: true });
    })();
    </script>
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
        0xFE00 <= cp <= 0xFE0F or cp == 0x200D or cp == 0x2764 or
        cp == 0x2B50 or 0x231A <= cp <= 0x231B or
        0x23E9 <= cp <= 0x23F3 or cp > 0x1F000
    )


def load_emoji_font(size):
    for p in EMOJI_FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return None


def parse_bold(text):
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


def _draw_chunk(d, x, y, text, font, color, shadow):
    if shadow:
        d.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0, 128))
    d.text((x, y), text, font=font, fill=color)


def draw_rich_line(d, x, y, text, f_reg, f_bold, f_emoji, color, shadow):
    segs = parse_bold(text)
    cx = x
    for txt, bold in segs:
        font = f_bold if bold else f_reg
        if f_emoji:
            buf = ''
            for ch in txt:
                if is_emoji(ch):
                    if buf:
                        _draw_chunk(d, cx, y, buf, font, color, shadow)
                        cx += d.textlength(buf, font=font)
                        buf = ''
                    _draw_chunk(d, cx, y, ch, f_emoji, color, shadow)
                    cx += d.textlength(ch, font=f_emoji)
                else:
                    buf += ch
            if buf:
                _draw_chunk(d, cx, y, buf, font, color, shadow)
                cx += d.textlength(buf, font=font)
        else:
            _draw_chunk(d, cx, y, txt, font, color, shadow)
            cx += d.textlength(txt, font=font)


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
        lx = (w - nw) // 2
        c = img.crop((lx, 0, lx + nw, h))
    else:
        nh = int(w / r)
        ty = (h - nh) // 2
        c = img.crop((0, ty, w, ty + nh))
    base = c.resize((FW, FH), Image.Resampling.LANCZOS).convert("RGBA")
    if darken > 0:
        a = int(255 * darken / 100)
        base.alpha_composite(Image.new('RGBA', (FW, FH), (0, 0, 0, a)))
    return base


def render_slide(slide, base, cfg):
    img = base.copy()
    draw = ImageDraw.Draw(img)

    hf = cfg['hf']
    tf = cfg['tf']
    bf = cfg['bf']
    ef = cfg['ef']
    color = cfg['color']
    shadow = cfg['shadow']

    h_lines = wrap_pixels(slide['title'], hf, cfg['hw'], draw)

    body_lines = []
    for para in slide['text'].split('\n'):
        para = para.strip()
        if para:
            body_lines.extend(wrap_pixels(para, tf, cfg['bw'], draw))
        else:
            body_lines.append('')

    title_lh = int(cfg['hs'] * cfg['h_line_mult'])
    text_lh = int(cfg['ts'] * cfg['t_line_mult'])

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

    # watermarks
    for wm in cfg.get('wms', []):
        if wm and (wm['text'] or wm['avatar']):
            _draw_watermark(img, wm, color)

    return img.convert("RGB")


def _draw_watermark(img, wm, default_color):
    wm_text = wm['text']
    av_img = wm['avatar']
    av_sz = wm['av_size']
    wf = wm['font']
    alpha = wm['alpha']

    draw = ImageDraw.Draw(img)
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

    if wm_text:
        draw2 = ImageDraw.Draw(img)
        text_y = int(wm_y + (block_h - text_h) // 2)
        draw2.text((cx, text_y), wm_text, font=wf, fill=(*default_color[:3], alpha))


# ─────────────────────────────────────────────
# WATERMARK UI BLOCK (reusable)
# ─────────────────────────────────────────────
def watermark_ui(label, prefix):
    """Renders a watermark settings block and returns config dict."""
    with st.container(border=True):
        st.markdown(f"### {label}")
        wm_text = st.text_input("Текст", value="", placeholder="@username", key=f"{prefix}_text", label_visibility="collapsed")

        c1, c2 = st.columns(2)
        with c1:
            wm_pos = st.selectbox("Позиция", ["Слева", "По центру", "Справа"], index=0, key=f"{prefix}_pos")
        with c2:
            wm_avatar_file = st.file_uploader("Аватарка", type=['png', 'jpg', 'jpeg'], key=f"{prefix}_av")

        c3, c4 = st.columns(2)
        with c3:
            wm_av_size = st.slider("Аватарка px", 20, 120, 44, step=2, key=f"{prefix}_avsz")
        with c4:
            wm_font_size = st.slider("Размер текста", 14, 60, 26, step=1, key=f"{prefix}_fsz")

        c5, c6, c7 = st.columns(3)
        with c5:
            wm_alpha = st.slider("Прозрачность", 30, 255, 140, step=5, key=f"{prefix}_alpha")
        with c6:
            wm_ox = st.slider("Сдвиг X", -300, 300, 0, step=5, key=f"{prefix}_ox")
        with c7:
            wm_oy = st.slider("Сдвиг Y", -300, 300, 0, step=5, key=f"{prefix}_oy")

    avatar_img = None
    if wm_avatar_file:
        avatar_img = Image.open(wm_avatar_file).convert("RGBA")

    return {
        'text': wm_text,
        'pos': wm_pos,
        'avatar': avatar_img,
        'av_size': wm_av_size,
        'font_size': wm_font_size,
        'alpha': wm_alpha,
        'ox': wm_ox,
        'oy': wm_oy,
        'font': None,  # will be set after font load
    }


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────
st.set_page_config(page_title="Carousel Gen", page_icon="⬛", layout="wide")
inject_ui()

left, right = st.columns([5, 4], gap="large")

# ═══════════════════════════════════════════
# LEFT
# ═══════════════════════════════════════════
with left:

    # ── ФОНЫ ──
    with st.container(border=True):
        st.markdown("### Фоны")
        uploaded_bgs = st.file_uploader(
            "bg", type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True, label_visibility="collapsed"
        )
        bg_darken = st.slider("Затемнение", 0, 100, 0, format="%d%%")

    # ── НИКНЕЙМ 1 ──
    wm1_cfg = watermark_ui("Никнейм 1", "wm1")

    # ── НИКНЕЙМ 2 ──
    wm2_cfg = watermark_ui("Никнейм 2", "wm2")

    # ── ТИПОГРАФИКА ──
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

    # ── МЕЖСТРОЧНЫЙ ИНТЕРВАЛ ──
    with st.container(border=True):
        st.markdown("### Межстрочный интервал")
        lc1, lc2 = st.columns(2)
        with lc1:
            h_line_mult = st.slider("Интервал заголовка", 1.0, 2.5, 1.25, step=0.05, key="hlm")
        with lc2:
            t_line_mult = st.slider("Интервал текста", 1.0, 3.0, 1.55, step=0.05, key="tlm")

    # ── КОНТЕЙНЕР ТЕКСТА ──
    with st.container(border=True):
        st.markdown("### Контейнер текста")
        st.caption("Ширина области переноса (px)")
        kc1, kc2 = st.columns(2)
        with kc1:
            header_w = st.slider("Ширина заголовка", 300, 1040, 900, step=10)
        with kc2:
            body_w = st.slider("Ширина текста", 300, 1040, 900, step=10)
        st.caption("Позиция блока на слайде")
        pc1, pc2 = st.columns(2)
        with pc1:
            text_x = st.slider("X (горизонталь)", 20, 500, 90, step=5)
        with pc2:
            text_y = st.slider("Y (вертикаль)", 50, 1100, 350, step=10)

    # ── КОНТЕНТ ──
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
# RIGHT
# ═══════════════════════════════════════════
with right:
    # anchor for sticky
    st.markdown('<div id="sticky-preview-anchor"></div>', unsafe_allow_html=True)

    fonts_ok = True
    try:
        hf = ImageFont.truetype(HEADER_FONT_PATH, header_size)
        tf = ImageFont.truetype(BODY_FONT_PATH, text_size)
        bf = ImageFont.truetype(BOLD_FONT_PATH, text_size)
    except IOError:
        fonts_ok = False
        st.error("Шрифты не найдены в ./fonts/ – нужен GoogleSans-Bold.ttf и GoogleSans-Regular.ttf")

    ef = load_emoji_font(text_size) if fonts_ok else None

    # load watermark fonts
    if fonts_ok:
        try:
            wm1_cfg['font'] = ImageFont.truetype(BODY_FONT_PATH, wm1_cfg['font_size'])
            wm2_cfg['font'] = ImageFont.truetype(BODY_FONT_PATH, wm2_cfg['font_size'])
        except IOError:
            pass

    if fonts_ok and not ef:
        st.caption("ℹ️ Для эмодзи – NotoEmoji-Regular.ttf в ./fonts/")

    cfg = {
        'hf': hf if fonts_ok else None,
        'tf': tf if fonts_ok else None,
        'bf': bf if fonts_ok else None,
        'ef': ef,
        'color': hex_to_rgb(text_color_hex),
        'hs': header_size,
        'ts': text_size,
        'hw': header_w,
        'bw': body_w,
        'tx': text_x,
        'ty': text_y,
        'gap': space_between,
        'shadow': add_shadow,
        'h_line_mult': h_line_mult,
        't_line_mult': t_line_mult,
        'wms': [wm1_cfg, wm2_cfg],
    }

    slides_data = parse_slides(text_input) if text_input.strip() else []

    with st.container(border=True):
        if uploaded_bgs and fonts_ok and slides_data:
            bg = prepare_bg(uploaded_bgs[0], bg_darken)
            preview = render_slide(slides_data[0], bg, cfg)
            st.image(preview, use_container_width=True)
        elif not uploaded_bgs:
            st.info("← Загрузи фон")
        elif not slides_data:
            st.info("← Добавь контент")

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
