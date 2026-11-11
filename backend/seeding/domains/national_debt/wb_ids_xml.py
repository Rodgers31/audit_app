"""Decode the World Bank Advanced Data API XML envelope."""

from xml.etree import ElementTree

from ...isolated_parser import isolated

_WB_NAMESPACE = "{http://www.worldbank.org}"


class _NoDoctype(ElementTree.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError("IDS XML cannot contain a document type")


@isolated("body", timeout=15)
def parse_ids_xml(body: bytes) -> dict:
    """Extract the XML fields without conferring source or monetary authority."""
    tag = _WB_NAMESPACE
    try:
        root = ElementTree.fromstring(
            body, parser=ElementTree.XMLParser(target=_NoDoctype())
        )
        if root.tag != tag + "data" or len(root) != 1 or root[0].tag != tag + "source":
            raise ValueError("unexpected IDS XML envelope")
        source = root[0]
        records = []
        for row in source:
            if (
                row.tag != tag + "data"
                or len(row) != 5
                or any(len(node) for node in row)
            ):
                raise ValueError("unexpected IDS XML row")
            variables = row.findall(tag + "variable")
            values = row.findall(tag + "value")
            if len(variables) != 4 or len(values) != 1:
                raise ValueError("unexpected IDS XML row")
            records.append(
                {
                    "variable": [
                        dict(node.attrib, value=node.text) for node in variables
                    ],
                    "value": values[0].text,
                }
            )
        return {
            **{
                key: int(root.attrib[key])
                for key in ("page", "pages", "per_page", "total")
            },
            "lastupdated": root.attrib.get("lastupdated"),
            "source": dict(source.attrib, data=records),
        }
    except (ElementTree.ParseError, KeyError) as exc:
        raise ValueError("malformed IDS XML response") from exc
