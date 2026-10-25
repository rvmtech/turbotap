# turbo_tap — Carga turbo para aventuras DAAD Ready de ZX Spectrum / Turbo loading for ZX Spectrum DAAD Ready adventures

[Español](#español) · [English](#english)

---

## Español

Convierte un `.tap` de una aventura conversacional hecha con **DAAD
Ready** (ZX Spectrum **48K** o **128K**) en una cinta de **carga turbo**
(`.tzx` y, opcionalmente, `.wav`), sin tocar el intérprete salvo un
parche mínimo en memoria.

Está pensado para quien quiere cargar su aventura en un Spectrum real
(cassette, audio del PC/móvil, etc.) sin esperar los ~12 minutos de la
carga estándar.

### Resultados

Tiempos de carga totales (BASIC incluido) con la velocidad por defecto
(~3000 baudios; la ROM carga a ~1364):

| Juego | Original | Turbo (~3000 baudios) |
|---|---|---|
| Aventura 128K de ~120 KB | 12,5 min | 5,7 min |
| Aventura 48K de ~40 KB | 4,8 min | 2,2 min |

### Demo

Cintas de ejemplo ya generadas (juego *Proyecto Starwash*) para probar la
carga turbo en tu emulador o Spectrum, a distintas velocidades. Cuanto
menor es la velocidad, más fiable; la velocidad por defecto es 3000
baudios.

| Fichero | Versión | Velocidad |
|---|---|---|
| [`demo/starwash-128k-2250.tzx`](demo/starwash-128k-2250.tzx) | 128K | ~2250 baudios (muy segura) |
| [`demo/starwash-128k-3000.tzx`](demo/starwash-128k-3000.tzx) | 128K | ~3000 baudios (por defecto) |
| [`demo/starwash-128k-3500.tzx`](demo/starwash-128k-3500.tzx) | 128K | ~3500 baudios |
| [`demo/starwash-128k-4150.tzx`](demo/starwash-128k-4150.tzx) | 128K | ~4150 baudios (más arriesgada) |
| [`demo/starwash-48k-2250.tzx`](demo/starwash-48k-2250.tzx) | 48K | ~2250 baudios (muy segura) |

### Requisitos

- Python 3.8 o superior
- [`pasmo`](https://pasmo.speccy.org/) (Debian/Ubuntu: `sudo apt install pasmo`)
- `loader.asm` en la misma carpeta que `turbo_tap.py`

#### Instalación en Windows

Windows **no** trae Python instalado de serie, y `pasmo` tampoco. Hay que
instalar ambos (no se necesitan permisos de programador ni nada más):

1. **Python**
   - Descárgalo de <https://www.python.org/downloads/windows/> y, en el instalador, marca **"Add python.exe to PATH"** antes de pulsar *Install Now*.
   - Alternativa desde una terminal (PowerShell): `winget install Python.Python.3.12`. También está en la Microsoft Store.
   - Comprueba que funciona abriendo una terminal nueva y escribiendo `python --version` (o `py --version`).
2. **pasmo**
   - Descarga el ejecutable para Windows de la [web de pasmo](https://pasmo.speccy.org), por ejemplo [`pasmo-0.5.3.zip`](https://pasmo.speccy.org/bin/pasmo-0.5.3.zip) (es la versión con la que se ha probado este programa en Linux).
   - Descomprime el ZIP y copia `pasmo.exe` **en la misma carpeta que `turbo_tap.py` y `loader.asm`**. El script lo busca ahí automáticamente (o en el `PATH`, si prefieres instalarlo en otro sitio).
3. **Ejecuta el script** desde esa carpeta (en el Explorador: escribe `cmd` en la barra de direcciones y pulsa Intro), usando `python` en lugar de `python3`:

   ```
   python turbo_tap.py juego.tap salida mijuego-turbo --baud 3000
   ```

   Si `python` no se reconoce, prueba con `py turbo_tap.py ...`.

Otra opción es usar
[WSL](https://learn.microsoft.com/windows/wsl/install) y seguir las
instrucciones de Linux (`sudo apt install pasmo python3`).

> En macOS: `brew install pasmo` (si usas Homebrew) y `python3` ya suele estar disponible.

### Uso

```
python3 turbo_tap.py juego.tap carpeta_salida nombre [--baud 3000] [--border rainbow|classic] [--wav] [--info]
```

| Opción | Descripción |
|---|---|
| `--baud N` | Velocidad aproximada. Por defecto 3000. Valores razonables: 2250 (muy seguro), 3000, 3500, 4150. |
| `--border` | `rainbow` (por defecto): franjas multicolor en el borde, como muchos cargadores turbo. `classic`: dos colores. |
| `--wav` | Genera también `nombre.wav` (44,1 kHz, mono, 16 bits; 12–40 MB según el juego). |
| `--info` | Solo analiza el TAP y muestra lo que ha detectado (modo, parche, bancos, direcciones). No escribe nada. |

Genera `carpeta_salida/nombre.tzx`. Ejemplo:

```
python3 turbo_tap.py starwash-128k.tap salida starwash-turbo --baud 3000 --wav
```

> **Emuladores:** hay que cargar el TZX en tiempo real. La "carga rápida" por ROM solo reconoce bloques de velocidad estándar y no funciona con la parte turbo (el cargador BASIC inicial sí va a velocidad normal).

### Cómo funciona

1. **Lee el TAP**: programa BASIC, bloques con cabecera (pantalla, intérprete, base de datos, etc.) y, en 128K, los bloques de bancos sin cabecera.
2. **Parchea el intérprete** en memoria (el TAP original no se modifica) para anular la carga desde cinta con la ROM, porque el cargador turbo ya habrá dejado todo en su sitio:
   - **128K**: localiza la rutina de carga de bancos (con su tabla de bancos y la llamada a `LD-BYTES`) y pone un `RET` (1 byte) al inicio de la parte de carga. Destinos y longitudes de cada banco se leen del propio intérprete.
   - **48K**: en **DAAD Ready A** el BASIC carga todo y el intérprete no usa la cinta, así que no hace falta parche (el script lo comprueba). En **DAAD Ready B** el intérprete carga con la ROM un bloque extra sin cabecera (longitud y dirección en variables del juego): el script lee esos valores de los datos del juego, incluye el bloque en la cinta turbo y neutraliza la llamada a la ROM con 3 `NOP`.
3. **Reescribe el cargador BASIC**: las sentencias `LOAD ""` se sustituyen por `LOAD ""CODE : RANDOMIZE USR <cargador>`. El resto del BASIC se conserva.
4. **Genera el cargador turbo** (`loader.asm`, ~340–410 bytes) y lo coloca en un hueco de memoria libre a partir de `$8000` (zona sin contención de la ULA, para que los tiempos sean estables). Al terminar, el cargador se borra a sí mismo, restaura paginación y borde, y vuelve al BASIC con el estado que espera la ROM.
5. **Genera la cinta**: BASIC y cargador a velocidad estándar; el resto en bloques turbo (≤ ~9 KB) con piloto, sincronismo, número de bloque y comprobación XOR.

#### Formato de los bloques turbo

Cada bit son 2 pulsos iguales (corto = 0, largo = 1), MSB primero. Cada
bloque lleva: tono piloto + 2 pulsos de sincronismo +
`[id][datos…][xor]`.

#### Recuperación de errores

Si un bloque falla (comprobación XOR incorrecta, tiempo agotado o bloque
que no es el esperado), el cargador **no se bloquea ni reinicia**: vuelve
a esperar piloto y acepta solo el bloque que le falta. Basta con
rebobinar un poco la cinta; los bloques anteriores ya cargados se saltan.

#### Colores del borde

- Piloto: franjas rojo/magenta alternas.
- Datos (`--border rainbow`): el borde toma los 3 bits bajos de cada byte recibido (franjas multicolor).
- Con `--border classic`: cian en piloto y azul/amarillo en datos.

### Intérpretes soportados y límites

Probado con intérpretes DAAD Ready 128K (varias versiones, con 2 y 6
bancos) y 48K (DAAD Ready A y B). No soporta juegos con cargadores
personalizados. Si el intérprete no se reconoce, el script se detiene con
un mensaje claro en vez de generar algo roto. En ese caso, abre un issue
adjuntando el `.tap`.

- Solo tiene en cuenta los patrones de carga observados en esas versiones.
- Las sentencias `LOAD "" CODE <dirección>` con parámetros no están soportadas (solo `LOAD ""`, `LOAD ""CODE` y `LOAD ""SCREEN$`).
- Con un Spectrum real y cassette no se ha probado todavía: se ha verificado en emulador (JSSpeccy3 con ROMs 48K/128K, carga por pulsos con contención de memoria).

### Verificación

La memoria de los 8 bancos (128K) o de la RAM completa (48K), tomada
justo después de la carga, es **idéntica byte a byte** a la que deja la
cinta original, salvo variables del sistema, el programa BASIC, la pila y
los bytes parcheados. Además:

- Tolerancia a variación de velocidad de la cinta: aprox. ±10 % a 3000 baudios.
- Tolerancia a ruido: ±10–15 % aleatorio en cada pulso.
- Carga correcta desde WAV (44,1 kHz) y tras forzar un error en un bloque y rebobinar.

### Estructura

```
turbo_tap.py   # script principal
loader.asm     # cargador turbo (Z80, pasmo); turbo_tap.py genera params.inc y table.inc al ensamblarlo
```

`params.inc` (tiempos, modo, dirección) y `table.inc` (lista de bloques) los crea el script en una carpeta temporal; no hay que mantenerlos a mano.

---

## English

Converts a **DAAD Ready** text adventure `.tap` (ZX Spectrum **48K** or
**128K**) into a **turbo-loading tape** (`.tzx` and optionally `.wav`),
without modifying the interpreter apart from a tiny in-memory patch.

It is meant for people who want to load their adventure on a real
Spectrum (cassette, PC/phone audio, etc.) without waiting ~12 minutes for
the standard loader.

### Results

Total load times (BASIC included) at the default speed (~3000 baud; the ROM loads at ~1364):

| Game | Original | Turbo (~3000 baud) |
|---|---|---|
| ~120 KB 128K adventure | 12.5 min | 5.7 min |
| ~40 KB 48K adventure | 4.8 min | 2.2 min |

### Demo

Ready-made example tapes (the *Proyecto Starwash* game) so you can try turbo loading
on your emulator or Spectrum at different speeds. The lower the speed,
the more reliable; the default is 3000 baud.

| File | Version | Speed |
|---|---|---|
| [`demo/starwash-128k-2250.tzx`](demo/starwash-128k-2250.tzx) | 128K | ~2250 baud (very safe) |
| [`demo/starwash-128k-3000.tzx`](demo/starwash-128k-3000.tzx) | 128K | ~3000 baud (default) |
| [`demo/starwash-128k-3500.tzx`](demo/starwash-128k-3500.tzx) | 128K | ~3500 baud |
| [`demo/starwash-128k-4150.tzx`](demo/starwash-128k-4150.tzx) | 128K | ~4150 baud (riskier) |
| [`demo/starwash-48k-2250.tzx`](demo/starwash-48k-2250.tzx) | 48K | ~2250 baud (very safe) |

### Requirements

- Python 3.8 or later
- [`pasmo`](https://pasmo.speccy.org/) (Debian/Ubuntu: `sudo apt install pasmo`)
- `loader.asm` in the same folder as `turbo_tap.py`

#### Installing on Windows

Windows does **not** ship with Python, and it doesn't ship with `pasmo`
either. Install both (no developer tools needed):

1. **Python**
   - Download it from <https://www.python.org/downloads/windows/> and, in the installer, tick **"Add python.exe to PATH"** before clicking *Install Now*.
   - Alternative from a terminal (PowerShell): `winget install Python.Python.3.12`. It's also available from the Microsoft Store.
   - Check it works by opening a new terminal and typing `python --version` (or `py --version`).
2. **pasmo**
   - Download the Windows executable from the [pasmo website](https://pasmo.speccy.org), e.g. [`pasmo-0.5.3.zip`](https://pasmo.speccy.org/bin/pasmo-0.5.3.zip) (the version this tool was tested with on Linux).
   - Unzip it and copy `pasmo.exe` **into the same folder as `turbo_tap.py` and `loader.asm`**. The script looks for it there automatically (or on your `PATH`, if you prefer to install it elsewhere).
3. **Run the script** from that folder (in Explorer: type `cmd` in the address bar and press Enter), using `python` instead of `python3`:

   ```
   python turbo_tap.py game.tap out mygame-turbo --baud 3000
   ```

   If `python` isn't recognised, try `py turbo_tap.py ...`.

Another option is [WSL](https://learn.microsoft.com/windows/wsl/install),
following the Linux instructions (`sudo apt install pasmo python3`).

> On macOS: `brew install pasmo` (if you use Homebrew); `python3` is usually already available.

### Usage

```
python3 turbo_tap.py game.tap output_dir name [--baud 3000] [--border rainbow|classic] [--wav] [--info]
```

| Option | Description |
|---|---|
| `--baud N` | Approximate speed. Default 3000. Sensible values: 2250 (very safe), 3000, 3500, 4150. |
| `--border` | `rainbow` (default): multicoloured border stripes, like many turbo loaders. `classic`: two colours. |
| `--wav` | Also writes `name.wav` (44.1 kHz, mono, 16-bit; 12–40 MB depending on the game). |
| `--info` | Only analyses the TAP and prints what was detected (mode, patch, banks, addresses). Writes nothing. |

Writes `output_dir/name.tzx`. Example:

```
python3 turbo_tap.py starwash-128k.tap out starwash-turbo --baud 3000 --wav
```

> **Emulators:** load the TZX in real time. ROM "fast loading" traps only recognise standard-speed blocks and don't work for the turbo part (the initial BASIC loader does run at normal speed).

### How it works

1. **Reads the TAP**: BASIC program, headered blocks (screen, interpreter, database, …) and, on 128K, the headerless bank blocks.
2. **Patches the interpreter** in memory (the original TAP is untouched) to disable its own ROM tape loading, since the turbo loader will already have put everything in place:
   - **128K**: finds the bank-loading routine (bank table + `LD-BYTES` call) and writes a `RET` (1 byte) at the start of its loading part. Each bank's destination and length are read from the interpreter itself.
   - **48K**: in **DAAD Ready A** the BASIC loads everything and the interpreter never touches the tape, so no patch is needed (the script checks this). In **DAAD Ready B** the interpreter loads an extra headerless block through the ROM (length and address held in game variables): the script reads those values from the game data, includes the block in the turbo tape and neutralises the ROM call with 3 `NOP`s.
3. **Rewrites the BASIC loader**: `LOAD ""` statements become `LOAD ""CODE : RANDOMIZE USR <loader>`. The rest of the BASIC is preserved.
4. **Generates the turbo loader** (`loader.asm`, ~340–410 bytes) and places it in a free memory gap at or above `$8000` (no ULA contention, for stable timing). When done it wipes itself, restores paging and border, and returns to BASIC in the state the ROM expects.
5. **Generates the tape**: BASIC and loader at standard speed; everything else in turbo blocks (≤ ~9 KB each) with pilot, sync, block number and XOR checksum.

#### Turbo block format

Each bit is 2 equal pulses (short = 0, long = 1), MSB first. Each block
is: pilot tone + 2 sync pulses + `[id][data…][xor]`.

#### Error recovery

If a block fails (bad XOR, timeout, or not the expected block), the
loader **neither hangs nor restarts**: it waits for a pilot again and
accepts only the missing block. Just rewind the tape a bit; blocks
already loaded are skipped.

#### Border colours

- Pilot: alternating red/magenta stripes.
- Data (`--border rainbow`): border takes the low 3 bits of each received byte (multicolour stripes).
- With `--border classic`: cyan on pilot, blue/yellow on data.

### Supported interpreters and limits

Tested with DAAD Ready 128K interpreters (several versions, with 2 and 6
banks) and 48K (DAAD Ready A and B). Games with custom loaders are not
supported. If the interpreter isn't recognised the script stops with a
clear message rather than producing something broken. In that case please
open an issue attaching the `.tap`.

- Only the loading patterns seen in those versions are handled.
- `LOAD "" CODE <address>` statements with parameters are not supported (only `LOAD ""`, `LOAD ""CODE` and `LOAD ""SCREEN$`).
- Not yet tested on a real Spectrum with a cassette: it has been verified in an emulator (JSSpeccy3 with 48K/128K ROMs, pulse-level tape loading with memory contention).

### Verification

The memory of all 8 banks (128K) or the whole RAM (48K), captured right
after loading, is **byte-for-byte identical** to what the original tape
leaves, except for system variables, the BASIC program, the stack and the
patched bytes. Also:

- Tape speed tolerance: roughly ±10 % at 3000 baud.
- Noise tolerance: random ±10–15 % on every pulse.
- Loads correctly from a 44.1 kHz WAV and after forcing a block error and rewinding.

### Layout

```
turbo_tap.py   # main script
loader.asm     # turbo loader (Z80, pasmo); turbo_tap.py generates params.inc and table.inc when assembling it
```

`params.inc` (timings, mode, address) and `table.inc` (block list) are created by the script in a temporary folder; they are not maintained by hand.
