; Replacement for the camera FOV routine at 0x419400 (entry jmp -> 0x65B618).
; Data at the start of the cave, written by the patcher:
;   0x65B610  float  fov_scale  (1.0 = game default; scales tan(fov/2))
;   0x65B614  dword  hp_enable  (1 = Hor+ beyond 16:9, 0 = stock Vert-)
bits 32
%include "consts.inc"
%ifndef TEST
org 0x65b610
%define TAN    0x64e470
%define ATAN   0x64ecf0
%define RECOMP 0x41937b
fov_scale: dd 1.0
hp_enable: dd 1
%endif
%macro MULC 1
    push dword %1
    fmul dword [esp]
    add esp, 4
%endmacro
%macro TODEG 0
    fadd st0, st0
    MULC R2D
%endmacro
start:
    push ebp
    mov ebp, esp
    sub esp, 0x10
    mov ecx, [eax]
    and ecx, 0x40
    mov [ebp-8], ecx            ; aspect-aware camera flag
    fld1
    jz .haveR
    fstp st0
    fild dword [eax+0x10]
    fidiv dword [eax+0x14]
.haveR:
    fstp dword [ebp-4]          ; R = width/height (1 if flag clear)
    ; --- FOV scale: aspect-aware cameras only, never on the re-derive path ---
    cmp dword [ebp-8], 0
    je .noscale
    cmp dword [ebp+4], RECOMP
    je .noscale
    fld dword [fov_scale]
    fld1
    fcomip st0, st1
    fstp st0
    je .noscale                 ; scale == 1.0 (or NaN)
    fld dword [ebp+8]
    MULC HALF_D2R
    call TAN
    fmul dword [fov_scale]
    call ATAN
    TODEG
    fstp dword [ebp+8]          ; base fov replaced by the scaled one
.noscale:
    fld dword [ebp+8]
    MULC HALF_D2R
    call TAN
    fstp dword [ebp-0xc]        ; t = tan(fov/2)
    cmp dword [ebp-8], 0
    je .pathB
    fld dword [ebp-4]
    fld1
    fcomip st0, st1
    fstp st0
    jae .pathB                  ; R <= 1
    cmp dword [ebp+4], RECOMP   ; re-derive path: input already processed
    je .stock
    fld dword [ebp-4]
    push dword RREF
    fdiv dword [esp]
    add esp, 4                  ; s = R / (16/9)
    fld1
    fcomip st0, st1
    jae .notwide                ; R <= 16:9
    cmp dword [hp_enable], 0
    jne .wide
.notwide:
    fstp st0
.stock:
    fld dword [ebp+8]
    fstp dword [edi]
    jmp .vert
.wide:
    fmul dword [ebp-0xc]        ; t' = t * s
    fst dword [ebp-0xc]
    call ATAN
    TODEG
    fstp dword [edi]            ; horizontal fov widened
.vert:
    fld dword [ebp-0xc]
    fdiv dword [ebp-4]
    call ATAN
    TODEG
    fstp dword [esi]            ; vertical fov
    jmp .done
.pathB:
    fld dword [ebp-0xc]
    fmul dword [ebp-4]
    call ATAN
    TODEG
    fstp dword [edi]
    fld dword [ebp+8]
    fstp dword [esi]
.done:
    mov esp, ebp
    pop ebp
    ret 8
