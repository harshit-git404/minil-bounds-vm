"""
Disassembler for MiniL bytecode (.mbc) files.
"""
import struct
import sys
from compiler.opcodes import OPCODE_NAMES

def disassemble_file(filepath: str):
    with open(filepath, "rb") as f:
        magic, num_arrays, entry_pc, num_instructions, reserved = struct.unpack("<8sIIII", f.read(24))
        if magic != b"MINILB01":
            raise ValueError(f"Invalid bytecode magic: {magic}")

        print(f"; MiniL Bytecode Disassembly: {filepath}")
        print(f"; Magic: {magic.decode('ascii')}, Arrays: {num_arrays}, Entry PC: {entry_pc}, Instructions: {num_instructions}\n")

        print("; Array Table:")
        arrays = []
        for i in range(num_arrays):
            name_bytes, length, base_offset = struct.unpack("<32sqq", f.read(48))
            name = name_bytes.split(b"\x00", 1)[0].decode("utf-8")
            arrays.append((name, length, base_offset))
            print(f";   [{i}] '{name}' (length={length}, base_offset={base_offset})")
        print()

        print("; Instruction Stream:")
        for pc in range(num_instructions):
            opcode, a, b = struct.unpack("<qqq", f.read(24))
            op_name = OPCODE_NAMES.get(opcode, f"OP_{opcode}")

            # Formatting operand display for readability
            if op_name in ("PUSH", "LOAD", "STORE", "ENTER"):
                op_str = f"{a}"
            elif op_name in ("JMP", "JZ", "JNZ"):
                op_str = f"-> pc {a}"
            elif op_name == "CALL":
                op_str = f"-> pc {a}, nargs={b}"
            elif op_name in ("ALOAD", "ASTORE", "CHK", "ALOADC", "ASTOREC"):
                arr_name = arrays[a][0] if a < len(arrays) else f"arr#{a}"
                op_str = f"{arr_name} (id={a})"
            elif op_name in ("RET", "PRINT", "HALT", "NOP", "POP", "DUP",
                             "ADD", "SUB", "MUL", "DIV", "MOD", "NEG",
                             "EQ", "NE", "LT", "LE", "GT", "GE", "NOT"):
                op_str = ""
            else:
                op_str = f"a={a}, b={b}"

            print(f"{pc:04d}:  {op_name:<8} {op_str}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m compiler.disasm <bytecode_file.mbc>")
        sys.exit(1)
    disassemble_file(sys.argv[1])
