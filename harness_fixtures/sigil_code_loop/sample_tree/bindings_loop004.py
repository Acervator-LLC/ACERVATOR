# LOOP004 open-method-readlines-in-for: one input per binding form of the closed table in
# failure_modes.txt; faulty_ is the open method twin of a form FURB129 reads on the built-in twin,
# corrected_ iterates the file object, and quiet_ is the open method twin of a form FURB129 reads on
# both twins or on neither
import io
from pathlib import Path
from typing import IO, Any, TextIO

NAME = "file.txt"
PATH = Path(NAME)
GLOBAL_HANDLE: Any = None
SHARED: Any = None


def faulty_with_as() -> None:
    with PATH.open() as handle:
        for line in handle.readlines():
            print(line)


def corrected_with_as() -> None:
    with PATH.open() as handle:
        for line in handle:
            print(line)


async def faulty_async_with_as() -> None:
    async with PATH.open() as handle:
        for line in handle.readlines():
            print(line)


async def corrected_async_with_as() -> None:
    async with PATH.open() as handle:
        for line in handle:
            print(line)


def faulty_assign_name() -> None:
    handle = PATH.open()
    for line in handle.readlines():
        print(line)


def corrected_assign_name() -> None:
    handle = PATH.open()
    for line in handle:
        print(line)


def faulty_assign_chained() -> None:
    handle = other = PATH.open()
    for line in handle.readlines():
        print(line, other)


def corrected_assign_chained() -> None:
    handle = other = PATH.open()
    for line in handle:
        print(line, other)


def faulty_assign_tuple() -> None:
    handle, count = PATH.open(), 0
    for line in handle.readlines():
        print(line, count)


def corrected_assign_tuple() -> None:
    handle, count = PATH.open(), 0
    for line in handle:
        print(line, count)


def faulty_assign_starred() -> None:
    handle, *rest = PATH.open(), 0
    for line in handle.readlines():
        print(line, rest)


def corrected_assign_starred() -> None:
    handle, *rest = PATH.open(), 0
    for line in handle:
        print(line, rest)


class QuietAssignAttribute:
    def __init__(self) -> None:
        self.handle = PATH.open()

    def lines(self) -> None:
        for line in self.handle.readlines():
            print(line)


def quiet_assign_subscript() -> None:
    handles = {}
    handles["a"] = PATH.open()
    for line in handles["a"].readlines():
        print(line)


def quiet_annotated_textio() -> None:
    handle: TextIO = PATH.open()
    for line in handle.readlines():
        print(line)


def quiet_annotated_io() -> None:
    handle: IO[str] = PATH.open()
    for line in handle.readlines():
        print(line)


def quiet_annotated_any() -> None:
    handle: Any = PATH.open()
    for line in handle.readlines():
        print(line)


def faulty_bare_annotation_then_assign() -> None:
    handle: Any
    handle = PATH.open()
    for line in handle.readlines():
        print(line)


def corrected_bare_annotation_then_assign() -> None:
    handle: Any
    handle = PATH.open()
    for line in handle:
        print(line)


def faulty_walrus_name() -> None:
    if (handle := PATH.open()) is not None:
        for line in handle.readlines():
            print(line)


def corrected_walrus_name() -> None:
    if (handle := PATH.open()) is not None:
        for line in handle:
            print(line)


def faulty_walrus_in_builder() -> list[str]:
    return [line for _ in [0] if (handle := PATH.open()) for line in handle.readlines()]


def corrected_walrus_in_builder() -> list[str]:
    return [line for _ in [0] if (handle := PATH.open()) for line in handle]


def quiet_walrus_direct() -> None:
    for line in (handle := PATH.open()).readlines():
        print(line, handle)


def quiet_for_target() -> None:
    for handle in (PATH.open(),):
        for line in handle.readlines():
            print(line)


def quiet_builder_target() -> list[str]:
    return [line for handle in (PATH.open(),) for line in handle.readlines()]


def quiet_parameter_default(handle=PATH.open()) -> None:
    for line in handle.readlines():
        print(line)


def quiet_parameter_default_annotated(handle: TextIO = PATH.open()) -> None:
    for line in handle.readlines():
        print(line)


def global_assign() -> None:
    global GLOBAL_HANDLE
    GLOBAL_HANDLE = PATH.open()


def quiet_global_read() -> None:
    for line in GLOBAL_HANDLE.readlines():
        print(line)


def faulty_closure_read() -> None:
    handle = PATH.open()

    def inner() -> None:
        for line in handle.readlines():
            print(line)

    inner()


def corrected_closure_read() -> None:
    handle = PATH.open()

    def inner() -> None:
        for line in handle:
            print(line)

    inner()


def quiet_nonlocal_assign() -> None:
    handle = None

    def inner() -> None:
        nonlocal handle
        handle = PATH.open()

    inner()
    for line in handle.readlines():
        print(line)


class FaultyClassBody:
    handle = PATH.open()
    for line in handle.readlines():
        print(line)


class CorrectedClassBody:
    handle = PATH.open()
    for line in handle:
        print(line)


class ClassAttribute:
    handle = PATH.open()


def quiet_class_attribute_read() -> None:
    for line in ClassAttribute.handle.readlines():
        print(line)


def quiet_match_capture() -> None:
    match PATH.open():
        case handle:
            for line in handle.readlines():
                print(line)


def quiet_match_as() -> None:
    match PATH.open():
        case object() as handle:
            for line in handle.readlines():
                print(line)


def faulty_direct_call() -> None:
    for line in PATH.open().readlines():
        print(line)


def corrected_direct_call() -> None:
    for line in PATH.open():
        print(line)


def faulty_direct_call_builder() -> list[str]:
    return [line for line in PATH.open().readlines()]


def corrected_direct_call_builder() -> list[str]:
    return [line for line in PATH.open()]


def faulty_rebound_after_loop() -> None:
    handle = PATH.open()
    for line in handle.readlines():
        print(line)
    handle = io.StringIO("")


def corrected_rebound_after_loop() -> None:
    handle = PATH.open()
    for line in handle:
        print(line)
    handle = io.StringIO("")


def quiet_rebound_before_loop() -> None:
    handle = PATH.open()
    handle = io.StringIO("")
    for line in handle.readlines():
        print(line)


def faulty_branch_open_last(flag: bool) -> None:
    if flag:
        handle = io.StringIO("")
    else:
        handle = PATH.open()
    for line in handle.readlines():
        print(line)


def corrected_branch_open_last(flag: bool) -> None:
    if flag:
        handle = io.StringIO("")
    else:
        handle = PATH.open()
    for line in handle:
        print(line)


def quiet_branch_open_first(flag: bool) -> None:
    if flag:
        handle = PATH.open()
    else:
        handle = io.StringIO("")
    for line in handle.readlines():
        print(line)


def faulty_bound_in_branch_only(flag: bool) -> None:
    if flag:
        handle = PATH.open()
        for line in handle.readlines():
            print(line)


def corrected_bound_in_branch_only(flag: bool) -> None:
    if flag:
        handle = PATH.open()
        for line in handle:
            print(line)


def faulty_bound_in_loop_body() -> None:
    handle = PATH.open()
    for line in handle.readlines():
        handle = io.StringIO(line)


def corrected_bound_in_loop_body() -> None:
    handle = PATH.open()
    for line in handle:
        handle = io.StringIO(line)


def quiet_closure_rebound_after() -> None:
    handle = PATH.open()

    def inner() -> None:
        for line in handle.readlines():
            print(line)

    inner()
    handle = io.StringIO("")


def faulty_unpack_list_target() -> None:
    [handle, count] = [PATH.open(), 0]
    for line in handle.readlines():
        print(line, count)


def corrected_unpack_list_target() -> None:
    [handle, count] = [PATH.open(), 0]
    for line in handle:
        print(line, count)


def faulty_unpack_nested() -> None:
    (handle, (first, second)) = (PATH.open(), (1, 2))
    for line in handle.readlines():
        print(line, first, second)


def corrected_unpack_nested() -> None:
    (handle, (first, second)) = (PATH.open(), (1, 2))
    for line in handle:
        print(line, first, second)


def faulty_unpack_second_place() -> None:
    count, handle = 0, PATH.open()
    for line in handle.readlines():
        print(line, count)


def corrected_unpack_second_place() -> None:
    count, handle = 0, PATH.open()
    for line in handle:
        print(line, count)


def faulty_unpack_star_before() -> None:
    *rest, handle = 0, PATH.open()
    for line in handle.readlines():
        print(line, rest)


def corrected_unpack_star_before() -> None:
    *rest, handle = 0, PATH.open()
    for line in handle:
        print(line, rest)


def faulty_unpack_star_value() -> None:
    handle, count = PATH.open(), *[0]
    for line in handle.readlines():
        print(line, count)


def corrected_unpack_star_value() -> None:
    handle, count = PATH.open(), *[0]
    for line in handle:
        print(line, count)


def faulty_unpack_set_value() -> None:
    handle, count = {PATH.open(), 0}
    for line in handle.readlines():
        print(line, count)


def corrected_unpack_set_value() -> None:
    handle, count = {PATH.open(), 0}
    for line in handle:
        print(line, count)


def quiet_unpack_from_call() -> None:
    handle, count = (lambda: (PATH.open(), 0))()
    for line in handle.readlines():
        print(line, count)


def faulty_with_second_item() -> None:
    with io.StringIO("") as first, PATH.open() as handle:
        for line in handle.readlines():
            print(line, first)


def corrected_with_second_item() -> None:
    with io.StringIO("") as first, PATH.open() as handle:
        for line in handle:
            print(line, first)


def quiet_with_tuple_target() -> None:
    with PATH.open() as (first, second):
        for line in first.readlines():
            print(line, second)


def faulty_walrus_in_while() -> None:
    while handle := PATH.open():
        for line in handle.readlines():
            print(line)
        break


def corrected_walrus_in_while() -> None:
    while handle := PATH.open():
        for line in handle:
            print(line)
        break


def quiet_walrus_then_rebound() -> None:
    if (handle := PATH.open()) is not None:
        handle = io.StringIO("")
        for line in handle.readlines():
            print(line)


def faulty_star_after_longer() -> None:
    handle, *rest = PATH.open(), 0, 1
    for line in handle.readlines():
        print(line, rest)


def corrected_star_after_longer() -> None:
    handle, *rest = PATH.open(), 0, 1
    for line in handle:
        print(line, rest)


def quiet_star_before_longer() -> None:
    *rest, handle = 0, 1, PATH.open()
    for line in handle.readlines():
        print(line, rest)


def quiet_star_middle_longer() -> None:
    first, *rest, handle = 0, 1, 2, PATH.open()
    for line in handle.readlines():
        print(line, first, rest)


def faulty_star_value_before() -> None:
    count, handle = *[0], PATH.open()
    for line in handle.readlines():
        print(line, count)


def corrected_star_value_before() -> None:
    count, handle = *[0], PATH.open()
    for line in handle:
        print(line, count)


def quiet_star_value_first_place() -> None:
    handle, count = *[PATH.open()], 0
    for line in handle.readlines():
        print(line, count)


def faulty_nested_first_place() -> None:
    (handle, count), other = (PATH.open(), 0), 1
    for line in handle.readlines():
        print(line, count, other)


def corrected_nested_first_place() -> None:
    (handle, count), other = (PATH.open(), 0), 1
    for line in handle:
        print(line, count, other)


def faulty_list_value_tuple_target() -> None:
    handle, count = [PATH.open(), 0]
    for line in handle.readlines():
        print(line, count)


def corrected_list_value_tuple_target() -> None:
    handle, count = [PATH.open(), 0]
    for line in handle:
        print(line, count)


def faulty_single_list_target() -> None:
    [handle] = [PATH.open()]
    for line in handle.readlines():
        print(line)


def corrected_single_list_target() -> None:
    [handle] = [PATH.open()]
    for line in handle:
        print(line)


def quiet_chained_tuple_value() -> None:
    handle = other = PATH.open(), 0
    for line in handle[0].readlines():
        print(line, other)


def faulty_textio_annotation_then_assign() -> None:
    handle: TextIO
    handle = PATH.open()
    for line in handle.readlines():
        print(line)


def corrected_textio_annotation_then_assign() -> None:
    handle: TextIO
    handle = PATH.open()
    for line in handle:
        print(line)


def quiet_try_except_rebind() -> None:
    try:
        handle = PATH.open()
    except OSError:
        handle = io.StringIO("")
    for line in handle.readlines():
        print(line)


def faulty_try_open_in_except() -> None:
    try:
        handle = io.StringIO("")
    except OSError:
        handle = PATH.open()
    for line in handle.readlines():
        print(line)


def corrected_try_open_in_except() -> None:
    try:
        handle = io.StringIO("")
    except OSError:
        handle = PATH.open()
    for line in handle:
        print(line)


def faulty_global_same_function() -> None:
    global SHARED
    SHARED = PATH.open()
    for line in SHARED.readlines():
        print(line)


def corrected_global_same_function() -> None:
    global SHARED
    SHARED = PATH.open()
    for line in SHARED:
        print(line)


def faulty_nonlocal_inner_read() -> None:
    handle = io.StringIO("")

    def inner() -> None:
        nonlocal handle
        handle = PATH.open()
        for line in handle.readlines():
            print(line)

    inner()


def corrected_nonlocal_inner_read() -> None:
    handle = io.StringIO("")

    def inner() -> None:
        nonlocal handle
        handle = PATH.open()
        for line in handle:
            print(line)

    inner()


def faulty_outer_open_inner_rebinds() -> None:
    handle = PATH.open()

    def inner() -> None:
        handle = io.StringIO("")
        for line in handle.readlines():
            print(line)

    inner()
    for line in handle.readlines():
        print(line)


def corrected_outer_open_inner_rebinds() -> None:
    handle = PATH.open()

    def inner() -> None:
        handle = io.StringIO("")
        for line in handle:
            print(line)

    inner()
    for line in handle:
        print(line)


def faulty_lambda_body_read() -> None:
    handle = PATH.open()
    count = (lambda: [line for line in handle.readlines()])()
    print(count)


def corrected_lambda_body_read() -> None:
    handle = PATH.open()
    count = (lambda: [line for line in handle])()
    print(count)
