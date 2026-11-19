"""Keep ranch actions opt-in when an existing account has no saved value."""

import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
config = root / 'core/src/config/ranch-automation.ts'
source = config.read_text(encoding='utf-8')
defaults = re.compile(r'(?ms)^export const RANCH_AUTOMATION_DEFAULTS = \{\n(.*?)^\};')
boolean = re.compile(r'(?m)^(    (ranch_\w+): )(?:true|false)(,)$')
existing_enabled = {'ranch_task', 'ranch_share'}


def preserve_defaults(match):
    fields = boolean.findall(match[1])
    if not existing_enabled.issubset(field for _, field, _ in fields):
        raise RuntimeError('Ranch defaults changed shape; review the update')
    updated = boolean.sub(
        lambda field: field[1] + ('true' if field[2] in existing_enabled else 'false') + field[3],
        match[1],
    )
    return match[0].replace(match[1], updated, 1)


updated, count = defaults.subn(preserve_defaults, source)
if count != 1:
    raise RuntimeError('Expected one ranch defaults declaration')
config.write_text(updated, encoding='utf-8')
