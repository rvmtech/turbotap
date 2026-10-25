; ---------------------------------------------------------------------------
; Cargador turbo para STARWASH (DAAD Ready, 128K)
; Se carga a velocidad normal en $8000 (zona sin contencion) y carga el resto
; del juego a velocidad turbo, dejando la memoria exactamente como la dejaba
; el cargador BASIC original + la rutina de carga de bancos del interprete.
;
; Formato de cada bloque turbo en cinta:
;   piloto (tono) + sincronismo (2 pulsos cortos) + [id][datos...][xor]
;   cada bit = 2 pulsos iguales (corto = 0, largo = 1), MSB primero.
; Los parametros de tiempos (LO, HI, NP, THR...) vienen de params.inc
; ---------------------------------------------------------------------------
        include "params.inc"

        org     LOADER_ADDR

BANK_M  equ     0x5B5C          ; ultimo valor escrito en $7FFD (128K)
BORDCR  equ     0x5C48

entry:
        di
        xor     a
        ld      (cur),a

blk_next:
        ld      a,(cur)
        cp      NBLK
        jp      z,done
        ; HL = tbl + 5*a
        ld      l,a
        ld      h,0
        ld      d,h
        ld      e,l
        add     hl,hl
        add     hl,hl
        add     hl,de
        ld      de,tbl
        add     hl,de
        ld      a,(hl)          ; banco
        inc     hl
        ld      e,(hl)
        inc     hl
        ld      d,(hl)          ; destino
        inc     hl
        ld      c,(hl)
        inc     hl
        ld      b,(hl)          ; longitud
        ld      (dst),de
        ld      (len),bc
        if MODE128
        ; paginar banco (solo el puerto; BANK_M no se toca)
        ld      b,a
        ld      a,(BANK_M)
        and     0xF8
        or      b
        ld      bc,0x7FFD
        out     (c),a
        endif

retry:
        ld      a,2             ; borde rojo = buscando piloto
        out     (0xFE),a
        ; registros alternos para leer el byte "id": HL'=idbuf DE'=1 C'=0 B'=color
        exx
        ld      hl,idbuf
        ld      de,1
        ld      c,0
        ld      b,6
        exx
        call    waitpilot
        call    rdblk           ; lee el id
        jr      c,retry
        ld      a,(cur)
        ld      b,a
        ld      a,(idbuf)
        cp      b
        jr      nz,retry        ; no es el bloque esperado (cinta rebobinada, etc)
        ; datos
        exx
        ld      hl,(dst)
        ld      de,(len)
        exx
        call    rdblk
        jr      c,retry
        ; byte de comprobacion
        exx
        ld      hl,chkbuf
        ld      de,1
        exx
        call    rdblk
        jr      c,retry
        exx
        ld      a,c             ; C' = XOR de id+datos+chk, debe ser 0
        exx
        or      a
        jr      nz,retry
        ld      hl,cur
        inc     (hl)
        jp      blk_next

; ---------------------------------------------------------------------------
; Mide un pulso (flanco a flanco). Devuelve A=B=cuenta (1 unidad = 45 T).
; Z=1 si hay timeout (no hay flancos). Actualiza el nivel de referencia C.
; ---------------------------------------------------------------------------
measure:
        ld      b,0
m1:     inc     b
        ret     z
        in      a,(0xFE)
        xor     c
        and     0x40
        jr      z,m1
        ld      a,c
        xor     0x40
        ld      c,a
        ld      a,b
        or      a
        ret

; ---------------------------------------------------------------------------
; Espera piloto + sincronismo. Al volver, el siguiente pulso es el primero
; del primer bit de datos.
; ---------------------------------------------------------------------------
waitpilot:
        in      a,(0xFE)
        and     0x40
        ld      c,a
wp0:    ld      e,NP
wp1:    call    measure
        jr      z,wp0
        cp      LO
        jr      c,wp0
        cp      HI+1
        jr      nc,wp0
        if BORDER_RAINBOW
        ld      a,c             ; piloto: borde rojo/magenta alternando
        rlca
        rlca
        xor     2
        out     (0xFE),a
        endif
        dec     e
        jr      nz,wp1
        if BORDER_RAINBOW=0
        ld      a,5             ; borde cian = piloto detectado
        out     (0xFE),a
        endif
wp2:    call    measure
        jr      z,wp0
        cp      LO
        jr      nc,wp2c
        call    measure         ; segundo pulso de sincronismo (tambien corto)
        jr      z,wp0
        cp      LO
        jr      nc,wp0
        ret
wp2c:   cp      HI+1
        jr      c,wp2
        jr      wp0

; ---------------------------------------------------------------------------
; Lee DE' bytes a (HL'), acumulando XOR en C'. B' = color de borde (alterna).
; Salida: CF=0 ok, CF=1 timeout. Conjunto principal: B=timer C=nivel D=byte
; ---------------------------------------------------------------------------
rdblk:
nb:     ld      d,1
nbit:   ld      b,0
e1:     inc     b
        jr      z,tmo
        in      a,(0xFE)
        xor     c
        and     0x40
        jr      z,e1
        ld      a,c
        xor     0x40
        ld      c,a
e2:     inc     b
        jr      z,tmo
        in      a,(0xFE)
        xor     c
        and     0x40
        jr      z,e2
        ld      a,c
        xor     0x40
        ld      c,a
        ld      a,THR
        cp      b               ; CF=1 si B>THR (pulso largo = bit 1)
        rl      d
        jr      nc,nbit
        ld      a,d             ; byte completo
        exx
        ld      (hl),a
        if BORDER_RAINBOW
        ld      b,a             ; borde = 3 bits bajos del byte (franjas multicolor)
        xor     c
        ld      c,a
        ld      a,b
        and     7
        out     (0xFE),a
        else
        xor     c
        ld      c,a
        ld      a,b
        xor     7
        ld      b,a
        out     (0xFE),a
        endif
        inc     hl
        dec     de
        ld      a,d
        or      e
        exx
        jr      nz,nb
        ret                     ; CF=0 (OR lo deja a 0)
tmo:    scf
        ret

; ---------------------------------------------------------------------------
; Fin: restaurar paginacion y borde, limpiar la zona del cargador y volver a
; BASIC con HL'=$2758 (requerido por la ROM) e interrupciones activas.
; ---------------------------------------------------------------------------
done:
        if MODE128
        ld      a,(BANK_M)
        ld      bc,0x7FFD
        out     (c),a
        endif
        ld      a,(BORDCR)
        and     0x38
        rrca
        rrca
        rrca
        out     (0xFE),a
        ld      hl,0
        add     hl,sp
        ld      de,-48
        add     hl,de
        push    hl
        pop     ix
        ex      de,hl
        ld      hl,stub
        ld      bc,stub_end-stub
        ldir
        jp      (ix)
stub:
        ld      hl,LOADER_ADDR
        ld      de,LOADER_ADDR+1
        ld      bc,loader_end-LOADER_ADDR-1
        ld      (hl),0
        ldir
        ld      ix,0
        exx
        ld      hl,0x2758
        exx
        ei
        ret
stub_end:

cur:    defb    0
dst:    defw    0
len:    defw    0
idbuf:  defb    0
chkbuf: defb    0

        include "table.inc"
loader_end:
