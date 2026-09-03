"""Puts a short one-sentence docstring on each function the checker named."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

NEW = {
    "test_the_parse_check_names_a_broken_module": (
        "A parse check accepting an unclosed brace would report a pass on any"
        " broken module."
    ),
    "test_the_counts_are_filled_in_from_the_lists_they_count": (
        "A count left at its starting value would read as a full table of tokens."
    ),
    "test_a_shadow_refuses_when_no_token_carries_its_colour": (
        "The surface declares five shadow alphas and no shadow colour, so each"
        " shadow renders nothing."
    ),
    "test_naming_a_colour_afterwards_renders_the_shadows": (
        "The same payload with a colour named afterwards renders every shadow"
        " the refusal held back."
    ),
    "test_the_unit_table_and_the_surface_name_the_same_groups": (
        "Both group lists are counted before pairing, so a group added to one"
        " side is named."
    ),
    "test_the_value_check_names_a_changed_payload_value": (
        "A module carrying its own copy of a value would answer the same"
        " whatever the payload said."
    ),
    "test_every_rendered_value_arrives_as_text": (
        "A stylesheet reads text, so a value reaching it as a number changed"
        " shape in transit."
    ),
    "test_the_type_check_would_name_a_value_that_is_not_text": (
        "Forty three tokens are numbers in the raw table before this module"
        " renders them."
    ),
    "test_every_alpha_byte_colour_is_converted_and_named": (
        "Each of the five conversions names the colour text that arrived and"
        " the text that renders."
    ),
    "test_the_converted_alpha_is_the_byte_over_the_published_scale": (
        "The scale is read off the module and the share multiplied by its"
        " reciprocal."
    ),
    "test_a_colour_already_in_the_browser_form_is_left_alone": (
        "Converting a colour whose share is one or less again would darken the"
        " tint each reload."
    ),
    "test_no_declared_colour_carries_a_digit_count_the_engines_read_apart": (
        "Qt reads an eight-digit hex as alpha first and a browser as alpha last."
    ),
    "test_the_digit_count_check_names_a_split_hex_and_a_short_hex": (
        "Both hex forms must be named, or the empty answer above means nothing."
    ),
    "test_a_colour_the_engines_read_apart_is_named_and_left_as_it_arrived": (
        "Repairing an eight-digit colour would guess which engine the author"
        " meant, so the value stays."
    ),
    "test_the_three_equal_channel_colours_render_by_exact_text": (
        "A colour whose three channels are one byte hides a swap, so each value"
        " is compared exactly."
    ),
    "test_the_three_equal_channel_list_names_every_such_colour": (
        "A list that fell behind would leave a new same-channel colour missing"
        " from these names."
    ),
    "test_the_order_check_names_a_reversed_group": (
        "A check comparing sets rather than order would pass on a reversed"
        " group of names."
    ),
    "test_a_token_is_reached_by_name_and_not_by_position": (
        "Each row carries its own name, so pairing two lists by index cannot"
        " misread a value."
    ),
    "test_each_read_answers_a_fresh_list_rather_than_the_one_it_holds": (
        "A caller handed the module's own list could reorder every screen by"
        " sorting it."
    ),
    "test_a_value_several_names_carry_resolves_to_none_of_them": (
        "A corner radius is not a layout gap, so naming either carrier would"
        " skin a screen wrong."
    ),
    "test_a_value_exactly_one_name_of_the_same_kind_carries_resolves": (
        "A refusal for every value would resolve nothing at all while passing"
        " the check above."
    ),
    "test_a_value_carried_by_a_name_of_another_kind_is_refused": (
        "A column width is not a pane height, so the one carrier must mean the"
        " same kind."
    ),
    "test_a_second_name_never_wins_the_resolution": (
        "Resolving to an alias would hide which token a screen really paints"
        " its colour from."
    ),
    "test_the_agreement_check_names_a_second_name_that_drifted": (
        "A check answering true for everything would pass on an alias whose"
        " target no longer matches."
    ),
    "test_the_shared_value_list_names_every_value_two_names_carry": (
        "A list that fell behind the surface would leave a new collision among"
        " these carriers unrefused."
    ),
    "test_the_scan_reads_past_a_comment_holding_a_colour": (
        "A scan treating a comment as code would report a colour the module"
        " only names."
    ),
    "test_each_written_value_is_caught_in_the_module_file_itself": (
        "The original is read inside the swap, and the restore is proved by"
        " digest after each line."
    ),
    "test_the_written_file_is_still_a_module_the_page_can_run": (
        "A written line that broke the parse would leave the scan reporting on"
        " an unloadable module."
    ),
    "test_no_line_in_the_module_runs_past_the_column_limit": (
        "Neither the formatter nor the linter reads a long comment, so this"
        " counts the columns."
    ),
    "test_a_scalar_and_a_null_inside_a_list_are_named_not_rendered": (
        "A number or a null where a token name belongs must be named, never"
        " rendered."
    ),
    "test_every_damaged_token_value_is_named_and_renders_nothing": (
        "Six damaged token values, each of a different shape, must each be"
        " named and render nothing."
    ),
    "test_the_bridge_cannot_carry_a_number_that_is_not_a_number": (
        "A NaN reaches the page through the bridge as text no parser accepts."
    ),
    "test_a_very_long_token_name_is_carried_rather_than_cut": (
        "A name of two hundred characters must reach the fault record whole"
        " and uncut."
    ),
    "test_a_name_no_token_carries_is_named_rather_than_rendered_empty": (
        "A group naming a token the table does not hold must say so, not"
        " render an empty declaration."
    ),
    "test_the_inherited_name_check_still_reads_a_real_token": (
        "A read answering nothing for every name would serve no declaration at" " all."
    ),
    "test_the_rendered_cases_and_the_surface_name_the_same_tokens": (
        "Both lists are counted before pairing, so a case naming a dropped"
        " token is named here."
    ),
    "test_every_kind_of_declaration_computes_in_the_browser": (
        "Each declaration is set on a probe through its own custom property"
        " and read back computed."
    ),
    "test_the_raw_surface_value_computes_to_nothing_in_the_browser": (
        "The same tokens written as the surface holds them paint no size and"
        " no tint."
    ),
    "test_a_reference_resolves_to_its_own_token_and_not_to_the_page": (
        "A reference written without the two dashes falls back to the colour"
        " the page inherits."
    ),
    "test_the_marking_check_names_an_unmarked_element": (
        "A count reading the same for both would pass on a page full of"
        " unnamed elements."
    ),
    "test_every_declaration_lands_on_the_page_as_a_custom_property": (
        "Each value is taken back off the rendered document, never off the"
        " object that wrote it."
    ),
}


def wrap(text: str, indent: str) -> list:
    """One docstring as source lines, wrapped inside the column limit."""
    body = " ".join(text.split())
    opened = f'{indent}"""{body}"""'
    if len(opened) <= 88:
        return [opened]
    words = body.split(" ")
    lines = [f'{indent}"""']
    for word in words:
        if len(lines[-1]) + len(word) + 1 > 84:
            lines.append(indent)
        lines[-1] = (
            (lines[-1] + " " + word).rstrip() if lines[-1].strip() else (indent + word)
        )
    lines[0] = lines[0].replace(indent + '"""', indent + '"""', 1)
    lines[-1] = lines[-1] + '"""'
    return lines


def main() -> None:
    target = REPO / sys.argv[1]
    source = target.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    edits = []
    holders = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders) or node.name not in NEW:
            continue
        first = node.body[0]
        indent = " " * (first.col_offset)
        edits.append((first.lineno, first.end_lineno, wrap(NEW[node.name], indent)))
    for start, end, body in sorted(edits, reverse=True):
        lines[start - 1 : end] = body
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    print(f"rewrote {len(edits)} docstring(s) in {target.name}")


if __name__ == "__main__":
    main()
