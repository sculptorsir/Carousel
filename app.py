import streamlit as st
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import io
import zipfile

HEADER_FONT_NAME = './fonts/Montserrat-Bold.ttf' 
TEXT_FONT_NAME = './fonts/Montserrat-Regular.ttf' 
WATERMARK_FONT_SIZE = 26 
WATERMARK_ALPHA = 130 

GLASS_BLUR_RADIUS = 40     
GLASS_DARKEN_ALPHA = 170   
BORDER_ALPHA = 30          

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def create_editorial_glass(base_img, panel_width, panel_height, glass_x, glass_y):
    glass_size = (panel_width, panel_height)
    target_region = base_img.crop((glass_x, glass_y, glass_x + panel_width, glass_y + panel_height))
    blurred_bg = target_region.filter(ImageFilter.GaussianBlur(GLASS_BLUR_RADIUS))
    
    darken = Image.new('RGBA', glass_size, (0, 0, 0, GLASS_DARKEN_ALPHA))
    blurred_bg.alpha_composite(darken)
    
    draw_border = ImageDraw.Draw(blurred_bg)
    draw_border.rectangle((0, 0, panel_width-1, panel_height-1), outline=(255, 255, 255, BORDER_ALPHA), width=1)
    return blurred_bg

def create_colored_backing(width, height, color, alpha):
    rgb_color = color[:3] if len(color) == 4 else color
    return Image.new('RGBA', (width, height), (*rgb_color, alpha))

def parse_raw_text(content):
    blocks = [block.strip() for block in content.split('\n\n') if block.strip()]
    slides = []
    for block in blocks:
        lines = block.split('\n')
        title = lines[0].strip()
        text = " ".join([line.strip() for line in lines[1:]])
        slides.append({"title": title, "text": text})
    return slides

st.set_page_config(page_title="Мой Генератор Каруселей", page_icon="⬛", layout="centered")

st.title("Генератор Каруселей")
st.markdown("Создавай карусели для соцсетей прямо с телефона. By @ТВОЙ_НИК")

st.subheader("1. Фоны")
uploaded_bgs = st.file_uploader(
    "Загрузи фоны (можно выбрать сразу несколько)", 
    type=['png', 'jpg', 'jpeg'], 
    accept_multiple_files=True
)

st.subheader("2. Брендинг")
user_watermark = st.text_input("Твой никнейм (водяной знак)", value="")

st.subheader("3. Дизайн")

st.write("### Эффекты Фона")
bg_darken_percent = st.slider("Сила общего затемнения фона (%)", 0, 100, 0)

st.write("---")

st.write("### Подложка текста")
col1, col2 = st.columns(2)
with col1:
    backing_type = st.selectbox("Тип подложки", ["Без подложки", "Матовое стекло", "Цветная заливка"])
with col2:
    text_position = st.selectbox("Позиция текста", ["Посередине", "Снизу", "Сверху"])

if backing_type == "Цветная заливка":
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        backing_color_hex = st.color_picker("Цвет заливки", "#000000")
    with col_c2:
        backing_alpha = st.slider("Прозрачность заливки", 0, 255, 180)
else:
    backing_color_hex = "#FFFFFF" 
    backing_alpha = 0 

st.write("---")

st.write("### Типографика")
col_t1, col_t2, col_t3 = st.columns([2, 1, 1])
with col_t1:
    text_color_hex = st.color_picker("Цвет текста", "#FFFFFF")
with col_t2:
    add_shadow = st.toggle("Тень текста", value=False)
with col_t3:
    st.empty() 

st.write("Типографика и отступы")
col4, col5 = st.columns(2)
with col4:
    header_font_size = st.slider("Размер заголовка", min_value=30, max_value=120, value=70, step=2)
with col5:
    text_font_size = st.slider("Размер текста", min_value=20, max_value=80, value=40, step=2)

space_between = st.slider("Отступ между заголовком и текстом", min_value=30, max_value=250, value=120, step=10)

st.write("---")

st.subheader("4. Контент")
default_text = """ЗАГОЛОВОК 1
Текст 1

ЗАГОЛОВОК 2
Текст 2"""
text_input = st.text_area("Текст карусели (Пустая строка разделяет слайды)", value=default_text, height=250)

st.write("---")
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    btn_preview = st.button("👁 Предпросмотр (1 слайд)", use_container_width=True)
with col_btn2:
    btn_generate = st.button("🚀 Сгенерировать всё", type="primary", use_container_width=True)

if btn_preview or btn_generate:
    if not uploaded_bgs:
        st.error("Сначала загрузи хотя бы один фон!")
    elif not text_input.strip():
        st.error("Вставь текст!")
    else:
        status_text = "Рендерим превью..." if btn_preview else "Собираем карусель..."
        with st.spinner(status_text):
            slides_data = parse_raw_text(text_input)
            
            if btn_preview:
                slides_data = slides_data[:1]
            
            user_rgb_color = hex_to_rgb(text_color_hex)
            backing_rgb_color = hex_to_rgb(backing_color_hex)
            try:
                h_font = ImageFont.truetype(HEADER_FONT_NAME, header_font_size)
                t_font = ImageFont.truetype(TEXT_FONT_NAME, text_font_size)
                w_font = ImageFont.truetype(TEXT_FONT_NAME, WATERMARK_FONT_SIZE)
            except IOError:
                st.error("Ошибка: шрифты не найдены в папке ./fonts/")
                st.stop()

            generated_images = []
            final_w, final_h = 1080, 1350 

            for i, slide in enumerate(slides_data):
                current_bg_file = uploaded_bgs[i % len(uploaded_bgs)]
                
                input_img = Image.open(current_bg_file).convert("RGB")
                w, h = input_img.size
                target_ratio = final_w / final_h
                input_ratio = w / h

                if input_ratio > target_ratio:
                    new_w = int(h * target_ratio)
                    left = (w - new_w) // 2
                    base_img = input_img.crop((left, 0, left + new_w, h))
                else:
                    new_h = int(w / target_ratio)
                    top = (h - new_h) // 2
                    base_img = input_img.crop((0, top, w, top + new_h))

                base_img = base_img.resize((final_w, final_h), Image.Resampling.LANCZOS).convert("RGBA")
                
                if bg_darken_percent > 0:
                    alpha = int(255 * (bg_darken_percent / 100))
                    darken_layer = Image.new('RGBA', (final_w, final_h), (0, 0, 0, alpha))
                    base_img.alpha_composite(darken_layer)

                img = base_img.copy()
                draw = ImageDraw.Draw(img)
                
                h_wrap = max(10, int(1000 / header_font_size))
                t_wrap = max(15, int(1120 / text_font_size))
                
                h_lines = textwrap.wrap(slide['title'], width=h_wrap)
                t_lines = textwrap.wrap(slide['text'], width=t_wrap) 
                
                padding_top = 110 
                padding_bottom = 90
                
                title_line_height = int(header_font_size * 1.2)
                text_line_height = int(text_font_size * 1.5)
                
                total_text_height = (len(h_lines) * title_line_height) + space_between + (len(t_lines) * text_line_height)
                panel_height = padding_top + total_text_height + padding_bottom
                panel_width = 900
                
                glass_x = (final_w - panel_width) // 2
                
                if text_position == "Сверху":
                    glass_y = 150 
                elif text_position == "Снизу":
                    glass_y = final_h - panel_height - 80 
                else: 
                    glass_y = (final_h - panel_height) // 2 - 20 
                
                if backing_type == "Матовое стекло":
                    glass_panel = create_editorial_glass(base_img, panel_width, panel_height, glass_x, glass_y)
                    img.alpha_composite(glass_panel, (glass_x, glass_y))
                elif backing_type == "Цветная заливка":
                    colored_backing = create_colored_backing(panel_width, panel_height, backing_rgb_color, backing_alpha)
                    img.alpha_composite(colored_backing, (glass_x, glass_y))
                
                draw = ImageDraw.Draw(img) 
                
                if user_watermark:
                    bbox = draw.textbbox((0, 0), user_watermark, font=w_font)
                    w_width = bbox[2] - bbox[0]
                    w_x = (final_w - w_width) // 2
                    w_y = 60 
                    draw.text((w_x, w_y), user_watermark, font=w_font, fill=(*user_rgb_color, WATERMARK_ALPHA))
                
                current_y = glass_y + padding_top
                margin_x = glass_x + 80 

                def draw_text_with_shadow(draw_obj, xy, text, font, fill_color):
                    if add_shadow:
                        shadow_color = (0, 0, 0, 128)
                        draw_obj.text((xy[0]+3, xy[1]+3), text, font=font, fill=shadow_color)
                    draw_obj.text(xy, text, font=font, fill=fill_color)

                for line in h_lines:
                    draw_text_with_shadow(draw, (margin_x, current_y), line, h_font, user_rgb_color)
                    current_y += title_line_height

                current_y += space_between 
                
                for line in t_lines:
                    draw_text_with_shadow(draw, (margin_x, current_y), line, t_font, user_rgb_color)
                    current_y += text_line_height
                
                generated_images.append(img.convert("RGB"))

            if btn_preview:
                st.success("Превью первого слайда готово!")
                st.image(generated_images[0], use_container_width=True)
            
            if btn_generate:
                st.success("Карусель собрана!")
                cols = st.columns(2)
                for idx, g_img in enumerate(generated_images):
                    cols[idx % 2].image(g_img, use_container_width=True)

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for idx, g_img in enumerate(generated_images):
                        img_byte_arr = io.BytesIO()
                        g_img.save(img_byte_arr, format='JPEG', quality=95)
                        zip_file.writestr(f"slide_{idx+1}.jpg", img_byte_arr.getvalue())

                st.download_button(
                    label="📥 Скачать всю карусель (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="premium_carousel.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
