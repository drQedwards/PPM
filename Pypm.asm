;; Pypm.asm — x86_64 entry for PYPM linked against the updated PMLL C core
; (PMLL.c / PMLL.h).
;
; PMLL owns memory/state:
;   memory_silo_t, silo_set, peek, peek_semantic, sat_bridge_*, init_pml
;   (assignments start at -1 = undecided; flag is solve state, not a var value)
; Q-promise owns temporal/control-flow (not entered from this stub).
;
; Build sketch (Linux x86_64):
;   nasm -f elf64 Pypm.asm -o Pypm.o
;   cc -DPMLL_NO_MAIN -c PMLL.c -o PMLL.o
;   cc -c Pypm.c -o Pypm_api.o
;   cc -no-pie -o pypm-asm Pypm.o PMLL.o Pypm_api.o
;
; Alternate CLI entry remains Pypm.c::main (doctor / version / …).

global _start

section .data
    msg     db  "PMLL core · silo + peek/peek_semantic · init_pml=-1", 10, 0
    msglen  equ $ - msg - 1          ; exclude trailing NUL from write length

section .text
_start:
    ; write(1, msg, msglen)
    mov rax, 1
    mov rdi, 1
    mov rsi, msg
    mov rdx, msglen
    syscall

    ; Smoke-boot the updated PMLL core (defined in Pypm.c)
    call pmll_asm_boot
    test eax, eax
    jnz .error

    ; exit(0)
    mov rax, 60
    xor rdi, rdi
    syscall

.error:
    ; exit(1)
    mov rax, 60
    mov rdi, 1
    syscall

extern pmll_asm_boot
