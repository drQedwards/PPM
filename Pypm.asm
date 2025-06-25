; pypm.asm - Minimal x86_64 assembly entry for PYPM
; Assumes linkage with C runtime and pypm.c

global _start

section .data
    msg     db  "PYPM v0.0.3-dev", 10, 0    ; Null-terminated string
    msglen  equ $ - msg

section .text
_start:
    ; Write version message to stdout
    mov rax, 1          ; syscall: write
    mov rdi, 1          ; file descriptor 1 (stdout)
    mov rsi, msg        ; pointer to message
    mov rdx, msglen     ; message length
    syscall

    ; Call pypm_init (assumed external C function)
    call pypm_init      ; Defined in pypm.c
    test eax, eax       ; Check return value
    jnz .error          ; Jump if error

    ; Exit successfully
    mov rax, 60         ; syscall: exit
    xor rdi, rdi        ; return code 0
    syscall

.error:
    ; Exit with error code
    mov rax, 60         ; syscall: exit
    mov rdi, 1          ; return code 1
    syscall

; External C function (to be linked)
extern pypm_init
