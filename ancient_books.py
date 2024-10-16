import re
from enum import Enum
from pprint import pprint
from turtledemo.penrose import start

import cv2
import math
import os
import random
import shutil
import textwrap
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Pool

from PIL.ImageOps import scale
from opencc import OpenCC
from PIL import ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter
from logger import Logger

LOGGER = Logger('ancient-books')


class TextType(Enum):
    CHAPTER = 'chapter'
    CONTENT = 'content'
    ANNOTATION = 'annotation'


def get_params(chapter_font_paths=[], chapter_font_size=50, chapter_font_color='black', content_font_paths=[],
               content_font_size=40, content_font_color='black', annotation_font_paths=[], annotation_font_size=30,
               annotation_font_color='red', output_dir='output', width=1400, height=1200,
               line_count=10, line_space=20, annotation_line_space=5, margin=(200, 200, 50, 50), border=5,
               border_color='black', background=None, line_sep=True, line_sep_color='black', line_sep_width=1,
               with_noise=False, noise_level=0.005, older=False, bg_color='white'):
    """
    获取生成文本图像的参数
    :param chapter_font_paths: 章节名字体路径列表
    :param chapter_font_size: 章节名字号
    :param chapter_font_color: 章节名字体颜色
    :param content_font_paths: 正文字体路径列表
    :param content_font_size: 正文字号
    :param content_font_color: 正文字体颜色
    :param annotation_font_paths: 批注字体路径列表
    :param annotation_font_size: 批注字号
    :param annotation_font_color: 批注字体颜色
    :param output_dir: 输出目录
    :param width: 图像宽度
    :param height: 图像高度
    :param line_count: 每页行数
    :param line_space: 行间距
    :param annotation_line_space: 批注行间距
    :param margin: 页边距
    :param border: 文本框宽度
    :param border_color: 文本框颜色
    :param background: 背景图片路径
    :param line_sep: 是否打印行分隔线
    :param line_sep_color: 行分隔线颜色
    :param line_sep_width: 行分隔线宽度
    :param with_noise: 是否添加噪点
    :param noise_level: 噪点等级
    :param older: 是否做旧
    :param bg_color: 图像底色
    :return: 图像参数字典
    """
    return {
        'chapter_font_paths': chapter_font_paths,
        'chapter_font_size': chapter_font_size,
        'chapter_font_color': chapter_font_color,
        'content_font_paths': content_font_paths,
        'content_font_size': content_font_size,
        'content_font_color': content_font_color,
        'annotation_font_paths': annotation_font_paths,
        'annotation_font_size': annotation_font_size,
        'annotation_font_color': annotation_font_color,
        'output_dir': output_dir,
        'width': width,
        'height': height,
        'line_count': line_count,
        'line_space': line_space,
        'annotation_line_space': annotation_line_space,
        'margin': margin,
        'border': border,
        'border_color': border_color,
        'background': background,
        'line_sep': line_sep,
        'line_sep_color': line_sep_color,
        'line_sep_width': line_sep_width,
        'with_noise': with_noise,
        'noise_level': noise_level,
        'older': older,
        'bg_color': bg_color
    }


def convert_to_traditional_chinese(lines):
    """
    将简体中文文本转换为繁体中文文本
    :param lines: 待转换的文本列表
    :return: 繁体中文文本
    """
    cc = OpenCC('s2t')
    return [cc.convert(line) for line in lines]

def convert_number_to_chinese(number: int):
    number_dict = {
        '0': '零',
        '1': '一',
        '2': '二',
        '3': '三',
        '4': '四',
        '5': '五',
        '6': '六',
        '7': '七',
        '8': '八',
        '9': '九'
    }
    number_str = str(number)
    return ''.join([number_dict.get(x) for x in number_str])

def load_font_for_char(char, fonts, font_size):
    """
    从字体列表中为指定字符查找合适的字体
    :param char: 指定字符
    :param fonts: 字体列表
    :param font_size: 字体大小
    :return: 包含该字符的字体
    """
    for font_path in fonts:
        font = ImageFont.truetype(font_path, font_size)
        if font.getmask(char).getbbox():
            return font
    return


def cut(text, length):
    if not text:
        return []
    return [text[i:i + length] for i in range(0, len(text), length)]


def calculate_remain_char_space(remain_height, char_height, is_annotation=False):
    if is_annotation:
        return remain_height // char_height * 2
    return remain_height // char_height


def calculate_remain_height(line, text_box_height, chapter_char_height, content_char_height, annotation_char_height):
    used_height = 0
    for item in line:
        match item.get('type'):
            case 'chapter':
                used_height += chapter_char_height * len(item.get('value'))
            case 'content':
                used_height += content_char_height * len(item.get('value'))
            case 'annotation':
                used_height += annotation_char_height * math.ceil(len(item.get('value')) / 2)
    return text_box_height - used_height


def adjust_font(params):
    width = params.get('width')
    height = params.get('height')
    chapter_font_paths = params.get('chapter_font_paths')
    chapter_font_size = params.get('chapter_font_size')
    content_font_paths = params.get('content_font_paths')
    content_font_size = params.get('content_font_size')
    annotation_font_paths = params.get('annotation_font_paths')
    annotation_font_size = params.get('annotation_font_size')
    margin = params.get('margin')
    border = params.get('border')
    line_count = params.get('line_count')
    line_space = params.get('line_space')
    annotation_line_space = params.get('annotation_line_space')

    text_box_width = width - margin[2] - margin[3] - border * 2 - 6
    text_box_height = height - margin[0] - margin[1] - border * 2 - 6
    tz_line_count = 2 * line_count + 1
    chapter_font_size, chapter_char_width, chapter_char_height = calculate_font_size(chapter_font_paths[0],
                                                                                     chapter_font_size,
                                                                                     text_box_width,
                                                                                     line_count=tz_line_count,
                                                                                     line_space=line_space)
    content_font_size, content_char_width, content_char_height = calculate_font_size(content_font_paths[0],
                                                                                     content_font_size,
                                                                                     text_box_width,
                                                                                     line_count=tz_line_count,
                                                                                     line_space=line_space)
    annotation_font_size, annotation_char_width, annotation_char_height = calculate_font_size(
        annotation_font_paths[0], annotation_font_size, text_box_width, line_count=tz_line_count,
        line_space=line_space, is_annotation=True, annotation_line_space=annotation_line_space)
    params['chapter_font_size'] = chapter_font_size
    params['chapter_content_font_size'] = content_font_size
    params['annotation_font_size'] = annotation_font_size
    params['chapter_char_width'] = chapter_char_width
    params['chapter_char_height'] = chapter_char_height
    params['content_char_width'] = content_char_width
    params['content_char_height'] = content_char_height
    params['annotation_char_width'] = annotation_char_width
    params['annotation_char_height'] = annotation_char_height
    params['text_box_width'] = text_box_width
    params['text_box_height'] = text_box_height

    return params


def split_paragraph(paragraph, text_box_height, content_char_height, annotation_char_height):
    """
    将段落文本进一步分割为行
    :param paragraph: 文本段落
    :param text_box_height: 文本框高度
    :param content_char_height: 正文字体高度
    :param annotation_char_height: 批注字体高度
    :return: 分割后的文本行列表
    """
    max_content_chars_per_line = text_box_height // content_char_height
    # 双行夹注
    max_annotation_chars_per_line = text_box_height // annotation_char_height * 2

    sentences = paragraph.get('texts')
    annotations = paragraph.get('annotations')
    lines = []
    remain_height = text_box_height
    for i in range(len(sentences)):
        sentence = sentences[i]
        annotation = None
        if i < len(annotations):
            annotation = annotations[i]
        if remain_height < text_box_height:
            remain_content_char_space = remain_height // content_char_height
            if remain_content_char_space == 0:
                remain_height = text_box_height
            elif remain_content_char_space < len(sentence):
                lines[-1].append(dict(type=TextType.CONTENT, value=sentence[0:remain_content_char_space]))
                remain_height = text_box_height
                sentence = sentence[remain_content_char_space:]
            else:
                lines[-1].append(dict(type=TextType.CONTENT, value=sentence))
                remain_height -= len(sentence) * content_char_height
                sentence = None
        for part in cut(sentence, max_content_chars_per_line):
            lines.append([dict(type=TextType.CONTENT, value=part)])
            if len(part) < max_content_chars_per_line:
                remain_height -= len(part) * content_char_height
            else:
                remain_height = text_box_height
        if annotation:
            if remain_height < text_box_height:
                remain_annotation_char_space = remain_height // annotation_char_height * 2
                if remain_annotation_char_space == 0:
                    remain_height = text_box_height
                elif remain_annotation_char_space < len(annotation):
                    lines[-1].append(dict(type=TextType.ANNOTATION, value=annotation[0:remain_annotation_char_space]))
                    remain_height = text_box_height
                    annotation = annotation[remain_annotation_char_space:]
                else:
                    lines[-1].append(dict(type=TextType.ANNOTATION, value=annotation))
                    remain_height -= (math.ceil(len(annotation) / 2)) * annotation_char_height
                    annotation = None
        for part in cut(annotation, max_annotation_chars_per_line):
            lines.append([dict(type=TextType.ANNOTATION, value=part)])
            if len(part) < max_annotation_chars_per_line - 1:
                remain_height -= math.ceil(len(part) / 2) * annotation_char_height
            else:
                remain_height = text_box_height
    return lines


def split_text(texts, params):
    """
    对加载的文本进一步分割成行
    :param texts:
    :param params:
    :return:
    """
    text_box_height = params.get('text_box_height')
    chapter_char_height = params.get('chapter_char_height')
    content_char_height = params.get('content_char_height')
    annotation_char_height = params.get('annotation_char_height')
    line_count = params.get('line_count')
    bookname = params.get('bookname')

    max_chapter_chars_per_line = text_box_height // chapter_char_height
    max_content_chars_per_line = text_box_height // content_char_height
    max_annotation_chars_per_line = text_box_height // annotation_char_height * 2

    text_lines = []
    for chapter in texts:
        # 分割章节名及批注
        chapter_name = chapter.get('chapter')
        chapter_annotation = chapter.get('annotation')
        for chapter_sec in cut(chapter_name, max_chapter_chars_per_line):
            line = [{'type': TextType.CHAPTER, 'value': chapter_sec}]
            text_lines.append(line)
        if chapter_annotation:
            remain_height = calculate_remain_height(text_lines[-1], text_box_height, chapter_char_height,
                                                    content_char_height, annotation_char_height)
            remain_annotation_char_space = calculate_remain_char_space(remain_height, annotation_char_height,
                                                                       is_annotation=True)
            if len(chapter_annotation) <= remain_annotation_char_space:
                text_lines[-1].append({'type': TextType.ANNOTATION, 'value': chapter_annotation})
            else:
                text_lines[-1].append(
                    {'type': TextType.ANNOTATION, 'value': chapter_annotation[0:remain_annotation_char_space]})
                chapter_annotation = chapter_annotation[remain_annotation_char_space:]
                for annotation_sec in cut(chapter_annotation, max_annotation_chars_per_line):
                    line = [{'type': TextType.ANNOTATION, 'value': annotation_sec}]
                    text_lines.append(line)
        contents = chapter.get('content')
        for paragraph in contents:
            lines = split_paragraph(paragraph, text_box_height, content_char_height, annotation_char_height)
            text_lines.extend(lines)

        if len(text_lines) % line_count != 0:
            text_lines.extend([[] for _ in range(line_count - (len(text_lines) % line_count) - 1)])
            text_lines.append([dict(type=TextType.CHAPTER, value=f'{bookname} {chapter_name}')])

    return text_lines


def load_text(file_path):
    """
    载入TXT文本文件，提取书名以及包含章节名、正文和批注的章节字典列表
    :param file_path: TXT文本文件路径
    :return: 书名，章节字典列表
    """
    file_path_without_ext, ext = os.path.splitext(file_path)
    bookname = os.path.basename(file_path_without_ext)

    sections = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 跳过空白行
            if not line.strip():
                continue
            # 以#开头的行为章节名
            elif line.startswith('#'):
                chapter_name = line.strip('#')
                # 检查是否有批注
                match = re.search(r'【(.*?)】$', chapter_name)
                if match:
                    annotation = match.group(1)
                    chapter_name = chapter_name[:match.start()].strip()
                else:
                    annotation = None
                sections.append({
                    'chapter': chapter_name,
                    'annotation': annotation,
                    'content': []
                })
            else:
                # 提取正文和批注
                pattern = r'([^【]*)(?:【(.*?)】)*'
                matches = re.findall(pattern, line)
                contents = []
                annotations = []
                for match in matches:
                    content_part = match[0].strip()
                    annotation_part = match[1] if match[1] else None
                    if content_part:
                        contents.append(content_part.strip())
                    if annotation_part:
                        annotations.append(annotation_part.strip())
                if sections:
                    sections[-1]['content'].append({'texts': contents, 'annotations': annotations})
        return bookname, sections


def calculate_font_size(font_path, font_size, text_box_width, line_count=10, line_space=5, is_annotation=False,
                        annotation_line_space=5):
    """
    根据初始字体字号判断是否文本框是否能容纳该字号的文本，如果超出文本框，则计算一个合适的字体字号
    :param font_path: 字体文件路径
    :param font_size: 初始字体字号
    :param text_box_width: 文本框宽度
    :param line_count: 文本框分行数
    :param line_space: 行间距
    :param is_annotation: 是否是批注文字
    :param annotation_line_space: 双行夹批行间距， is_annotation为True时有效
    :return: 最终计算出的字体字号，文字宽度，文字高度
    """
    for size in range(font_size, 0, -1):
        font = ImageFont.truetype(font_path, size)
        char_width, char_height = font.getbbox('字')[2], font.getbbox('字')[3]
        if is_annotation:
            if line_count * (2 * char_width + annotation_line_space + line_space) - line_space > text_box_width:
                continue
            else:
                break
        else:
            if line_count * (char_width + line_space) - line_space > text_box_width:
                continue
            else:
                break

    return size, char_width, char_height


def add_noise(image, noise_level=0.01):
    """
    为图片添加噪点 (目前效果不理想)
    :param image:
    :param noise_level:
    :return:
    """
    LOGGER.info('为图片添加噪点')
    width, height = image.size
    pixels = image.load()

    for i in range(width):
        for j in range(height):
            if random.random() < noise_level:
                noise_color = random.randint(0, 255)
                pixels[i, j] = (noise_color, noise_color, noise_color)
    return image


def apply_vintage_effect(image, blur_radius=1, contrast_factor=0.8, color_factor=0.7):
    """
    应用做旧效果，包括模糊处理，降低对比度和降低饱和度
    :param image: 待处理的图像
    :param blur_radius: 模糊像素
    :param contrast_factor: 对比度降低比例
    :param color_factor: 饱和度降低比例
    :return: 做旧之后的图像
    """
    LOGGER.info('为图片添加做旧效果')
    # 应用高斯模糊效果
    image = image.filter(ImageFilter.GaussianBlur(blur_radius))

    # 调整对比度
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast_factor)

    # 调整饱和度
    enhancer = ImageEnhance.Color(image)
    enhancer.enhance(color_factor)

    return image


def create_gradient_mask(size):
    """创建一个渐变遮罩，边缘颜色为黄色，中间为白色"""
    mask = Image.new('L', size, 0)  # 灰度图
    draw = ImageDraw.Draw(mask)

    width, height = size
    center_x, center_y = width // 2, height // 2
    max_radius = min(center_x, center_y)

    for i in range(max_radius):
        # 计算每个环的颜色值，边缘更深
        value = int(255 * (1 - i / max_radius))
        draw.ellipse((center_x - i, center_y - i, center_x + i, center_y + i), fill=value)

    return mask


def apply_yellowed_page_effect_with_gradient(image):
    """应用带渐变的书页发黄效果"""
    # 生成渐变遮罩
    mask = create_gradient_mask(image.size)

    # 将图像转换为RGBA格式
    image = image.convert("RGBA")

    # 获取每个像素
    data = image.getdata()
    new_data = []

    for item in data:
        r, g, b, a = item
        # 调整颜色，使其变黄
        r = int(r * 1.3)
        g = int(g * 1.3)
        b = int(b * 0.7)

        r = min(255, r)
        g = min(255, g)
        b = min(255, b)

        new_data.append((r, g, b, a))

    # 更新图像数据
    image.putdata(new_data)

    # 应用渐变遮罩
    yellowed_image = Image.new("RGBA", image.size)
    yellowed_image.putdata(new_data)

    # 将原图像与发黄效果结合，使用遮罩控制
    final_image = Image.composite(yellowed_image, image, mask)

    return final_image


def gen_image_with_fixed_size(lines, params, output_path):
    """
    生成排版好的图片
    :return:
    """

    width = params.get('width')
    height = params.get('height')
    margin = params.get('margin')
    border = params.get('border')
    line_count = params.get('line_count')
    line_space = params.get('line_space')
    annotation_line_space = params.get('annotation_line_space')
    annotation_char_width = params.get('annotation_char_width')
    content_char_height = params.get('content_char_height')

    LOGGER.info("开始生成图片")

    image, draw, line_width = init_image(params)

    # 逐个字符绘制图像
    LOGGER.info('开始绘制文本')
    for line_index, line in enumerate(lines):
        # 筒子页中间行不绘制正文
        if line_index >= line_count:
            line_index += 1
        x = width - margin[3] - (line_index + 1) * line_width - border - 3 + line_space * 2
        y = margin[0] + border + 3
        y_anno_start = 0
        y_anno_end = 0
        font_paths = []
        font_size = 0
        font_color = 'black'
        char_height = 0
        for i in range(len(line)):
            item = line[i]
            x_offset = 0
            text_type = item.get('type')
            text = item.get('value')
            if i == len(line) - 1 and i != 0 and text_type is TextType.CONTENT:
                y = height - margin[1] - border - 3 - len(text) * content_char_height
            match text_type:
                case TextType.CHAPTER:
                    font_paths = params.get('chapter_font_paths')
                    font_size = params.get('chapter_font_size')
                    font_color = params.get('chapter_font_color')
                    char_height = params.get('chapter_char_height')
                case TextType.CONTENT:
                    font_paths = params.get('content_font_paths')
                    font_size = params.get('content_font_size')
                    font_color = params.get('content_font_color')
                    char_height = params.get('content_char_height')
                case TextType.ANNOTATION:
                    font_paths = params.get('annotation_font_paths')
                    font_size = params.get('annotation_font_size')
                    font_color = params.get('annotation_font_color')
                    char_height = params.get('annotation_char_height')
                    x_offset = annotation_char_width + annotation_line_space - line_space
                    x = x + x_offset
                    y_anno_start = y

            text_length = len(text)
            for i in range(text_length):
                char = text[i]
                font = load_font_for_char(char, font_paths, font_size)
                if font:
                    draw.text((x, y), char, font=font, fill=font_color)
                if text_type == TextType.ANNOTATION and i == math.ceil(text_length / 2) - 1:
                    x = x - x_offset
                    y_anno_end = y + char_height
                    y = y_anno_start
                else:
                    y += char_height
            if text_type == TextType.ANNOTATION:
                y = y_anno_end

    x = width - margin[3] - border - 3 - (line_count + 1) * line_width + params.get('line_space')
    y = margin[0] + border + 3
    draw_middle_line(draw, x, y, params.get('bookname'), params)
    LOGGER.info(f'文本绘制完成, 圖片保存至{output_path}')
    image.save(output_path)


def gen_images(texts, params):
    """
    并发生成多页
    :param texts: 待输入的文本
    :param font_paths: 字体文件路径列表
    :param font_size: 字体大小
    :param annotation_font_paths: 批注字体路径列表
    :param annotation_font_size: 批注字体大小
    :param output_dir: 图片生成目录
    :param width: 图片的宽（像素）
    :param height: 图片的高（像素）
    :param line_count: 每页的行数
    :param line_space: 行间距
    :param annotation_line_space: 双行夹注的行间距
    :param margin: 页而边距(上，下，左，右)
    :param border: 边框宽度
    :param backgroud: 背景图片
    :param line_sep: 是否绘制行分隔线
    :param line_sep_color: 行分隔线颜色，line_sep为True时有效
    :param line_sep_width: 行分隔线宽度，line_sep为True时有效
    :param with_noise: 是否添加噪点
    :param noise_level: 噪点等级，with_noise为True时有效
    :param older: 是否添加做旧效果
    :param bg_color: 背景底图颜色
    :return:
    """
    output_dir = params.get('output_dir')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    elif not os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
        os.makedirs(output_dir)

    lines = split_text(texts, params)
    line_count = params.get('line_count')
    if len(lines) > line_count * 2:
        with Pool(processes=10) as pool:
            tasks = []
            for i in range(math.ceil(len(lines) / (line_count * 2))):
                part = lines[i * line_count * 2: line_count * 2 * (i + 1)]
                output_path = os.path.join(output_dir, f'第{convert_number_to_chinese(i + 1)}頁.png')
                tasks.append(pool.apply_async(
                    gen_image_with_fixed_size, (part, params, output_path)))

            for task in tasks:
                try:
                    task.get()
                except Exception as e:
                    LOGGER.exception(e)
    else:
        output_path = os.path.join(output_dir, 'page-1.png')
        gen_image_with_fixed_size(lines, params, output_path)


def init_image(params):
    """
    根据参数绘制底图
    :param params:
    :return:
    """
    scale_factor = 4
    width = params.get('width')
    height = params.get('height')
    margin = params.get('margin')
    border = params.get('border')

    LOGGER.info('计算文本边框尺寸')
    # 文本框宽度为内框宽度
    text_box_width = width - margin[2] - margin[3] - border * 2 - 6

    # 筒子页是两页对折，中间一行是书口，一个筒子页总行数为 line_count * 2 + 1
    line_width = text_box_width / (params.get('line_count') * 2 + 1)

    if params.get('background'):
        LOGGER.info('生成带背景的底图')
        bg_image = Image.open(params.get('background')).resize(width, height)
        image = Image.new('RGB', (width, height))
        image.paste(bg_image)
    else:
        LOGGER.info('生成底图')
        image = Image.new('RGB', (width, height), color=params.get('bg_color'))

    image_fishtail = Image.new('RGB', (scale_factor * width, scale_factor * height), color=params.get('bg_color'))

    fishtail_draw = ImageDraw.Draw(image_fishtail)
    center_x = width - margin[3] - border - 3 - line_width * params.get('line_count')
    center_y = margin[0] + border + 3 + (len(params.get('bookname')) + 1) * params.get('chapter_char_height')
    draw_fishtail(fishtail_draw, scale_factor * center_x, scale_factor * center_y, scale_factor * line_width)
    layer_fishtail = image_fishtail.resize((width, height), Image.Resampling.LANCZOS)

    image.paste(layer_fishtail)

    draw = ImageDraw.Draw(image)

    LOGGER.info('绘制边框')
    draw.rectangle([margin[2], margin[0], width - (margin[3]), height - margin[1]], outline=params.get('border_color'),
                   width=border)
    draw.rectangle([margin[2] + border + 2, margin[0] + border + 2, width - margin[3] - border - 2,
                    height - margin[1] - border - 2], outline=params.get('border_color'), width=1)

    if params.get('line_sep'):
        LOGGER.info('绘制行分隔线')
        for i in range(params.get('line_count') * 2):
            x = width - margin[3] - (i + 1) * line_width - border - 3
            draw.line([(x, margin[0] + border + 3), (x, height - margin[1] - border - 3)],
                      fill=params.get('line_sep_color'), width=params.get('line_sep_width'))

    return image, draw, line_width


def draw_fishtail(draw, x, y, line_width, color='black'):
    """
    绘制一个简单的对称鱼尾图案。

    :param draw: ImageDraw 对象
    :param x: 图案右顶点X坐标
    :param y: 图案右顶点Y坐标
    :param line_width: 中间行宽度
    :param color: 图案颜色
    """
    # 定义鱼尾的几个关键点（简单的对称多边形）
    points = [
        (x, y),  # 右上顶点
        (x, y + 80),  # 右下顶点
        (x - line_width / 2, y + 40),  # 中间转折点
        (x - line_width, y + 80),  # 左下顶点
        (x - line_width, y)  # 左上顶点
    ]

    # 绘制多边形
    draw.polygon(points, fill=color, outline=color)
    draw.line([(x, y - 16), (x - line_width, y - 16)], fill='black', width=4)
    draw.line([(x, y + 96), (x - line_width / 2, y + 56)], fill='black', width=4)
    draw.line([(x - line_width / 2, y + 56), (x - line_width, y + 96)], fill='black', width=4)


def draw_middle_line(draw, x, y, bookname, params):
    font_paths = params.get('chapter_font_paths')
    font_size = params.get('chapter_font_size')
    char_height = params.get('chapter_char_height')

    bookname_length = len(bookname)
    for i in range(bookname_length):
        char = bookname[i]
        font = load_font_for_char(char, font_paths, font_size)
        if font:
            draw.text((x, y), char, font=font, fill='black')
            y += char_height


def main():
    input_path = 'input/孙子兵法.txt'
    bookname, texts = load_text(input_path)
    font_paths = ['fonts/ZiYue_Song_Keben_GBK_Updated.ttf', 'fonts/ZiYue_Song_Keben_Tranditional_Supplimentary.otf',
                  'fonts/FangSong.ttf', 'fonts/WenYue_GuTi_FangSong.otf',
                  'fonts/HanYi_ChangLi_Song_Keben_JingXiu.ttf', 'fonts/FangZheng_Song_Keben_XiuKai_GBK.TTF']
    output_dir = os.path.join('output', bookname)
    params = get_params(chapter_font_paths=font_paths, chapter_font_size=50, content_font_paths=font_paths,
                        content_font_size=40, annotation_font_paths=font_paths, annotation_font_size=30,
                        annotation_line_space=3, line_space=5, output_dir=output_dir)
    params = adjust_font(params)
    params['bookname'] = bookname
    gen_images(texts, params)



if __name__ == '__main__':
    main()
