import re
from difflib import SequenceMatcher


def _name_parts(name):
    value = str(name).strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    return [part.lower() for part in value.split() if part]


def _normalised_name(name):
    return "".join(_name_parts(name))


def _token_similarity(source, destination):
    a = set(_name_parts(source))
    b = set(_name_parts(destination))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def name_similarity(source, destination):
    normal_a = _normalised_name(source)
    normal_b = _normalised_name(destination)

    if not normal_a or not normal_b:
        return 0.0
    if normal_a == normal_b:
        return 1.0

    sequence_score = SequenceMatcher(None, normal_a, normal_b).ratio()
    token_score = _token_similarity(source, destination)
    return round(0.75 * sequence_score + 0.25 * token_score, 4)


def fuzzy_matches(source_names, destination_names, minimum_score=0.45):
    matches = []
    for source in source_names:
        for destination in destination_names:
            score = name_similarity(source, destination)
            if score >= minimum_score:
                matches.append({
                    "source": source,
                    "destination": destination,
                    "score": score,
                })
    return sorted(
        matches,
        key=lambda item: (-item["score"], item["source"], item["destination"]),
    )


def best_fuzzy_match(source, destination_names, used_destinations=None):
    used = set(used_destinations or [])
    candidates = [
        (destination, name_similarity(source, destination))
        for destination in destination_names
        if destination not in used
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[1], item[0]))
    destination, score = candidates[0]
    return {
        "source": source,
        "destination": destination,
        "score": round(score, 4),
    }


def similarity_label(score):
    if score >= 0.90:
        return "Very high"
    if score >= 0.80:
        return "High"
    if score >= 0.65:
        return "Medium"
    if score >= 0.50:
        return "Low"
    return "Very low"
