from abc import abstractproperty
from concurrent.futures import ThreadPoolExecutor
from csnake import CodeWriter, Variable
from io import BytesIO, FileIO
import os.path
import subprocess
from csnake.cconstructs import FormattedLiteral
import numpy as np
# from shellescape import quote
from shlex import quote
from imageio import imread
import glob
from tqdm import tqdm
import math
import re
import json

fileName = 'image.png'
bpp = 2

tr = str.maketrans({
    '\\': '\\\\',
    ' ': '\\ ',
})


def to_snake_case(name):
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    name = re.sub('__([A-Z])', r'_\1', name)
    name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    return name.lower()


def q(c):
    return quote(c.translate(tr))


def rowToInt(row):
    return sum(v << (i * bpp) for i, v in enumerate(reversed(row)))


width = 12

# characters = 'abcdefghijklmnñopqrstuvwxyzABCDEFGHIJKLMNÑOPQRSTUVWXYZ áéíóúÁÉÍÓÚ´üÜ1234567890!"#$%&/()={{}}[]\\|/ -_=+`~\'\"'

# for row in charToBitmap('N'):
#     print(bin(row))
# exit()


class Font:
    @property
    def primitive(self):
        return min(filter(lambda b: b > self.bpp * self.width, [8, 16, 32, 64]))

    @property
    def bpp(self):
        return 1

    @property
    def offset(self):
        return 0

    @abstractproperty
    def name(self) -> str: ...


class ImageMagickFont(Font):
    def __init__(self, fontName: str) -> None:
        self.fontName = fontName

    def charToBitmap(self, l: str):
        # if l in characters:
        if l.isprintable():
            imageBytes = subprocess.check_output(
                f'convert -geometry {width}x -font "{self.fontName}" -pointsize 30 label:{q(l)} -depth {bpp} png:-', shell=True)

            file = BytesIO(imageBytes)
            img = imread(file)
            maxValue = 1 << bpp
            img = maxValue - img//(256//maxValue) - 1
            # img = img//(256//maxValue)
            return tuple(rowToInt(row) for row in np.array(img))
        return self.charToBitmap(' ')

    @property
    def width(self):
        return width

    @property
    def bpp(self):
        return bpp

    @property
    def name(self):
        return os.path.splitext(os.path.basename(self.fontName))[0]


class JSONFont(Font):
    def __init__(self, title: str, fontWidth: int, file: FileIO) -> None:
        self.data = json.load(file)
        self.title = title
        self.fontWidth = fontWidth

    def charToBitmap(self, l: str):
        if l in self.data:
            return tuple(int(bin(i)[2:].zfill(self.width)[::-1], 2) for i in self.data[l])
        return self.charToBitmap(' ')

    @property
    def offset(self):
        return 1

    @property
    def width(self):
        return self.fontWidth

    @property
    def name(self):
        return self.title


def createFontBitmap(font: Font, encoding='latin-1'):
    uniqueLetters = []
    letterMappings = []
    for b in tqdm(range(256), desc=font.name, leave=True):
        l = bytes([b]).decode('latin-1')
        # print(f'{b}/256')

        bit = font.charToBitmap(l)
        if bit not in uniqueLetters:
            uniqueLetters.append(bit)
        i = uniqueLetters.index(bit)
        letterMappings.append(i)

    fontSnake = to_snake_case(font.name).replace('-', '_').replace('.', '_')

    height = len(uniqueLetters[0])
    primitiveType = font.primitive

    font_letters = Variable(f'{fontSnake}_letters', primitive=f'uint{primitiveType}_t', value=[
                            [FormattedLiteral(row, int_formatter=lambda x:hex(x)) for row in l] for l in uniqueLetters])
    font_mapping = Variable(f'{fontSnake}_mapping', primitive=f'uint8_t', value=[
                            FormattedLiteral(i, int_formatter=hex) for i in letterMappings])

    header = CodeWriter()
    header.add('#pragma once')
    header.start_comment()
    header.add('\n\t\tAuthor: Alan Sartorio')
    header.add('\n\tThis file was automatically generated with a python script')
    header.end_comment()
    header.include('<stdint.h>')
    header.add_define('FONT_WIDTH', value=font.width + font.offset)
    header.add_define('FONT_HEIGHT', value=height)
    header.add_define('FONT_BPP', value=bpp)
    header.add(f'\ntypedef uint{primitiveType}_t FONT_ROW_TYPE;')
    header.add_variable_declaration(font_letters, True)
    header.add_variable_declaration(font_mapping, True)

    code = CodeWriter()
    code.include(f'"{font.name}.h"')
    code.add_variable_initialization(font_letters)
    code.add_variable_initialization(font_mapping)

    return header.code, code.code
    # cw.write_to_file(f'fonts/{os.path.basename(font)}.h')


def doFont(font: Font):
    # print(f'Processing font {font}...')
    header, code = createFontBitmap(font)
    with open(f'headers/{font.name}.h', 'w') as headerFile:
        headerFile.write(header)
    with open(f'headers/{font.name}.c', 'w') as codeFile:
        codeFile.write(code)


fonts = [ImageMagickFont(font) for font in list(glob.glob(
    "fonts/*.ttf") + ['Noto-Sans-Mono-Regular'])] + [JSONFont('monogram', 5, open('fonts/monogram-bitmap.json'))]

with ThreadPoolExecutor(16) as pool:
    pool.map(doFont, fonts)
