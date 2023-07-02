"""Image converter constants"""


import re


EXT_BMP = 'bmp'
EXT_GIF = 'gif'
EXT_JPG = 'jpg'
EXT_PNG = 'png'
EXT_TIFF = 'tiff'
EXT_WEBP = 'webp'
EXT_MATCHERS = {
    EXT_BMP: re.compile(r'bmp', flags=re.IGNORECASE),
    EXT_GIF: re.compile(r'gif', flags=re.IGNORECASE),
    EXT_JPG: re.compile(r'(jpg|jpeg)', flags=re.IGNORECASE),
    EXT_PNG: re.compile(r'png', flags=re.IGNORECASE),
    EXT_TIFF: re.compile(r'(tif|tiff)', flags=re.IGNORECASE),
    EXT_WEBP: re.compile(r'webp', flags=re.IGNORECASE),
}
EXTENSIONS = set(EXT_MATCHERS)
ERR_IMAGE_OPEN = 'ERR_IMAGE_OPEN'
ERR_IMAGE_SAVE = 'ERR_IMAGE_SAVE'
STATUS_OK = 0
ERR_FOLDER_INVALID = 1
ERR_FOLDER_DOES_NOT_EXIST = 1 << 1
ERR_PATH_IS_NOT_FOLDER = 1 << 2
CANCELED = 'CANCELED'
ERRORS = 'ERRORS'
OUTPUTS = 'OUTPUTS'
TARGETS = 'TARGETS'
