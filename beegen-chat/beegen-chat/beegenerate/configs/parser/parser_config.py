from enum import Enum

class ParserType(str, Enum):
    JSON = "json"
    YAML = "yaml"
    XML = "xml"
    KEY_VALUE = "key_value"
    STRUCTURED = "structured"
    REGEX = "regex"
    

PARSER_REQUIREMENTS = {
    ParserType.KEY_VALUE: ['separator'],
    ParserType.STRUCTURED: ['template'],
    ParserType.REGEX: ['pattern']
}
    

if __name__ == "__main__":
    from pprint import pprint
    import json
    