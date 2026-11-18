"""Experimental native ARM Thumb BLE gesture hook, emulator only.

Inputs at an UNRESERVED RAM candidate: count u8, active u8, eligibility u8,
pad u8, now_ticks u16 (incremented by an additional native OEM-classifier
hook every dispatched tick), last_ticks u16, first_ticks u16. The precise
hardware timer cadence is NOT verified, nor are the MCU speed/safety paths.
"""
from dataclasses import dataclass
from hashlib import sha256

from bwpatcher.mi5pro_research import APP_BASE, APP_SHA256, AnalysisError

HOOK = 0x8550
CAVE = 0x2BE62
CAVE_LENGTH = 130
RAM_CANDIDATE = 0x20B000
STOCK_ROUTINE = APP_BASE + 0x80AA
STOCK_INSN = bytes.fromhex("fff7abfd")
TX_HOOK = 0x3AB8
TX_STOCK_INSN = bytes.fromhex("05f022fc")
TX_STOCK_ROUTINE = APP_BASE + 0x9300
CLOCK_HOOK = 0x82FC
CLOCK_STOCK_INSN = bytes.fromhex("fff7b0ff")
CLOCK_STOCK_ROUTINE = APP_BASE + 0x8260
CLOCK_CODE_OFF = 0x2C42A    # 16-byte candidate in an unproven zero data region
CLOCK_LITERAL_OFF = 0x2C448  # 4-byte candidate in a separate unproven zero region


@dataclass(frozen=True)
class ExperimentalHook:
    app: bytes
    branch: bytes
    thumb: bytes
    tx_branch: bytes
    tx_thumb: bytes
    clock_branch: bytes
    clock_thumb: bytes
    safe_to_flash: bool = False
    hardware_tested: bool = False


def compile_hook(original: bytes) -> ExperimentalHook:
    """Assemble a real BLE instruction redirect inside an in-memory APP copy.

    NOT a loadable image. RAM allocation, clock source and code-cave safety
    have not been proven. No MCU speed override has been added.
    """
    from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
    if sha256(original).hexdigest() != APP_SHA256:
        raise AnalysisError("Exakter BLE-APP-Hash erforderlich.")
    if original[HOOK:HOOK + 4] != STOCK_INSN:
        raise AnalysisError("Originaler Modus-Hook nicht gefunden.")
    if original[CAVE:CAVE + CAVE_LENGTH] != bytes(CAVE_LENGTH):
        raise AnalysisError("Unverfuegbarer experimenteller Codebereich.")
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    addr = APP_BASE + CAVE
    source = f"""
        push {{r0-r4,lr}}
        ldr r4, ={RAM_CANDIDATE}
        ldrb r0, [r4, #1]
        cmp r0, #0
        bne deactivate
        bl {STOCK_ROUTINE}
        ldrb r2, [r4, #2]
        cmp r2, #1
        bne clear
        ldrh r1, [r4, #4]
        ldrb r0, [r4, #0]
        cmp r0, #0
        beq begin_sequence
        ldrh r2, [r4, #6]
        subs r3, r1, r2
        cmp r3, #60
        blo begin_sequence
        cmp r3, #160
        bhi begin_sequence
        ldrh r2, [r4, #8]
        subs r3, r1, r2
        cmp r3, #400
        bhi begin_sequence
        adds r0, #1
        cmp r0, #3
        bne store_counter
        ldr r2, ={0x20826D}
        ldrb r3, [r2]
        cmp r3, #3
        bne clear
        movs r0, #1
        strb r0, [r4, #1]
        b clear
    begin_sequence:
        movs r0, #1
        strh r1, [r4, #8]
    store_counter:
        strh r1, [r4, #6]
        strb r0, [r4, #0]
        b done
    deactivate:
        movs r0, #0
        strb r0, [r4, #1]
    clear:
        movs r0, #0
        strb r0, [r4, #0]
    done:
        pop {{r0-r4,pc}}
    """
    if original[TX_HOOK:TX_HOOK + 4] != TX_STOCK_INSN:
        raise AnalysisError("Originaler BLE-UART-Aufruf nicht gefunden.")
    if original[CLOCK_HOOK:CLOCK_HOOK+4] != CLOCK_STOCK_INSN:
        raise AnalysisError("Originaler BLE-Tastenaufruf nicht gefunden.")
    if original[CLOCK_CODE_OFF:CLOCK_CODE_OFF+16] != bytes(16):
        raise AnalysisError("Nur ein exakt leerer experimenteller Tick-Codebereich ist erlaubt.")
    if original[CLOCK_LITERAL_OFF:CLOCK_LITERAL_OFF+4] != bytes(4):
        raise AnalysisError("Nur ein exakt leerer experimenteller Tick-Literalbereich ist erlaubt.")
    try:
        opcodes, _ = ks.asm(source, addr=addr)
        branch, _ = ks.asm(f"bl {addr}", addr=APP_BASE + HOOK)
        tx_addr = addr + len(opcodes)
        tx_source = f"""
            ldr r3, ={RAM_CANDIDATE}
            ldrb r3, [r3, #1]
            cbz r3, send_stock
            ldrb r3, [r1, #3]
            cmp r3, #0x23
            bne send_stock
            adds r3, #1
            strb r3, [r1, #3]
            ldrb r3, [r1, #10]
            adds r3, #1
            strb r3, [r1, #10]
        send_stock:
            b.w {TX_STOCK_ROUTINE}
        """
        tx_code, _ = ks.asm(tx_source, addr=tx_addr)
        tx_branch, _ = ks.asm(f"bl {tx_addr}", addr=APP_BASE + TX_HOOK)
        # Increment the native clock before the original OEM classifier.
        # r0/r1 and the stack are restored; tail branch preserves the LR.
        clock_source = f"""
            push {{r0,r1}}
            ldr r0, [pc, #0x18]
            ldrh r1, [r0,#4]
            adds r1, #1
            strh r1, [r0,#4]
            pop {{r0,r1}}
            b.w {CLOCK_STOCK_ROUTINE}
        """
        clock_code, _ = ks.asm(clock_source, addr=APP_BASE+CLOCK_CODE_OFF)
        clock_branch, _ = ks.asm(
            f"bl {APP_BASE+CLOCK_CODE_OFF}", addr=APP_BASE+CLOCK_HOOK
        )
    except Exception as exc:
        raise AnalysisError(f"Thumb-Assemblerfehler: {exc}") from exc
    opcodes, branch = bytes(opcodes), bytes(branch)
    tx_code, tx_branch = bytes(tx_code), bytes(tx_branch)
    clock_code, clock_branch = bytes(clock_code), bytes(clock_branch)
    if len(opcodes) + len(tx_code) > CAVE_LENGTH or len(branch) != 4 or len(tx_branch) != 4:
        raise AnalysisError(
            "BLE Thumb-Codebereich oder Sprunglaenge passt nicht "
            f"({len(opcodes)}+{len(tx_code)}/{CAVE_LENGTH} Bytes)."
        )
    result = bytearray(original)
    if len(clock_code) != 16 or len(clock_branch) != 4:
        raise AnalysisError("Native Tick-Trampoline passt nicht in den 16-Byte-Kandidaten.")
    # Thumb LDR is 2 bytes into the stub; its literal PC is 4-byte aligned.
    if (((APP_BASE+CLOCK_CODE_OFF+2+4)&~3)+0x18 != APP_BASE+CLOCK_LITERAL_OFF):
        raise AnalysisError("ARM-Tick-PC-Literaladressierung stimmt nicht.")
    result[CAVE:CAVE + len(opcodes)] = opcodes
    result[CAVE + len(opcodes):CAVE + len(opcodes) + len(tx_code)] = tx_code
    result[HOOK:HOOK + 4] = branch
    result[TX_HOOK:TX_HOOK + 4] = tx_branch
    result[CLOCK_HOOK:CLOCK_HOOK+4] = clock_branch
    result[CLOCK_CODE_OFF:CLOCK_CODE_OFF+len(clock_code)] = clock_code
    result[CLOCK_LITERAL_OFF:CLOCK_LITERAL_OFF+4] = RAM_CANDIDATE.to_bytes(4,"little")
    return ExperimentalHook(bytes(result), branch, opcodes, tx_branch, tx_code,
                            clock_branch, clock_code)
