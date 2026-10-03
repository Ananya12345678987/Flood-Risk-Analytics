"""District-name normalisation, alias table and resolver.

The flood inventory (IFI) uses current district names; the boundary file is Census 2011.
ALIASES maps normalised IFI names to the normalised 2011 shapefile name, per state.
Entry kinds: RENAME (same district), TYPO (spelling error), PARENT (district created
after 2011 -> attributed to its 2011 parent district; an approximation).
"""
import re


def norm(s):
    s = str(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


ALIASES = {
    "assam": {
        "kamrup metro": "kamrup metropolitan",            # RENAME
        "west karbi anglong": "karbi anglong",            # PARENT (2015)
        "biswanath": "sonitpur",                          # PARENT (2015)
        "hojai": "nagaon",                                # PARENT (2016)
        "majuli": "jorhat",                               # PARENT (2016)
        "charaideo": "sivasagar",                         # PARENT (2016) - verify
        "south salmara mancachar": "dhubri",              # PARENT (2016)
        "south salmara mancachar mankachar": "dhubri",    # PARENT (2016)
        "mancachar": "dhubri",                            # TYPO (Mankachar is in Dhubri)
    },
    "kerala": {
        "kochi": "ernakulam",                             # city inside Ernakulam district
    },
    "karnataka": {
        "uttar kashia kannada": "uttara kannada",         # TYPO
        "belagavi": "belgaum",
        "bengaluru urban": "bangalore",
        "bengaluru rural": "bangalore rural",
        "ballari": "bellary",
        "vijayanagara": "bellary",                        # PARENT (2021)
        "mysuru": "mysore",
        "kalaburagi": "gulbarga",
        "shivamogga": "shimoga",
        "davangere": "davanagere",
        "tumakuru": "tumkur",
        "beedar": "bidar",
        "bagalkotee": "bagalkot",                         # TYPO
        "bagalkote": "bagalkot",                          # TYPO
        "vijayapura": "bijapur",
        "chikkamagaluru": "chikmagalur",
        "chamarajanagara": "chamrajnagar",                # TYPO
        "chamarajanagaraa": "chamrajnagar",               # TYPO
        "chamarajanagar": "chamrajnagar",                 # spelling variant
        "mangalore": "dakshina kannada",                  # city inside DK - verify
        "chikodi": "belgaum",                             # taluk inside Belgaum - verify
    },
    "maharashtra": {
        "beed": "bid",
        "gadchiroli": "garhchiroli",
        "buldhana": "buldana",
        "dharashiv": "osmanabad",
        "palghar": "thane",                               # PARENT (2014)
        "ahmednagar": "ahmadnagar",
        "gondia": "gondiya",
        "raigad": "raigarh",
        "yavotmal": "yavatmal",                           # TYPO
    },
}

NOISE = {"and", "ant"}   # connector words/typos allowed between names in a concatenated string


def canonical(state_n, dist_n):
    return ALIASES.get(state_n, {}).get(dist_n, dist_n)


def resolve(state_n, text, shp_names):
    """Map a raw district string to shapefile district names.

    Returns (list_of_names, status), status in: exact | split | unmatched | empty.
    'split' = a concatenated string (missing comma) fully explained by known names.
    A string is only accepted if NOTHING unexplained is left over.
    """
    t = norm(text)
    if not t:
        return [], "empty"
    c = canonical(state_n, t)
    if c in shp_names:
        return [c], "exact"
    keys = set(shp_names) | set(ALIASES.get(state_n, {}).keys())
    rest, found = t, []
    for k in sorted(keys, key=len, reverse=True):
        if k in rest:
            found.append(canonical(state_n, k))
            rest = rest.replace(k, " ")
    leftover = [w for w in rest.split() if w not in NOISE]
    if found and not leftover:
        return list(dict.fromkeys(found)), "split"
    return [], "unmatched"
