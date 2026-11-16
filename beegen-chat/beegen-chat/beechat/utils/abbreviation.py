import pandas as pd
from typing import Dict


class AbbreviationHandler:
    def __init__(self, abbreviation_file_path: str = 'beeportal/bot_bee247/bee247/abbreviations.csv'):
        """Initialize the abbreviation handler with a CSV file of abbreviations."""
        self.abbr_dict = self._load_abbreviation(abbreviation_file_path)

    def _load_abbreviation(self, file_path: str) -> Dict[str, str]:
        """Load abbreviation dictionary from CSV file."""
        try:
            abb_df = pd.read_csv(file_path, encoding="utf-8-sig")
            abb_df["Abbreviation"] = abb_df["Abbreviation"].str.lower()
            abb_dict = dict(zip(abb_df["Abbreviation"], abb_df["Meaning"]))
            return abb_dict
        except Exception as e:
            print(f"Error loading abbreviations: {e}")
            return {}

    def annotate_query(self, query: str) -> str:
        """Adds explanations after abbreviations found in text."""
        words = query.split()

        result = []
        for word in words:
            if word.lower() in self.abbr_dict:
                result.append(f"{word} ({self.abbr_dict[word.lower()]})")
            else:
                result.append(word)

        anns_query = " ".join(result)
        return anns_query
    

if __name__ == "__main__":
    abbr_handler = AbbreviationHandler()
    print(abbr_handler.abbr_dict)