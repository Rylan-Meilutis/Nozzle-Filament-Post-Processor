#!/usr/bin/python3
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from typing import Any, Union


def main(gcode_path: str, json_path: Union[str, None] = None, json_data: Union[list[str], None] = None) -> None:
    """
    Main function,
    :param gcode_path: path to the gcode file
    :param json_path: path to the json file
    :param json_data: json data dictionary
    """
    if json_data is None:
        if json_path is None:
            print("You must provide either a json file path or a json data dictionary")
            sys.exit(1)
        json_data = parse_json_file(json_path)

    gcode = parse_gcode(gcode_path)
    new_file = replace_names(gcode, json_data)

    replace_gcode_tail(gcode_path, new_file)


def parse_json_file(json_path: str) -> list[str | None]:
    """
    Parse the json file and return the names in order of the extruders
    :param json_path: path to the json file
    :return: a list of db ids in order
    """
    # add the current directory of the py file to the front of the json path if it is not an absolute path
    if not os.path.isabs(json_path):
        json_path = os.path.join(os.path.dirname(__file__), json_path)
    with open(json_path, 'r') as file:
        data = json.load(file)
        return parse_json_data(data)
        # get each db id and the corresponding extruder position and put then in order in a list


def parse_json_data(json_data: dict[str, Any]) -> list[str | None]:
    """
    Parse the json data and return the names in order of the extruders
    :param json_data: the json data dictionary
    :return: a list of db ids in order
    """
    # get each db id and the corresponding extruder position and put then in order in a list
    out_list = [None] * len(json_data)
    for key, value in json_data.items():
        out_list[int(key) - 1] = value['sm_name']
    return out_list


def parse_gcode(gcode_path: str) -> str:
    """
    Parse the gcode file and return the last 1000 lines
    :param gcode_path: path to the gcode file
    :return: the last 1000 lines of the gcode file
    """
    tail, _ = read_gcode_tail(gcode_path, 1000)
    return tail.decode('utf-8', errors='replace')


def read_gcode_tail(gcode_path: str, num_lines: int) -> tuple[bytes, int]:
    """
    Read the last num_lines lines from a G-code file without loading the full file.
    :param gcode_path: path to the G-code file
    :param num_lines: number of trailing lines to read
    :return: the tail bytes and the byte offset where the tail starts
    """
    chunk_size = 8192

    with open(gcode_path, 'rb') as file:
        file.seek(0, os.SEEK_END)
        pos = file.tell()
        chunks = []
        newline_count = 0

        while pos > 0 and newline_count <= num_lines:
            read_size = min(chunk_size, pos)
            pos -= read_size
            file.seek(pos)
            chunk = file.read(read_size)
            chunks.append(chunk)
            newline_count += chunk.count(b'\n')

    tail = b''.join(reversed(chunks))
    lines = tail.splitlines(keepends=True)
    tail_lines = lines[-num_lines:]
    tail_bytes = b''.join(tail_lines)
    tail_start = pos + len(tail) - len(tail_bytes)
    return tail_bytes, tail_start


def replace_gcode_tail(gcode_path: str, new_tail: str) -> None:
    """
    Replace the last 1000 lines of a G-code file without loading the full file.
    :param gcode_path: path to the G-code file
    :param new_tail: replacement text for the trailing slicer settings
    """
    _, tail_start = read_gcode_tail(gcode_path, 1000)
    directory = os.path.dirname(gcode_path) or '.'

    with open(gcode_path, 'rb') as source:
        first_line = source.readline()
        has_header = first_line.startswith(b'; Edited with NVF Postprocessor')
        source.seek(0)

        with tempfile.NamedTemporaryFile('wb', delete=False, dir=directory) as temp_file:
            temp_path = temp_file.name
            if not has_header:
                temp_file.write(b'; Edited with NVF Postprocessor\n')

            remaining = tail_start
            while remaining > 0:
                chunk = source.read(min(8192, remaining))
                if not chunk:
                    break
                temp_file.write(chunk)
                remaining -= len(chunk)

            temp_file.write(new_tail.encode('utf-8'))

    os.replace(temp_path, gcode_path)


def replace_names(gcode: str, json_data: list[Any]) -> str:
    """
    Replace the db ids in the gcode with the correct values
    :param gcode: the last 1000 lines of the gcode
    :param json_data: the list of db ids in order
    :return: the last 1000 lines of the gcode with the db ids replaced
    """

    if json_data is None:
        return gcode
    # match the regex
    filament_notes_pattern = re.compile(r'; filament_notes = (.+)')
    filament_pattern = re.compile(r'; filament_type = (.+)')
    used_filament_pattern = re.compile(r'; filament used \[mm] = (.+)')

    filament_notes_match = filament_notes_pattern.search(gcode)
    filament_match = filament_pattern.search(gcode)
    filament_used_match = used_filament_pattern.search(gcode)

    filament_notes = None
    filament_types = None
    filament_used = None

    if filament_used_match:
        filament_used = filament_used_match.group(1).strip().split(',')

    if filament_match:
        filament_types = filament_match.group(1).strip().split(';')
    if filament_notes_match:
        filament_notes = filament_notes_match.group(1).strip().split(';')
    if filament_notes is None:
        return gcode

    num_filaments = 0
    if filament_types is not None:
        num_filaments = len(filament_types)
    new_filament_notes = filament_notes_match.group(0)
    new_filament_notes = new_filament_notes[1:].split(';')
    if filament_used is not None:
        if len(filament_used) != num_filaments:
            while len(filament_used) < num_filaments:
                filament_used.append('0')
            filament_used = [value.strip() for value in filament_used]

            gcode = re.sub(r"; filament used \[mm] = (.+)", f"; filament used [mm] = {', '.join(filament_used)}", gcode)

    # loop through the json data
    for i in range(len(filament_notes)):
        try:
            if json_data[i] is None:
                continue
        except IndexError:
            continue
        if re.search(r"\[\s*sm_name\s*=\s*([^]]*\S)?\s*]", filament_notes[i]):
            tmp_string = re.sub(r"\[\s*sm_name\s*=\s*([^]]*\S)?\s*]", f"[sm_name = {json_data[i]}]", filament_notes[i])
            # replace the match with the json data
            new_filament_notes[i] = new_filament_notes[i].replace(filament_notes[i], tmp_string)
    #convert the list to a string replacing the commas with a semicolon and not adding the brackets
    new_filament_notes = ";" + '; '.join(new_filament_notes)
    # replace the filament notes in the gcode
    gcode = gcode.replace(filament_notes_match.group(0), new_filament_notes)
    return gcode


if __name__ == "__main__":
    GCODE_PATH = sys.argv[2]
    JSON_PATH = sys.argv[1]
    main(GCODE_PATH, JSON_PATH)
