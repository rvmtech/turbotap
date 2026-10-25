#!/usr/bin/env python3
"""
turbo_tap.py - convierte un TAP de una aventura DAAD Ready (ZX Spectrum 48K o 128K)
en una cinta de carga turbo (TZX y, opcionalmente, WAV).

uso:
    python3 turbo_tap.py juego.tap carpeta_salida nombre [--baud 3000] [--wav] [--info]

  --baud N     velocidad aproximada en baudios (por defecto 3000; el original va a ~1364).
               Valores razonables: 2250 (muy seguro), 3000, 3500, 4150.
  --wav        genera tambien nombre.wav (44,1 kHz, mono, 16 bits)
  --info       solo analiza el TAP y muestra lo que ha detectado (no escribe nada)

Requiere: Python 3.8+ y el ensamblador `pasmo` (en el PATH o junto a este script), y
loader.asm en la misma carpeta que este script.

Que hace:
  1. Lee el TAP: cargador BASIC, bloques con cabecera (pantalla, interprete, base de
     datos...) y, en 128K, los bloques de bancos sin cabecera.
  2. Busca en el interprete la rutina que carga cosas desde cinta con la ROM y la
     neutraliza con un parche minimo (1 byte en 128K, 3 bytes en 48K), porque el
     cargador turbo ya habra puesto todo en su sitio.
        - 128K: rutina de carga de bancos (tabla de bancos + LD-BYTES).
        - 48K : rutina que ejecuta "LOAD" de los bloques restantes (CALL $0708 de la ROM).
  3. Reescribe el cargador BASIC: las sentencias LOAD "" se sustituyen por
        LOAD ""CODE : RANDOMIZE USR <cargador turbo>
     (el resto del BASIC se conserva tal cual).
  4. Genera el cargador turbo (Z80), la tabla de bloques y la cinta TZX/WAV.
"""
import struct, subprocess, sys, os, math, wave, array, re, argparse, tempfile, shutil

ITER = 45            # T-states por iteracion del bucle de muestreo del cargador
MAXCHUNK = 9000      # tamano maximo de cada bloque turbo en cinta
PILOT_PULSES = 700
PAUSE_MS = 250
NPILOT = 150
BORDER = 'rainbow'     # 'rainbow' (franjas multicolor) o 'classic' (2 colores)

# --------------------------------------------------------------------------- TAP
def read_tap(path):
    d = open(path, 'rb').read()
    p = 0; out = []
    while p < len(d):
        n = struct.unpack('<H', d[p:p+2])[0]
        b = d[p+2:p+2+n]
        if len(b) != n or n < 2:
            raise SystemExit('TAP corrupto')
        out.append(b); p += 2 + n
    return out

def xor(bs):
    x = 0
    for b in bs: x ^= b
    return x

class Tap:
    """Estructura del TAP: BASIC + bloques de codigo con cabecera + bloques sin cabecera"""
    def __init__(self, path):
        bl = read_tap(path)
        self.basic = None      # (nombre, autostart, longprog, datos)
        self.codes = []        # (nombre, dest, datos)
        self.raws = []         # (datos, byte_de_paridad_original)
        i = 0
        while i < len(bl):
            b = bl[i]
            if b[0] == 0 and len(b) == 19:
                typ = b[1]; name = b[2:12].decode('latin1')
                ln, p1, p2 = struct.unpack('<HHH', b[12:18])
                if i + 1 >= len(bl) or bl[i+1][0] != 0xFF:
                    raise SystemExit('cabecera sin bloque de datos')
                data = bl[i+1][1:-1]
                if typ == 0:
                    if self.basic: raise SystemExit('mas de un programa BASIC')
                    self.basic = (name, p1, p2, data)
                elif typ == 3:
                    self.codes.append((name, p1, data))
                else:
                    raise SystemExit(f'tipo de bloque no soportado: {typ}')
                i += 2
            elif b[0] == 0xFF:
                self.raws.append((b[1:-1], b[-1])); i += 1
            else:
                raise SystemExit(f'bloque inesperado (flag {b[0]:#x})')
        if not self.basic or not self.codes:
            raise SystemExit('no encuentro BASIC + bloques de codigo')

# ------------------------------------------------------------------- BASIC
def split_statements(content):
    """content = bytes de una linea sin el 0x0D final. Devuelve lista de sentencias (bytes)."""
    st = []; cur = bytearray(); inq = False; j = 0
    rem = False
    while j < len(content):
        c = content[j]
        if rem:
            cur.append(c); j += 1; continue
        if c == 0x22: inq = not inq
        if not inq and c == 0xEA and not cur.strip(b' ') :  # REM al principio de sentencia
            rem = True
        if not inq and c == 0x0E and j + 5 < len(content):
            cur.extend(content[j:j+6]); j += 6; continue
        if not inq and c == 0x3A:
            st.append(bytes(cur)); cur = bytearray(); j += 1; continue
        cur.append(c); j += 1
    st.append(bytes(cur))
    return st

def rewrite_basic(prog, loader_addr):
    """Sustituye las sentencias LOAD "" por LOAD ""CODE : RANDOMIZE USR VAL "addr"."""
    new = bytearray(); i = 0; replaced = False; nloads = 0
    while i + 4 <= len(prog):
        ln = (prog[i] << 8) | prog[i+1]
        l = prog[i+2] | (prog[i+3] << 8)
        body = prog[i+4:i+4+l]
        if body[-1:] != b'\r': raise SystemExit('linea BASIC mal formada')
        stm = split_statements(body[:-1]); i += 4 + l
        out = []
        for s in stm:
            t = s.lstrip(b' ')
            if t.startswith(b'\xef\x22\x22'):
                if len(t) != 4 or t[3] not in (0xAF, 0xAA):
                    raise SystemExit('sentencia LOAD con parametros no soportada')
                nloads += 1
                if not replaced:
                    out.append(b'\xef\x22\x22\xaf')
                    out.append(b'\xf9\xc0\xb0"' + str(loader_addr).encode() + b'"')
                    replaced = True
            else:
                out.append(s)
        if not out: continue          # linea que solo cargaba: se elimina
        nb = b':'.join(out) + b'\r'
        new += bytes([ln >> 8, ln & 255]) + struct.pack('<H', len(nb)) + nb
    if not replaced: raise SystemExit('el BASIC no contiene LOAD ""')
    return bytes(new), nloads

# -------------------------------------------------------- analisis del interprete
class Mem:
    def __init__(self, codes):
        self.codes = codes
    def find(self, addr):
        for name, dest, data in self.codes:
            if dest <= addr < dest + len(data): return data, addr - dest
        return None, 0
    def byte(self, a):
        d, o = self.find(a)
        if d is None: raise SystemExit(f'direccion {a:#x} fuera de los bloques cargados')
        return d[o]
    def word(self, a): return self.byte(a) | (self.byte(a+1) << 8)

PAT128 = re.compile(rb'\x21(..)\xdd\x21(..)\x11(..)\x7e\xfe\xff\xc8\xb7\x20.\xdd\x2a(..)\xed\x5b(..)\x18.\xfe\x01\x20.\xdd\x21(..)\x11(..)', re.S)
PAT48 = re.compile(rb'\xdd\xe5(\xcd\x08\x07)\xdd\xe1\xc9')
# DAAD Ready B 48K: rutina que carga con la ROM un bloque extra sin cabecera (longitud y direccion en variables del juego)
PAT48B = re.compile(rb'\x3e\xff\x32..\xed\x5b(..)\x7a\xb3\xc8\xdd\x2a(..)\x3e\xff\x37(\xcd\x56\x05)\xc9', re.S)

def analyze(tap):
    """Devuelve dict con modo, parches [(bloque, offset, bytes_nuevos, descripcion)] y bancos."""
    info = {'patches': [], 'banks': []}
    codes = [list(c) for c in tap.codes]
    mem = Mem(tap.codes)
    found128 = None
    for ci, (name, dest, data) in enumerate(codes):
        m = PAT128.search(data)
        if m: found128 = (ci, m); break
    if found128:
        ci, m = found128
        base = codes[ci][1]
        info['mode'] = 128
        info['patches'].append((ci, m.start(), b'\xC9',
            f'RET en ${base + m.start():04X} (inicio de la rutina de carga de bancos)'))
        tbl = struct.unpack('<H', m.group(1))[0]
        ddest, dlen = struct.unpack('<H', m.group(2))[0], struct.unpack('<H', m.group(3))[0]
        a0i, a0l = struct.unpack('<H', m.group(4))[0], struct.unpack('<H', m.group(5))[0]
        d1i, d1l = struct.unpack('<H', m.group(6))[0], struct.unpack('<H', m.group(7))[0]
        entries = []; a = tbl
        while True:
            v = mem.byte(a)
            if v == 0xFF: break
            entries.append(v); a -= 1
            if len(entries) > 32: raise SystemExit('tabla de bancos sin terminador')
        if len(entries) != len(tap.raws):
            raise SystemExit(f'la tabla de bancos tiene {len(entries)} entradas pero el TAP trae {len(tap.raws)} bloques sin cabecera')
        for v, (data_r, chk) in zip(entries, tap.raws):
            if v == 0:   bank, dst, req = 0, mem.word(a0i), mem.word(a0l)
            elif v == 1: bank, dst, req = 1, d1i, d1l
            else:        bank, dst, req = v, ddest, dlen
            if len(data_r) > req:
                raise SystemExit(f'banco {bank}: el bloque ({len(data_r)}) es mayor que lo que pide el interprete ({req})')
            stored = data_r + (bytes([chk]) if len(data_r) < req else b'')   # la ROM guardaba el byte de paridad
            info['banks'].append((bank, dst, stored))
        info['table'] = f'tabla de bancos en ${tbl:04X}: {entries}'
    else:
        info['mode'] = 48
        if tap.raws:
            hits = [(ci, m) for ci, (name, dest, data) in enumerate(codes) for m in PAT48B.finditer(data)]
            if len(hits) != 1 or len(tap.raws) != 1:
                raise SystemExit('hay bloques sin cabecera pero no reconozco la rutina de carga de bancos')
            ci, m = hits[0]
            base = codes[ci][1]
            lenaddr, ixaddr = struct.unpack('<H', m.group(1))[0], struct.unpack('<H', m.group(2))[0]
            req, dst = mem.word(lenaddr), mem.word(ixaddr)
            data_r, chk = tap.raws[0]
            if len(data_r) > req:
                raise SystemExit(f'el bloque extra ({len(data_r)}) es mayor que lo que pide el interprete ({req})')
            info['banks'].append((0, dst, data_r + (bytes([chk]) if len(data_r) < req else b'')))
            info['patches'].append((ci, m.start(3), b'\x00\x00\x00',
                f'NOP NOP NOP en ${base + m.start(3):04X} (sustituye CALL $0556 de la carga del bloque extra)'))
            info['table'] = f'bloque extra sin cabecera: ${dst:04X}, {req} bytes (long. en ${lenaddr:04X}, dir. en ${ixaddr:04X})'
            return info
        hits = []
        for ci, (name, dest, data) in enumerate(codes):
            for m in PAT48.finditer(data): hits.append((ci, m))
        if not hits:
            # DAAD Ready A 48K: todo lo carga el BASIC y el interprete no toca la cinta -> no hace falta parche
            ldb = re.compile(rb'[\xcd\xc3]\x56\x05|\xcd\x08\x07', re.S)
            if not any(ldb.search(data) for name, dest, data in codes):
                info['table'] = 'el interprete no carga nada de cinta: no hace falta parche'
                return info
        if len(hits) != 1:
            raise SystemExit('no reconozco el interprete (ni rutina de bancos 128K ni rutina de carga 48K)')
        ci, m = hits[0]
        base = codes[ci][1]
        info["patches"].append((ci, m.start(1), b'\x00\x00\x00',
            f'NOP NOP NOP en ${base + m.start(1):04X} (sustituye CALL $0708, la carga de la ROM)'))
    return info

# ------------------------------------------------------------------- build
def params_for(a):
    lo = round((2.5 * a - 120) / ITER)
    hi = round((3.6 * a - 60) / ITER)
    thr = round((2.8 * a - 90) / ITER)
    return lo, hi, thr

def chunks(data, mx=MAXCHUNK):
    k = max(1, math.ceil(len(data) / mx))
    base, extra = divmod(len(data), k)
    out = []; o = 0
    for i in range(k):
        n = base + (1 if i < extra else 0)
        out.append(data[o:o+n]); o += n
    return out

def find_pasmo(here):
    """Busca pasmo en el PATH y, si no esta, junto a este script (util en Windows: pasmo.exe)."""
    p = shutil.which('pasmo')
    if p: return p
    for n in ('pasmo.exe', 'pasmo'):
        c = os.path.join(here, n)
        if os.path.isfile(c): return c
    raise SystemExit('no encuentro pasmo. Linux: apt install pasmo. Windows: descarga pasmo.exe '
                     '(https://pasmo.speccy.org) y dejalo en la misma carpeta que turbo_tap.py')

def assemble(here, work, mode, loader_addr, table, params):
    lo, hi, thr = params
    open(os.path.join(work, 'params.inc'), 'w').write(
        f"LO equ {lo}\nHI equ {hi}\nNP equ {NPILOT}\nTHR equ {thr}\nNBLK equ {len(table)}\n"
        f"MODE128 equ {1 if mode == 128 else 0}\nLOADER_ADDR equ {loader_addr}\nBORDER_RAINBOW equ {1 if BORDER == 'rainbow' else 0}\n")
    with open(os.path.join(work, 'table.inc'), 'w') as f:
        f.write("tbl:\n")
        for b, d, l in table:
            f.write(f"        defb {b}\n        defw {d}\n        defw {l}\n")
    shutil.copy(os.path.join(here, 'loader.asm'), os.path.join(work, 'loader.asm'))
    pasmo = find_pasmo(here)
    subprocess.check_call([pasmo, '--bin', 'loader.asm', 'loader.bin'], cwd=work)
    return open(os.path.join(work, 'loader.bin'), 'rb').read()

def pick_loader_addr(mode, main_segs, size):
    """Primera zona libre >= $8000 (sin contencion de la ULA) donde cabe el cargador."""
    limit = 0xC000 if mode == 128 else 0x10000
    occ = sorted((d, d + len(x)) for d, x in main_segs)
    cur = 0x8000
    for s, e in occ:
        if e <= cur: continue
        if s - cur >= size + 16: break
        cur = max(cur, e)
    cur = (cur + 15) & ~15
    if cur + size + 16 > (limit if mode == 128 else 0x10000):
        # ultima oportunidad: hueco tras el ultimo bloque
        raise SystemExit('no encuentro hueco libre para el cargador (>= $8000)')
    # comprobar que no pisa nada
    for s, e in occ:
        if cur < e and s < cur + size: raise SystemExit('el hueco elegido pisa un bloque')
    return cur

def build(tap_path, outdir, name, baud=3000, wav=False, info_only=False,
          scale=1.0, jitter=0.0, seed=1, corrupt=None, replay_from=None):
    import random
    rnd = random.Random(seed)
    J = lambda v: max(1, round(v * (1 + rnd.uniform(-jitter, jitter)))) if jitter else v
    here = os.path.dirname(os.path.abspath(__file__))
    tap = Tap(tap_path)
    info = analyze(tap)
    mode = info['mode']
    # ---- aplicar parches y construir segmentos -------------------------------
    codes = [[n, d, bytearray(x)] for n, d, x in tap.codes]
    for ci, off, new, desc in info['patches']:
        codes[ci][2][off:off+len(new)] = new
    segs = [(0, d, bytes(x)) for n, d, x in codes] + [(b, d, x) for b, d, x in info['banks']]
    main_segs = [(d, x) for b, d, x in segs if b == 0]
    # tabla provisional para medir el tamano del cargador
    tmp = tempfile.mkdtemp(prefix='turbo_')
    a = max(200, round(3.5e6 / (3 * baud)))
    params = params_for(a)
    table = []; blocks = []
    def make_table():
        table.clear(); blocks.clear()
        for bank, dest, data in segs:
            o = 0
            for c in chunks(data):
                idx = len(table)
                table.append((bank, dest + o, len(c)))
                body = bytes([idx]) + c
                blocks.append(body + bytes([xor(body)]))
                o += len(c)
    make_table()
    probe = assemble(here, tmp, mode, 0x8000, table, params)
    laddr = pick_loader_addr(mode, main_segs, len(probe))
    loader = assemble(here, tmp, mode, laddr, table, params)
    shutil.rmtree(tmp, ignore_errors=True)
    # ---- BASIC -------------------------------------------------------------
    bname, bauto, bplen, bdata = tap.basic
    prog, nloads = rewrite_basic(bdata[:bplen], laddr)
    vars_ = bdata[bplen:]
    bdata_new = prog + vars_
    # ---- informe -----------------------------------------------------------
    rep = [f"modo: {mode}K", f"cargador turbo: ${laddr:04X}-${laddr+len(loader)-1:04X} ({len(loader)} bytes)",
           f"velocidad: ~{baud} baudios (a={a} T)"]
    for ci, off, new, desc in info['patches']: rep.append('parche: ' + desc)
    if 'table' in info: rep.append(info['table'])
    for n, d, x in tap.codes: rep.append(f"bloque '{n}': ${d:04X}, {len(x)} bytes")
    for b, d, x in info['banks']: rep.append(f"banco {b}: ${d:04X}, {len(x)} bytes")
    rep.append(f"sentencias LOAD sustituidas en el BASIC: {nloads}; bloques turbo: {len(blocks)}")
    report = '\n'.join(rep)
    if info_only: return dict(report=report)
    os.makedirs(outdir, exist_ok=True)
    # ---- TZX ----------------------------------------------------------------
    def std_block(flag, data, pause):
        body = bytes([flag]) + data
        body += bytes([xor(body)])
        return bytes([0x10]) + struct.pack('<HH', pause, len(body)) + body
    def header(typ, nm, ln, p1, p2):
        return bytes([typ]) + nm.ljust(10)[:10].encode('latin1') + struct.pack('<HHH', ln, p1, p2)
    tzx = bytearray(b'ZXTape!\x1a\x01\x14')
    pulses = []
    def add_std(flag, data, pause):
        blk = std_block(flag, data, pause); tzx.extend(blk)
        body = blk[5:]
        pulses.extend([2168] * (8063 if body[0] < 128 else 3223) + [667, 735])
        for byte in body:
            for i in range(7, -1, -1):
                pulses.extend([1710, 1710] if (byte >> i) & 1 else [855, 855])
        pulses.append(('pause', pause))
    add_std(0x00, header(0, bname, len(bdata_new), bauto, len(prog)), 1000)
    add_std(0xFF, bdata_new, 1000)
    add_std(0x00, header(3, 'turbo', len(loader), laddr, 32768), 1000)
    add_std(0xFF, loader, 1500)
    pilot = round(3 * a * scale); sync = round(a * scale)
    b0 = round(a * scale); b1 = round(2 * a * scale)
    play = list(blocks)
    if corrupt is not None:
        bad = bytearray(play[corrupt]); bad[len(bad)//2] ^= 0x10; play[corrupt] = bytes(bad)
        play += blocks[(replay_from if replay_from is not None else corrupt):]
    for body in play:
        tzx.extend(bytes([0x11]) + struct.pack('<HHHHHHBH', pilot, sync, sync, b0, b1, PILOT_PULSES, 8, PAUSE_MS)
                   + struct.pack('<I', len(body))[:3] + body)
        pulses.extend([J(pilot) for _ in range(PILOT_PULSES)] + [J(sync), J(sync)])
        for byte in body:
            for i in range(7, -1, -1):
                v = b1 if (byte >> i) & 1 else b0
                pulses.extend([J(v), J(v)])
        pulses.append(('pause', PAUSE_MS))
    tzx_path = os.path.join(outdir, name + '.tzx')
    open(tzx_path, 'wb').write(bytes(tzx))
    total_T = sum(p[1] * 3500 if isinstance(p, tuple) else p for p in pulses)
    if wav: write_wav(os.path.join(outdir, name + '.wav'), pulses)
    return dict(report=report, tzx=tzx_path, seconds=total_T / 3.5e6, loader=loader, laddr=laddr, mode=mode,
                blocks=blocks, table=table, pulses=pulses)

def write_wav(path, pulses, rate=44100, amp=26000):
    out = array.array('h'); t = 0.0; level = -1; pos = 0; cps = 3.5e6 / rate
    for p in pulses:
        if isinstance(p, tuple):
            ms = p[1]
            level = -level                 # flanco que cierra el ultimo pulso de datos
            t += 3500
            end = int(round(t / cps)); n = end - pos
            if n > 0: out.extend([amp * level] * n); pos = end
            level = -1
            t += max(0, ms - 1) * 3500
        else:
            t += p; level = -level
        end = int(round(t / cps)); n = end - pos
        if n > 0: out.extend([amp * level] * n); pos = end
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(out.tobytes())

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='TAP DAAD Ready -> cinta turbo (TZX/WAV)')
    ap.add_argument('tap'); ap.add_argument('outdir'); ap.add_argument('name')
    ap.add_argument('--baud', type=int, default=3000)
    ap.add_argument('--border', choices=['rainbow', 'classic'], default='rainbow')
    ap.add_argument('--wav', action='store_true'); ap.add_argument('--info', action='store_true')
    ap.add_argument('--scale', type=float, default=1.0); ap.add_argument('--jitter', type=float, default=0.0)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--corrupt', type=int); ap.add_argument('--replay', type=int)
    o = ap.parse_args()
    BORDER = o.border
    r = build(o.tap, o.outdir, o.name, o.baud, o.wav, o.info, o.scale, o.jitter, o.seed, o.corrupt, o.replay)
    print(r['report'])
    if not o.info:
        print(f"\n-> {r['tzx']}  duracion total: {r['seconds']/60:.1f} min")
