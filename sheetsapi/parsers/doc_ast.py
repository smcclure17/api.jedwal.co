from enum import Enum, StrEnum, auto
import json
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, fields, is_dataclass, asdict
from functools import reduce


from sheetsapi.image_handler import ImageHandler


class ElementType(StrEnum):
    """Document element types enumeration"""

    DOCUMENT = auto()
    PARAGRAPH = auto()
    LIST_ITEM = auto()
    TEXT = auto()
    TABLE = auto()
    TABLE_CELL = auto()
    TABLE_ROW = auto()
    IMAGE = auto()
    LINK = auto()
    HEADING = auto()


class NamedStyles(StrEnum):
    NORMAL = "NORMAL_TEXT"
    HEADING1 = "HEADING_1"
    HEADING2 = "HEADING_2"
    HEADING3 = "HEADING_3"
    HEADING4 = "HEADING_4"
    HEADING5 = "HEADING_5"
    HEADING6 = "HEADING_6"
    TITLE = "TITLE"
    SUBTITLE = "SUBTITLE"


@dataclass
class Node:
    """Base AST node"""

    node_type: ElementType


@dataclass
class TextNode(Node):
    """Text node with styling information"""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False


@dataclass
class LinkNode(Node):
    """Link node containing a URL and child nodes"""

    url: str
    children: List[Node] = field(default_factory=list)


@dataclass
class ImageNode(Node):
    """Image node with source URL and alt text"""

    src: str
    alt: str = ""
    title: str = ""


@dataclass
class ParagraphNode(Node):
    """Paragraph node containing child nodes"""

    children: List[Node] = field(default_factory=list)
    alignment: Optional[str] = None


@dataclass
class HeadingNode(Node):
    """Heading node with level and content"""

    level: int
    children: List[Node] = field(default_factory=list)


@dataclass
class ListItemNode(Node):
    """List item node with nesting level and child nodes"""

    nesting_level: int = 0
    ordered: bool = False
    list_id: str = ""
    number: Optional[int] = None
    children: List[Node] = field(default_factory=list)


@dataclass
class TableNode(Node):
    """Table node containing rows"""

    rows: List["TableRowNode"] = field(default_factory=list)


@dataclass
class TableRowNode(Node):
    """Table row node containing cells"""

    cells: List["TableCellNode"] = field(default_factory=list)
    is_header: bool = False


@dataclass
class TableCellNode(Node):
    """Table cell node containing child nodes"""

    children: List[Node] = field(default_factory=list)


@dataclass
class DocumentNode(Node):
    """Root document node containing all content"""

    children: List[Node] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class GoogleDocsParser:
    """Parse Google Docs API JSON into an AST structure"""

    def __init__(
        self, docs_json: Dict[str, Any], image_handler: Optional[ImageHandler]
    ):
        """Initialize parser with Google Docs API JSON response"""
        self.docs_json = docs_json
        # Cache inline objects for quick lookup
        self.inline_objects = self.docs_json.get("inlineObjects", {})
        # Store list counters
        self.list_counters = {}
        # Image handler
        self.image_handler = image_handler

    def parse(self) -> DocumentNode:
        """Parse Google Docs JSON to AST"""
        if not self.docs_json or "body" not in self.docs_json:
            return DocumentNode(node_type=ElementType.DOCUMENT)

        # Create document node
        document = DocumentNode(node_type=ElementType.DOCUMENT)

        # Set metadata
        document.metadata["title"] = self.docs_json.get("title", "")
        document.metadata["documentId"] = self.docs_json.get("documentId", "")

        # Process content
        content = self.docs_json.get("body", {}).get("content", [])

        for element in content:
            node = self._process_element(element)
            if node:
                document.children.append(node)

        return document

    def _process_element(self, element: Dict[str, Any]) -> Optional[Node]:
        """Process a document element and convert it to an AST node"""
        if "paragraph" in element:
            return self._process_paragraph(element["paragraph"])
        elif "table" in element:
            return self._process_table(element["table"])
        elif "sectionBreak" in element:
            # Not currently represented in AST
            return None
        # Add more element types as needed
        return None

    def _process_paragraph(self, paragraph: Dict[str, Any]) -> Node:
        """Process a paragraph element to AST node"""
        paragraph_style = paragraph.get("paragraphStyle", {})
        named_style = paragraph_style.get("namedStyleType", NamedStyles.NORMAL)

        # Check if this is a list item
        if "bullet" in paragraph:
            return self._process_list_item(paragraph)

        # Process elements
        elements = paragraph.get("elements", [])

        # Check if paragraph is a heading
        if named_style.startswith("HEADING_") or named_style in (
            NamedStyles.TITLE,
            NamedStyles.SUBTITLE,
        ):
            # Convert to heading node
            level = 1  # Default level

            if named_style == NamedStyles.TITLE:
                level = 1
            elif named_style == NamedStyles.SUBTITLE:
                level = 2
            elif named_style.startswith("HEADING_"):
                # Extract level from named style (e.g., "HEADING_1" -> 1)
                try:
                    level = int(named_style.split("_")[1])
                except (IndexError, ValueError):
                    level = 1

            heading = HeadingNode(node_type=ElementType.HEADING, level=level)

            # Process text elements
            for element in elements:
                if "inlineObjectElement" in element:
                    child = self._process_inline_object(element["inlineObjectElement"])
                    if child:
                        heading.children.append(child)
                elif "textRun" in element:
                    child = self._process_text_run(element["textRun"])
                    if child:
                        heading.children.append(child)

            return heading
        else:
            # Regular paragraph
            paragraph_node = ParagraphNode(node_type=ElementType.PARAGRAPH)

            # Process text elements
            for element in elements:
                if "inlineObjectElement" in element:
                    child = self._process_inline_object(element["inlineObjectElement"])
                    if child:
                        paragraph_node.children.append(child)
                elif "textRun" in element:
                    child = self._process_text_run(element["textRun"])
                    if child:
                        paragraph_node.children.append(child)

            return paragraph_node

    def _process_text_run(
        self, text_run: Dict[str, Any]
    ) -> Union[TextNode, LinkNode, None]:
        """Process a text run to AST node"""
        content = text_run.get("content", "")
        if not content:
            return None

        text_style = text_run.get("textStyle", {})

        # Check if this is a link
        if text_style.get("link"):
            url = text_style["link"].get("url", "")
            link_node = LinkNode(node_type=ElementType.LINK, url=url)

            # Create a text node for link content with styles
            text_node = TextNode(
                node_type=ElementType.TEXT,
                text=content,
                bold=text_style.get("bold", False),
                italic=text_style.get("italic", False),
                underline=text_style.get("underline", False),
                strikethrough=text_style.get("strikethrough", False),
            )

            link_node.children.append(text_node)
            return link_node
        else:
            # Regular text with styling
            return TextNode(
                node_type=ElementType.TEXT,
                text=content,
                bold=text_style.get("bold", False),
                italic=text_style.get("italic", False),
                underline=text_style.get("underline", False),
                strikethrough=text_style.get("strikethrough", False),
            )

    def _process_inline_object(
        self, inline_obj_element: Dict[str, Any]
    ) -> Optional[ImageNode]:
        """Process an inline object element (usually images)"""
        inline_obj_id = inline_obj_element.get("inlineObjectId")
        if not inline_obj_id or inline_obj_id not in self.inline_objects:
            return None

        # Extract image properties
        inline_obj = self.inline_objects[inline_obj_id]
        embedded_obj = inline_obj.get("inlineObjectProperties", {}).get(
            "embeddedObject", {}
        )
        image_props = embedded_obj.get("imageProperties", {})

        # Get image URL
        google_url = image_props.get("contentUri")
        if not google_url:
            return None
        if self.image_handler is not None:
            url = self.image_handler.upload(src=google_url)
        else:
            url = google_url

        title = embedded_obj.get("title", f"Image {inline_obj_id}")
        alt = embedded_obj.get("description", title)

        return ImageNode(node_type=ElementType.IMAGE, src=url, alt=alt, title=title)

    def _process_list_item(self, paragraph: Dict[str, Any]) -> ListItemNode:
        """Process a list item paragraph to AST node"""
        bullet = paragraph.get("bullet", {})
        list_id = bullet.get("listId", "")
        nesting_level = bullet.get("nestingLevel", 0)

        # Determine if ordered and get item number
        glyph_type = self._get_list_glyph_type(list_id, nesting_level)
        ordered = glyph_type in ("DECIMAL", "UPPER_ALPHA", "LOWER_ALPHA")

        # Get counter for ordered lists
        number = None
        if ordered:
            counter_key = f"{list_id}_{nesting_level}"
            if counter_key not in self.list_counters:
                self.list_counters[counter_key] = 1
            else:
                self.list_counters[counter_key] += 1

            number = self.list_counters[counter_key]

        # Create list item node
        list_item = ListItemNode(
            node_type=ElementType.LIST_ITEM,
            nesting_level=nesting_level,
            ordered=ordered,
            list_id=list_id,
            number=number,
        )

        # Process text elements
        for element in paragraph.get("elements", []):
            if "textRun" in element:
                child = self._process_text_run(element["textRun"])
                if child:
                    list_item.children.append(child)
            elif "inlineObjectElement" in element:
                child = self._process_inline_object(element["inlineObjectElement"])
                if child:
                    list_item.children.append(child)

        return list_item

    def _get_list_glyph_type(self, list_id: str, nesting_level: int) -> str:
        """Get the glyph type for a list item"""
        lists = self.docs_json.get("lists", {})
        if list_id in lists:
            list_def = lists[list_id]
            nesting_levels = list_def.get("listProperties", {}).get("nestingLevels", [])
            if nesting_level < len(nesting_levels):
                return nesting_levels[nesting_level].get("glyphType", "BULLET")
        return "BULLET"

    def _process_table(self, table: Dict[str, Any]) -> TableNode:
        """Process a table element to AST node"""
        table_node = TableNode(node_type=ElementType.TABLE)

        for row_idx, row in enumerate(table.get("tableRows", [])):
            row_node = TableRowNode(
                node_type=ElementType.TABLE_ROW,
                is_header=(row_idx == 0),  # Treat first row as header
            )

            for cell in row.get("tableCells", []):
                cell_node = TableCellNode(node_type=ElementType.TABLE_CELL)

                # Process cell content
                for content_item in cell.get("content", []):
                    if "paragraph" in content_item:
                        cell_para = self._process_paragraph(content_item["paragraph"])
                        cell_node.children.append(cell_para)

                row_node.cells.append(cell_node)

            table_node.rows.append(row_node)

        return table_node

CLASSES = {
    "ElementType": ElementType,
    "NamedStyles": NamedStyles,
    "DocumentNode": DocumentNode,
    "ParagraphNode": ParagraphNode,
    "TextNode": TextNode,
    "LinkNode": LinkNode,
    "ImageNode": ImageNode,
    "HeadingNode": HeadingNode,
    "ListItemNode": ListItemNode,
    "TableNode": TableNode,
    "TableRowNode": TableRowNode,
    "TableCellNode": TableCellNode,
}

def node_to_dict(node):
    if is_dataclass(node):
        result = {"__class__": node.__class__.__name__}
        for f in fields(node):
            value = getattr(node, f.name)
            result[f.name] = node_to_dict(value)
        return result
    elif isinstance(node, Enum):
        return {"__enum__": f"{node.__class__.__name__}.{node.name}"}
    elif isinstance(node, list):
        return [node_to_dict(v) for v in node]
    elif isinstance(node, dict):
        return {k: node_to_dict(v) for k, v in node.items()}
    else:
        return node


def dict_to_node(data, classes = CLASSES):
    if isinstance(data, dict):
        if "__enum__" in data:
            enum_name, member = data["__enum__"].split(".")
            enum_cls = classes[enum_name]
            return enum_cls[member]
        if "__class__" in data:
            cls_name = data["__class__"]
            cls = classes[cls_name]
            init_kwargs = {}
            for f in fields(cls):
                if f.name in data:
                    init_kwargs[f.name] = dict_to_node(data[f.name], classes)
            return cls(**init_kwargs)
        else:
            return {k: dict_to_node(v, classes) for k, v in data.items()}
    elif isinstance(data, list):
        return [dict_to_node(v, classes) for v in data]
    else:
        return data