import yaml
import difflib

def make_yaml_diff(old: dict, new: dict) -> str:
    old_txt = yaml.dump(old, sort_keys=False, allow_unicode=True).splitlines(keepends=True)
    new_txt = yaml.dump(new, sort_keys=False, allow_unicode=True).splitlines(keepends=True)
    return "".join(difflib.unified_diff(old_txt, new_txt, fromfile="before", tofile="after"))
