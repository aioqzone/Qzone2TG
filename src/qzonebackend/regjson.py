import json
import re

__all__ = ['json_loads']

re_clause = re.compile(r"([a-zA-Z_][a-zA-Z_\d]*)\s*:\s*([\{\[])")
re_bool = re.compile(r"([a-zA-Z_][a-zA-Z_\d]*)\s*:\s*(true|false)\s*([,\}\]])")
re_num = re.compile(r"([a-zA-Z_][a-zA-Z_\d]*)\s*:\s*(\d+\.?\d*)\s*([,\}\]])")
re_undefined_k = re.compile(
    r"\"?([a-zA-Z_][a-zA-Z_\d]*)\"?\s*:([^']*)undefined([^']*)([,\}\]])"
)
re_undefined_v = re.compile(r",([^']*?)undefined([^']*)([,\]])")
re_str = re.compile(r"([a-zA-Z_][a-zA-Z_\d]*)\s*:\s*'([^']*?)'\s*([,\}\]])")
re_asctag = re.compile(r"([^\\])\\x")


def regulateJson(json_str: str) -> str:
    json_str = re_asctag.sub(r'\1\\\\x', json_str)
    json_str = re_clause.sub(r'"\1":\2', json_str)
    json_str = re_bool.sub(r'"\1":\2\3', json_str)
    json_str = re_num.sub(r'"\1":\2\3', json_str)
    json_str = re_undefined_k.sub(r'"\1":\2null\3\4', json_str)
    json_str = re_undefined_v.sub(r',\1null\2\3', json_str)
    json_str = re_str.sub(r'"\1":"\2"\3', json_str)
    return json_str


def json_loads(s, *args, **kwargs):
    try:
        return json.loads(s, *args, **kwargs)
    except json.JSONDecodeError:
        return json.loads(regulateJson(s), *args, **kwargs)
