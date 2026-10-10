"""Render untrusted evidence as text without activating Markdown or templates."""

import html
import re

import yaml


def inline(value: str) -> str:
    text = " ".join(str(value).splitlines())
    text = re.sub(r"([\\`*_\[\]()!#$~])", r"\\\1", text)
    return html.escape(text, quote=False)


def literal(value: str) -> str:
    """HTML text escaping preserves displayed characters, including code fences.

    A fence alone would leave raw <% template openers in the file. Escaped text
    inside pre/code also prevents those openers, remote images and active code
    blocks from becoming source-authored executable markup.
    """
    return "<pre><code>" + html.escape(value, quote=False) + "</code></pre>"


class EvidenceDumper(yaml.SafeDumper):
    pass


def _string(dumper, value):
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style='"' if "<" in value else None
    )


EvidenceDumper.add_representer(str, _string)


def note(properties: dict, body: str) -> str:
    # Keep YAML values exact when parsed, while preventing a template plugin
    # from finding an executable opener in an alias, title or source URI.
    metadata = yaml.dump(properties, Dumper=EvidenceDumper, sort_keys=False, allow_unicode=True)
    metadata = metadata.replace("<", "\\u003c")
    return "---\n" + metadata + "---\n" + body.rstrip() + "\n"
