# LOOP003 str-concat-in-loop: each faulty_ function holds one form of the fault, its corrected_
# twin the io.StringIO or str.join form, its outside_ twin the same statement outside any loop, and
# each clean_ function a str each pass assigns afresh
import io
from dataclasses import dataclass

DESCRIPTION_WORD_LIMIT = 20


@dataclass(frozen=True)
class Volume:
    label: str
    size_gb: float
    has_auth_file: bool


def faulty_for(rows: list[list[str]]) -> str:
    out = ""
    for row in rows:
        out += ",".join(row) + "\n"
    return out


def corrected_for(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    for row in rows:
        buffer.write(",".join(row) + "\n")
    return buffer.getvalue()


def outside_for(rows: list[list[str]]) -> str:
    out = ""
    out += ",".join(rows[0])
    widths = [len(row) for row in rows]
    return out + str(widths)


def faulty_while(count: int) -> str:
    text = ""
    step = 0
    while step < count:
        text += str(step)
        step += 1
    return text


def corrected_while(count: int) -> str:
    parts: list[str] = []
    step = 0
    while step < count:
        parts.append(str(step))
        step += 1
    return "".join(parts)


def outside_while(count: int) -> str:
    text = ""
    text += "start"
    step = 0
    while step < count:
        step += 1
    return text + str(step)


def faulty_nested(grid: list[list[str]]) -> str:
    text = ""
    for row in grid:
        for cell in row:
            text += cell
    return text


def corrected_nested(grid: list[list[str]]) -> str:
    buffer = io.StringIO()
    for row in grid:
        for cell in row:
            buffer.write(cell)
    return buffer.getvalue()


def outside_nested(grid: list[list[str]]) -> str:
    text = ""
    text += grid[0][0]
    cells = [cell for row in grid for cell in row]
    return text + str(len(cells))


def faulty_rebind(words: list[str]) -> str:
    text = ""
    for word in words:
        text = text + word
    return text


def corrected_rebind(words: list[str]) -> str:
    buffer = io.StringIO()
    for word in words:
        buffer.write(word)
    return buffer.getvalue()


def outside_rebind(words: list[str]) -> str:
    text = ""
    text = text + words[0]
    return text + str([len(word) for word in words])


def faulty_site_trophy_cards(tiers: list[str], colors: dict[str, str]) -> str:
    cards = ""
    for tier in tiers:
        colour = colors[tier]
        cards += f'<div style="color:{colour}">{tier}</div>'
    return cards


def corrected_site_trophy_cards(tiers: list[str], colors: dict[str, str]) -> str:
    buffer = io.StringIO()
    for tier in tiers:
        colour = colors[tier]
        buffer.write(f'<div style="color:{colour}">{tier}</div>')
    return buffer.getvalue()


def outside_site_trophy_cards(tiers: list[str], colors: dict[str, str]) -> str:
    cards = ""
    cards += f'<div style="color:{colors[tiers[0]]}">{tiers[0]}</div>'
    return cards + str([colors[tier] for tier in tiers])


def faulty_site_fitted(head: str, *extras: str) -> str:
    text = str(head)
    for extra in extras:
        if extra and len((text + extra).split()) <= DESCRIPTION_WORD_LIMIT:
            text += extra
    return text


def corrected_site_fitted(head: str, *extras: str) -> str:
    parts = [str(head)]
    words = len(parts[0].split())
    for extra in extras:
        if extra and words + len(extra.split()) <= DESCRIPTION_WORD_LIMIT:
            parts.append(extra)
            words += len(extra.split())
    return "".join(parts)


def outside_site_fitted(head: str, *extras: str) -> str:
    text = str(head)
    text += extras[0]
    return text + str([len(extra) for extra in extras])


def clean_site_usb_labels(volumes: list[Volume]) -> list[str]:
    labels: list[str] = []
    for vol in volumes:
        label = f"{vol.label} ({vol.size_gb:.1f} GB)"
        if vol.has_auth_file:
            label += " key present"
        labels.append(label)
    return labels


def clean_site_api_details(endpoints: list[tuple[str, str]], unread: int) -> list[str]:
    details: list[str] = []
    for method, url in endpoints:
        detail = f"Method: {method}\nURL: {url}\n"
        if unread:
            detail += f"{unread} more bytes"
        details.append(detail)
    return details


def clean_site_transaction_queries(symbol: str, pages: int) -> list[str]:
    queries: list[str] = []
    page = 0
    while page < pages:
        query = f"?per-page=250&page-offset={page}&sort=Asc&types[]=Trade"
        if symbol:
            query += f"&symbol={symbol}"
        queries.append(query)
        page += 1
    return queries


class FaultyAttributeLog:
    def __init__(self) -> None:
        self.text = ""

    def write_all(self, words: list[str]) -> None:
        for word in words:
            self.text += word


class CorrectedAttributeLog:
    def __init__(self) -> None:
        self.buffer = io.StringIO()

    def write_all(self, words: list[str]) -> None:
        for word in words:
            self.buffer.write(word)


class OutsideAttributeLog:
    def __init__(self) -> None:
        self.text = ""

    def write_all(self, words: list[str]) -> list[int]:
        self.text += words[0]
        return [len(word) for word in words]


class CleanAttributeLabel:
    def __init__(self) -> None:
        self.label = ""

    def label_all(self, words: list[str]) -> list[str]:
        labels: list[str] = []
        for word in words:
            self.label = f"{word}:"
            self.label += " present"
            labels.append(self.label)
        return labels
