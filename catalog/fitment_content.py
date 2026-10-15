"""Text derived from explicit fitment ranges, never from guessed end years."""
import re
from collections import defaultdict


_YEAR = r"(?:19\d{2}|20\d{2}|2100|\d{2})"
_YEARS = re.compile(
    rf"(?<![\w./-])'?(?P<start>{_YEAR})\s*[-–—−‑](?:\s*'?(?P<end>{_YEAR}))?(?![\w./-])"
    r"|(?<![\w./-])(?P<single>19\d{2}|20\d{2}|2100)(?![\w./-])"
    r"|(?<![\w./-])'?(?P<short_single>\d{2})(?=\s*$)"
)


def year_label(start, end):
    return str(start) if start == end else f"{start}-{end}"


def _expand_year(value):
    number = int(value)
    return number if len(value) == 4 else number + (2000 if number <= 39 else 1900)


def year_replacements(before, after):
    """A shared old range may split across models; never invent one new range."""
    choices = defaultdict(set)
    for pk, old in before.items():
        new = after.get(pk)
        choices[(old.year_from, old.year_to)].add(
            (new.year_from, new.year_to) if new is not None else None
        )
    return {
        old: next(iter(targets)) if len(targets) == 1 else None
        for old, targets in choices.items() if targets != {old}
    }


def replace_years(text, replacements, numeric_models=()):
    """Replace only complete tokens matching a known previous fitment range."""
    def replace(match):
        single = match["single"] or match["short_single"]
        start = _expand_year(single or match["start"])
        end = start if single or not match["end"] else _expand_year(match["end"])
        if single and single in numeric_models:
            return match[0]
        old = (start, end)
        if old not in replacements:
            return match[0]
        new = replacements[old]
        return year_label(*new) if new else ""

    result = _YEARS.sub(replace, text)
    if result == text:
        return text
    # Removing an ambiguous/deleted range can leave empty parentheses.
    result = re.sub(r"\(\s*\)|\[\s*\]", "", result)
    return re.sub(r"\s+", " ", result).strip()


def corrected_notes(notes, old, fitment):
    years = year_label(fitment.year_from, fitment.year_to)
    replacements = {(old.year_from, old.year_to): (fitment.year_from, fitment.year_to)} if old else {}
    # Notes are a generation label. Normalize its year tokens even when a prior
    # manual edit left the label out of sync with the actual fitment row.
    for match in _YEARS.finditer(notes):
        single = match["single"] or match["short_single"]
        start = _expand_year(single or match["start"])
        end = start if single or not match["end"] else _expand_year(match["end"])
        replacements[(start, end)] = (fitment.year_from, fitment.year_to)
    numeric_models = {fitment.vehicle_model.name} if fitment.vehicle_model.name.isdigit() else set()
    result = replace_years(notes, replacements, numeric_models)
    if result == notes and years not in result:
        result = f"{result or fitment.vehicle_model.name} - {years}"
    return result or f"{fitment.vehicle_model.name} {years}"


def fitment_spec_values(fitments):
    vehicles = []
    generations = []
    for fitment in fitments:
        vehicle = f"{fitment.vehicle_model.make.name} {fitment.vehicle_model.name}"
        if vehicle not in vehicles:
            vehicles.append(vehicle)
        label = fitment.notes or f"{fitment.vehicle_model.name} {year_label(fitment.year_from, fitment.year_to)}"
        if label not in generations:
            generations.append(label)
    return {"მანქანა": "; ".join(vehicles), "თაობა": "; ".join(generations)}
