from enum import StrEnum, auto
import json
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from functools import reduce


class ElementType(StrEnum):
    """Document element types enumeration, similar to DocumentApp.ElementType in Apps Script"""

    PARAGRAPH = auto()
    LIST_ITEM = auto()
    TEXT = auto()
    TABLE = auto()
    TABLE_CELL = auto()
    TABLE_ROW = auto()
    TABLE_OF_CONTENTS = auto()
    FOOTNOTE = auto()
    FOOTNOTE_SECTION = auto()
    FOOTER_SECTION = auto()
    HEADER_SECTION = auto()
    PAGE_BREAK = auto()
    HORIZONTAL_RULE = auto()
    INLINE_DRAWING = auto()
    INLINE_IMAGE = auto()
    UNSUPPORTED = auto()
    EQUATION = auto()


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


@dataclass(frozen=True)
class ListContext:
    """Immutable context for list processing"""

    list_counters: Dict[str, int]
    current_list_id: Optional[str] = None
    current_list_nesting: int = 0
    in_list: bool = False
    list_blocks: List[Dict[str, Any]] = field(default_factory=list)
    current_list_type: Optional[str] = None  # "ordered" or "unordered"


class GoogleDocsToJSON:
    def __init__(self, docs_json: Dict[str, Any]):
        """Initialize converter with Google Docs API JSON response"""
        self.docs_json = docs_json
        self.id_counter = 0
        # Cache inline objects for quick lookup
        self.inline_objects = self.docs_json.get("inlineObjects", {})

    def get_next_id(self) -> str:
        """Generate a unique ID for each block"""
        self.id_counter += 1
        return f"block-{self.id_counter:03d}"

    def convert(self) -> Dict[str, Any]:
        """Convert Google Docs JSON to structured CMS JSON"""
        if not self.docs_json or "body" not in self.docs_json:
            return {"blocks": []}

        content = self.docs_json.get("body", {}).get("content", [])
        blocks = []
        list_context = ListContext(list_counters={})

        for element in content:
            blocks, list_context = self._process_element(element, blocks, list_context)

        # Add metadata if available
        metadata = self._extract_metadata()
        result = {"blocks": blocks}

        if metadata:
            result["metadata"] = metadata

        return result

    def _extract_metadata(self) -> Dict[str, Any]:
        """Extract document metadata if available"""
        metadata = {}

        # Extract title from document properties if available
        doc_properties = self.docs_json.get("documentProperties", {})
        if "title" in doc_properties:
            metadata["title"] = doc_properties["title"]

        # Add other metadata extraction as needed
        return metadata

    def _process_element(
        self,
        element: Dict[str, Any],
        blocks: List[Dict[str, Any]],
        list_context: ListContext,
    ) -> Tuple[List[Dict[str, Any]], ListContext]:
        """Process a document element and convert it to JSON block"""
        if "paragraph" in element:
            return self._process_paragraph(element["paragraph"], blocks, list_context)
        elif "table" in element:
            table_block = self._process_table(element["table"])
            if table_block:
                blocks.append(table_block)
            return blocks, list_context
        elif "sectionBreak" in element:
            # Handle section breaks if needed
            return blocks, list_context

        return blocks, list_context

    def _process_paragraph(
        self,
        paragraph: Dict[str, Any],
        blocks: List[Dict[str, Any]],
        list_context: ListContext,
    ) -> Tuple[List[Dict[str, Any]], ListContext]:
        """Process a paragraph element"""
        paragraph_style = paragraph.get("paragraphStyle", {})
        named_style = paragraph_style.get("namedStyleType", NamedStyles.NORMAL)

        # Check if this is a list item
        if "bullet" in paragraph:
            return self._process_list_item(paragraph, blocks, list_context)

        # Check if paragraph contains an inline image
        if self._contains_inline_object(paragraph):
            image_block = self._process_inline_image(paragraph)
            if image_block:
                blocks.append(image_block)
            return blocks, list_context

        # Process text content and formatting
        text_content, formatting = self._process_text_elements(
            paragraph.get("elements", [])
        )

        # Skip empty paragraphs
        if not text_content.strip():
            return blocks, list_context

        block_id = self.get_next_id()

        # Apply heading formatting
        if named_style in (NamedStyles.HEADING1, NamedStyles.TITLE):
            blocks.append(
                {"id": block_id, "type": "heading", "level": 1, "content": text_content}
            )
        elif named_style in (NamedStyles.HEADING2, NamedStyles.SUBTITLE):
            blocks.append(
                {"id": block_id, "type": "heading", "level": 2, "content": text_content}
            )
        elif named_style == NamedStyles.HEADING3:
            blocks.append(
                {"id": block_id, "type": "heading", "level": 3, "content": text_content}
            )
        elif named_style == NamedStyles.HEADING4:
            blocks.append(
                {"id": block_id, "type": "heading", "level": 4, "content": text_content}
            )
        elif named_style == NamedStyles.HEADING5:
            blocks.append(
                {"id": block_id, "type": "heading", "level": 5, "content": text_content}
            )
        elif named_style == NamedStyles.HEADING6:
            blocks.append(
                {"id": block_id, "type": "heading", "level": 6, "content": text_content}
            )
        else:
            # Regular paragraph
            block = {"id": block_id, "type": "paragraph", "content": text_content}

            # Add formatting information if present
            if formatting:
                block["formatting"] = formatting

            blocks.append(block)

        return blocks, list_context

    def _contains_inline_object(self, paragraph: Dict[str, Any]) -> bool:
        """Check if paragraph contains an inline object (like an image)"""
        for element in paragraph.get("elements", []):
            if "inlineObjectElement" in element:
                return True
        return False

    def _process_inline_image(
        self, paragraph: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process a paragraph containing an inline image"""
        for element in paragraph.get("elements", []):
            if "inlineObjectElement" in element:
                inline_obj_id = element["inlineObjectElement"].get("inlineObjectId")
                if inline_obj_id and inline_obj_id in self.inline_objects:
                    # Extract image properties
                    inline_obj = self.inline_objects[inline_obj_id]
                    embedded_obj = inline_obj.get("inlineObjectProperties", {}).get(
                        "embeddedObject", {}
                    )
                    image_props = embedded_obj.get("imageProperties", {})

                    # Get image URL
                    url = image_props.get("contentUri")
                    if not url:
                        continue

                    # Get image dimensions
                    size = embedded_obj.get("size", {})
                    width = size.get("width", {}).get("magnitude")
                    height = size.get("height", {}).get("magnitude")

                    # Create image block
                    image_block = {
                        "id": self.get_next_id(),
                        "type": "image",
                        "url": url,
                        "alt": f"Image {inline_obj_id}",  # Default alt text
                    }

                    # Add dimensions if available
                    if width:
                        image_block["width"] = width
                    if height:
                        image_block["height"] = height

                    # Add caption if available
                    title = embedded_obj.get("title")
                    if title:
                        image_block["caption"] = title

                    return image_block

        return None

    def _process_text_elements(
        self, elements: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Process a list of text elements and return combined content with formatting info"""
        content = ""
        formatting = []

        for element in elements:
            if "textRun" not in element:
                continue

            text_run = element["textRun"]
            text_content = text_run.get("content", "")
            text_style = text_run.get("textStyle", {})

            start_pos = len(content)
            content += text_content
            end_pos = len(content)

            # Collect formatting information
            format_info = {}

            if text_style.get("link"):
                format_info["type"] = "link"
                format_info["url"] = text_style["link"].get("url", "")

            elif text_style.get("bold"):
                format_info["type"] = "bold"

            elif text_style.get("italic"):
                format_info["type"] = "italic"

            elif text_style.get("strikethrough"):
                format_info["type"] = "strikethrough"

            if format_info:
                format_info["range"] = [start_pos, end_pos]
                formatting.append(format_info)

        return content, formatting

    def _process_list_item(
        self,
        paragraph: Dict[str, Any],
        blocks: List[Dict[str, Any]],
        list_context: ListContext,
    ) -> Tuple[List[Dict[str, Any]], ListContext]:
        """Process a list item paragraph"""
        bullet = paragraph.get("bullet", {})
        list_id = bullet.get("listId", "")
        nesting_level = bullet.get("nestingLevel", 0)

        # Process text content and formatting
        text_content, formatting = self._process_text_elements(
            paragraph.get("elements", [])
        )
        if not text_content.strip():
            return blocks, list_context

        # Determine list type
        glyph_type = self._get_list_glyph_type(list_id, nesting_level)
        is_ordered = glyph_type in ("DECIMAL", "UPPER_ALPHA", "LOWER_ALPHA")
        list_type = "ordered" if is_ordered else "unordered"

        # Create a copy of list counters for modification
        updated_counters = dict(list_context.list_counters)

        # Handle list counters for ordered lists
        if is_ordered:
            counter_key = f"{list_id}_{nesting_level}"

            if (
                list_context.current_list_id != list_id
                or list_context.current_list_nesting != nesting_level
            ):
                updated_counters[counter_key] = 1
            else:
                updated_counters[counter_key] = updated_counters.get(counter_key, 0) + 1

        # Check if we need to create a new list block
        create_new_list = (
            not list_context.in_list
            or list_id != list_context.current_list_id
            or list_context.current_list_type != list_type
        )

        # Create list item object with formatting if present
        list_item = {"content": text_content}
        if formatting:
            list_item["formatting"] = formatting

        # Handle nesting
        if nesting_level > 0:
            list_item["nesting_level"] = nesting_level

        # Create or update list blocks
        if create_new_list:
            # Create a new list block
            list_block = {
                "id": self.get_next_id(),
                "type": "list",
                "style": list_type,
                "items": [list_item],
            }
            blocks.append(list_block)
            current_blocks = [list_block]
        else:
            # Add to existing list
            if (
                blocks
                and blocks[-1]["type"] == "list"
                and blocks[-1]["style"] == list_type
            ):
                blocks[-1]["items"].append(list_item)
                current_blocks = [blocks[-1]]
            else:
                # Create a new list if needed
                list_block = {
                    "id": self.get_next_id(),
                    "type": "list",
                    "style": list_type,
                    "items": [list_item],
                }
                blocks.append(list_block)
                current_blocks = [list_block]

        # Create new list context
        new_list_context = ListContext(
            list_counters=updated_counters,
            current_list_id=list_id,
            current_list_nesting=nesting_level,
            in_list=True,
            list_blocks=current_blocks,
            current_list_type=list_type,
        )

        return blocks, new_list_context

    def _get_list_glyph_type(self, list_id: str, nesting_level: int) -> str:
        """Get the glyph type for a list item"""
        lists = self.docs_json.get("data", {}).get("lists", {})
        if list_id in lists:
            list_def = lists[list_id]
            nesting_levels = list_def.get("listProperties", {}).get("nestingLevels", [])
            if nesting_level < len(nesting_levels):
                return nesting_levels[nesting_level].get("glyphType", "BULLET")
        return "BULLET"

    def _process_table(self, table: Dict[str, Any]) -> Dict[str, Any]:
        """Process a table element"""
        rows = table.get("tableRows", [])
        if not rows:
            return None

        table_data = []

        # Process each row
        for row in rows:
            row_data = []
            cells = row.get("tableCells", [])

            # Process each cell in the row
            for cell in cells:
                cell_content = ""
                cell_formatting = []

                # Process cell content
                for content_item in cell.get("content", []):
                    if "paragraph" in content_item:
                        text, formatting = self._process_text_elements(
                            content_item["paragraph"].get("elements", [])
                        )
                        cell_content += text

                        # Adjust formatting ranges for the combined content
                        for format_item in formatting:
                            format_item["range"][0] += len(cell_content) - len(text)
                            format_item["range"][1] += len(cell_content) - len(text)
                            cell_formatting.append(format_item)

                cell_obj = {"content": cell_content.strip()}
                if cell_formatting:
                    cell_obj["formatting"] = cell_formatting

                row_data.append(cell_obj)

            table_data.append(row_data)

        return {"id": self.get_next_id(), "type": "table", "rows": table_data}


# Usage example
def convert_google_docs_to_json(docs_json):
    converter = GoogleDocsToJSON(docs_json)
    return converter.convert()


# Example usage
if __name__ == "__main__":
    # Load Google Docs JSON from file or API response
    with open("google_docs_export.json", "r") as f:
        docs_json = json.load(f)

    result = convert_google_docs_to_json(docs_json)
    print(json.dumps(result, indent=2))
