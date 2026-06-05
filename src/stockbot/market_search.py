import unicodedata

import pandas as pd


def _tokenize(keyword: str) -> list[str]:
    tokens = []
    for part in keyword.split():
        if len(part) > 2 and all(unicodedata.east_asian_width(c) in ("W", "F") for c in part):
            tokens.extend(part[i:i + 2] for i in range(0, len(part), 2))
        else:
            tokens.append(part)
    return tokens


def search_by_name(keyword: str) -> pd.DataFrame:
    from .market_data import get_index_list, get_stock_list

    tokens = _tokenize(keyword)

    def matches(name: str) -> bool:
        return all(t in name for t in tokens)

    stock_df = get_stock_list()
    stock_matches = stock_df[stock_df["name"].apply(matches)].copy()
    idx = get_index_list()
    index_matches = idx[idx["name"].apply(matches)].copy()
    if not index_matches.empty:
        stock_matches = pd.concat([index_matches, stock_matches], ignore_index=True)
    return stock_matches.reset_index(drop=True)
