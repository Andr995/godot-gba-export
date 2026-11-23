"""PNG -> tile GBA e WAV -> input Maxmod. Solo standard library, nessun asset esterno."""
from pathlib import Path
import struct
import wave
import zlib


class ExportError(Exception):
    def __init__(self, path, line, message, code='GBA001'):
        self.path, self.line, self.message, self.code = str(path).replace('\\', '/'), max(1, line), message, code
        super().__init__(f'{self.path}:{self.line}: error {code}: {message}')


def read_png(path, allow_partial=False):
    raw = Path(path).read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ExportError(path, 1, 'Firma PNG non valida')
    offset, packed, palette, alpha = 8, bytearray(), [], b''
    header = None
    ended = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ExportError(path, 1, 'Chunk PNG troncato')
        size = struct.unpack_from('>I', raw, offset)[0]
        kind, data = raw[offset + 4:offset + 8], raw[offset + 8:offset + 8 + size]
        if offset + 12 + size > len(raw) or zlib.crc32(kind + data) & 0xffffffff != struct.unpack_from('>I', raw, offset + 8 + size)[0]:
            raise ExportError(path, 1, 'CRC PNG errato o chunk troncato')
        offset += size + 12
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', data)
        elif kind == b'PLTE':
            if len(data) % 3: raise ExportError(path, 1, 'Palette PNG non valida')
            palette = [tuple(data[i:i + 3]) for i in range(0, len(data), 3)]
        elif kind == b'tRNS': alpha = data
        elif kind == b'IDAT': packed.extend(data)
        elif kind == b'IEND': ended = True; break
        elif kind[:1].isupper(): raise ExportError(path, 1, 'Chunk PNG critico sconosciuto: ' + kind.decode('ascii', 'replace'))
    if header is None or not ended:
        raise ExportError(path, 1, 'PNG senza IHDR/IEND')
    width, height, depth, color, compression, filtering, interlaced = header
    if not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 4194304:
        raise ExportError(path, 1, 'PNG oltre il limite di conversione 4 megapixel')
    if interlaced or compression or filtering or color not in (0, 2, 3, 4, 6) or (depth != 8 and not (color == 3 and depth in (1, 2, 4))):
        raise ExportError(path, 1, 'PNG supportati: RGB/RGBA/grigio 8 bit o indicizzati 1/2/4/8 bit, non interlacciati')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    stride, bpp = (width * channels * depth + 7) // 8, max(1, channels * depth // 8)
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(packed, (stride + 1) * height + 1)
    if len(decoded) != (stride + 1) * height or not decoder.eof:
        raise ExportError(path, 1, 'Dimensione dati PNG non valida')
    previous = bytearray(stride)
    pixels = []
    for y in range(height):
        method = decoded[y * (stride + 1)]
        row = bytearray(decoded[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if method > 4: raise ExportError(path, 1, 'Filtro PNG non valido')
        for x in range(stride):
            a, b, c = row[x - bpp] if x >= bpp else 0, previous[x], previous[x - bpp] if x >= bpp else 0
            if method == 1: predictor = a
            elif method == 2: predictor = b
            elif method == 3: predictor = (a + b) // 2
            elif method == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
            else: predictor = 0
            row[x] = (row[x] + predictor) & 255
        for x in range(width):
            if color == 3:
                index = (row[x * depth // 8] >> (8 - depth - (x * depth % 8))) & ((1 << depth) - 1)
                if index >= len(palette): raise ExportError(path, 1, 'Indice palette PNG non valido')
                pixel = (*palette[index], alpha[index] if index < len(alpha) else 255)
            elif color == 6: pixel = tuple(row[x * 4:x * 4 + 4])
            elif color == 2:
                rgb = tuple(row[x * 3:x * 3 + 3])
                pixel = (*rgb, 0 if len(alpha) == 6 and rgb == struct.unpack('>HHH', alpha) else 255)
            else:
                value = row[x * channels]
                opacity = row[x * 2 + 1] if color == 4 else 0 if len(alpha) == 2 and value == int.from_bytes(alpha, 'big') else 255
                pixel = (value, value, value, opacity)
            if pixel[3] not in (0, 255) and not allow_partial:
                raise ExportError(path, 1, 'Alpha parziale non supportato dagli OBJ/BG GBA; serve un asset con alpha binario')
            if allow_partial: pixel=(*pixel[:3],255 if pixel[3]>=128 else 0)
            pixels.append(pixel)
        previous = row
    return width, height, pixels


def rgb555(pixel):
    return (pixel[0] >> 3) | ((pixel[1] >> 3) << 5) | ((pixel[2] >> 3) << 10)


def make_palette(images, bpp):
    colors = sorted({rgb555(p) for _, _, pixels in images for p in pixels if p[3]})
    limit = (1 << bpp) - 1
    if len(colors) > limit:
        raise ExportError('assets', 1, f'{len(colors)} colori RGB555 opachi; massimo {limit} con {bpp}bpp. Ridurre esplicitamente la palette.')
    return [0] + colors + [0] * (limit - len(colors)), {c: i + 1 for i, c in enumerate(colors)}


def tiles(image, colors, bpp, region=None, size=None):
    width, height, pixels = image
    rx, ry, rw, rh = region or (0, 0, width, height)
    tw, th = size or (((rw + 7) // 8) * 8, ((rh + 7) // 8) * 8)
    result = bytearray()
    for by in range(0, th, 8):
        for bx in range(0, tw, 8):
            indices = []
            for y in range(8):
                for x in range(8):
                    ix, iy = bx + x, by + y
                    p = pixels[(ry + iy) * width + rx + ix] if ix < rw and iy < rh else (0, 0, 0, 0)
                    indices.append(colors[rgb555(p)] if p[3] else 0)
            result.extend(indices if bpp == 8 else [indices[i] | (indices[i + 1] << 4) for i in range(0, 64, 2)])
    return bytes(result)


OBJ_SIZES = [(8, 8, 0, 0), (16, 16, 0, 1), (32, 32, 0, 2), (64, 64, 0, 3),
             (16, 8, 1, 0), (32, 8, 1, 1), (32, 16, 1, 2), (64, 32, 1, 3),
             (8, 16, 2, 0), (8, 32, 2, 1), (16, 32, 2, 2), (32, 64, 2, 3)]


def obj_size(width, height, path):
    choices = [s for s in OBJ_SIZES if s[0] >= width and s[1] >= height]
    if not choices:
        raise ExportError(path, 1, f'Frame {width}×{height} troppo grande per un OBJ (massimo 64×64)')
    return min(choices, key=lambda s: s[0] * s[1])


def convert_wav(source, target, rate=11025):
    try:
        with wave.open(str(source), 'rb') as wav:
            channels, width, frequency, count = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
            if channels not in (1, 2) or width not in (1, 2) or wav.getcomptype() != 'NONE':
                raise ExportError(source, 1, 'Maxmod: richiesto WAV PCM 8/16 bit mono/stereo')
            if count * rate // frequency > 32 * 1024 * 1024:
                raise ExportError(source, 1, 'Il solo audio supera la ROM GBA da 32 MiB')
            raw = wav.readframes(count)
            if len(raw) != count * channels * width or count < 1:
                raise ExportError(source, 1, 'WAV vuoto o troncato')
    except (wave.Error, EOFError) as exc:
        raise ExportError(source, 1, 'WAV non valido: ' + str(exc)) from exc
    samples = []
    for i in range(count):
        total = 0
        for channel in range(channels):
            offset = (i * channels + channel) * width
            total += ((raw[offset] - 128) << 8) if width == 1 else struct.unpack_from('<h', raw, offset)[0]
        samples.append(total // channels)
    output = bytearray()
    # Media sull'intervallo: filtro box contro aliasing nel downsampling, senza dipendenze.
    for i in range(max(1, count * rate // frequency)):
        start = min(count - 1, i * frequency // rate)
        end = min(count, max(start + 1, (i + 1) * frequency // rate))
        value = sum(samples[start:end]) // (end - start)
        output.append(max(0, min(255, (value >> 8) + 128)))
    with wave.open(str(target), 'wb') as wav:
        wav.setparams((1, 1, rate, len(output), 'NONE', 'not compressed'))
        wav.writeframes(output)
    return len(output)


def c_array(name, data, kind='unsigned char'):
    numbers = list(data)
    lines = [','.join(str(v) for v in numbers[i:i + 32]) for i in range(0, len(numbers), 32)]
    return f'const {kind} {name}[{max(1, len(numbers))}] __attribute__((aligned(4))) = {{\n' + ',\n'.join(lines or ['0']) + '\n};\n'
