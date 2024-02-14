"""
SPDX-FileCopyrightText: 2024-present Luiz Eduardo Amaral <luizamaral306@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later

Script your way to rescue Christmas as part of the ElfScript Brigade team.

`esb` is a CLI tool to help us _elves_ to save christmas for the
[Advent Of Code](https://adventofcode.com/) yearly events
(Thank you [Eric 😉!](https://twitter.com/ericwastl)).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from enum import Enum, auto
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, Callable, Literal

from esb.protocol.metric_prefix import MetricPrefix

if TYPE_CHECKING:
    from pathlib import Path

AocSolutionFn = Callable[[str], Any]


###########################################################
# Python template runner
###########################################################
def _run_solution(part: Literal[1, 2], solve_pt1: AocSolutionFn, solve_pt2: AocSolutionFn):
    match part:
        case 1:
            return solve_pt1(sys.stdin.read())
        case 2:
            return solve_pt2(sys.stdin.read())
        case _:
            message = f"Part {part} does not exist"
            raise KeyError(message)


def run_solutions(solve_pt1: AocSolutionFn, solve_pt2: AocSolutionFn):
    parser = argparse.ArgumentParser("")
    parser.add_argument(
        "-p",
        "--part",
        choices=[1, 2],
        required=True,
        type=int,
        help="Run solution part 1 or part 2",
    )
    parser.add_argument(
        "-a",
        "--args",
        nargs="*",
        help="Run solution part 1 or part 2",
    )
    args = parser.parse_args()
    t0 = perf_counter_ns()
    ans = _run_solution(args.part, solve_pt1, solve_pt2)
    sys.stdout.write(f"{ans}\n")
    dt = perf_counter_ns() - t0
    sys.stdout.write(f"RT {dt} ns\n")


###########################################################
# Protocol runner
###########################################################
class FPStatus(Enum):
    Ok = auto()
    InputDoesNotExists = auto()
    ProtocolError = auto()


@dataclass
class FPResult:
    status: FPStatus
    answer: str | None = None
    running_time: int | None = None
    unit: MetricPrefix | None = None


FPPart = Literal[1, 2]


# @TODO: type this
async def _read_output(stream, threshold, print_stream):
    ret = ""
    lines = 0
    while line := await stream.readline():
        line = line.decode("utf-8")
        ret += line
        if lines == threshold:
            print_stream.write(ret)
        elif lines > threshold:
            print_stream.write(line)
        lines += 1
    return ret, lines


async def _exec_protocol_command(cmd: list[str], cwd: Path, day_input: Path) -> tuple[int, tuple[str, int]]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )

    if proc.stdin is None:
        message = "Could not open stdin"
        raise RuntimeError(message)

    proc.stdin.write(day_input.read_text().encode())
    proc.stdin.close()

    return await asyncio.gather(proc.wait(), _read_output(proc.stdout, threshold=2, print_stream=sys.stdout))


def _parse_running_time(running_time_line: str) -> tuple[int, MetricPrefix]:
    try:
        match running_time_line.split():
            case ["RT", running_time_str, unit_str]:
                running_time = int(running_time_str)
                unit = MetricPrefix.parse(unit_str, "second", "s")
                return running_time, unit
    except Exception as exc:  # noqa: BLE001
        message = f"Could not parse running time for '{running_time_line}'"
        raise ValueError(message) from exc
    message = f"Could not parse running time for '{running_time_line}'"
    raise ValueError(message)


def exec_protocol(command: list[str], part: FPPart, cwd: Path, day_input: Path) -> FPResult:
    if not day_input.is_file():
        return FPResult(status=FPStatus.InputDoesNotExists)

    cmd = [*command, "--part", f"{part}"]
    exitcode, (stdout, out_lines) = asyncio.run(_exec_protocol_command(cmd, cwd, day_input))

    success_exit = 0
    stdout_lines = [1, 2]
    if exitcode != success_exit or out_lines not in stdout_lines:
        return FPResult(status=FPStatus.ProtocolError)

    answer = None
    running_time = None
    unit = None
    match stdout.strip().split("\n"):
        case [ans, running_time_line]:
            answer = ans
            try:
                running_time, unit = _parse_running_time(running_time_line)
            except ValueError:
                return FPResult(status=FPStatus.ProtocolError)
        case [ans]:
            answer = ans
        case _:
            return FPResult(status=FPStatus.ProtocolError)

    return FPResult(status=FPStatus.Ok, answer=answer, running_time=running_time, unit=unit)
