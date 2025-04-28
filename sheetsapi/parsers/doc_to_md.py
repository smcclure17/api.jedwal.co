from enum import StrEnum, auto
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
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


class GoogleDocsToMarkdown:
    def __init__(self, docs_json: Dict[str, Any]):
        """Initialize converter with Google Docs API JSON response"""
        self.docs_json = docs_json
        # Cache inline objects for quick lookup
        self.inline_objects = self.docs_json.get("inlineObjects", {})

    def convert(self) -> str:
        """Convert Google Docs JSON to Markdown"""
        if not self.docs_json or "body" not in self.docs_json:
            return ""

        content = self.docs_json.get("body", {}).get("content", [])
        result = ""
        list_context = ListContext(list_counters={})

        for element in content:
            result, list_context = self._process_element(element, result, list_context)

        return result

    def _process_element(
        self, element: Dict[str, Any], markdown: str, list_context: ListContext
    ) -> Tuple[str, ListContext]:
        """Process a document element and convert it to Markdown"""
        if "paragraph" in element:
            return self._process_paragraph(element["paragraph"], markdown, list_context)
        elif "table" in element:
            return self._process_table(element["table"], markdown), list_context
        elif "sectionBreak" in element:
            # Handle section breaks if needed
            return markdown, list_context
        # Add more element types as needed
        return markdown, list_context

    def _process_paragraph(
        self, paragraph: Dict[str, Any], markdown: str, list_context: ListContext
    ) -> Tuple[str, ListContext]:
        """Process a paragraph element"""
        paragraph_style = paragraph.get("paragraphStyle", {})
        named_style = paragraph_style.get("namedStyleType", NamedStyles.NORMAL)

        # Check if this is a list item
        if "bullet" in paragraph:
            return self._process_list_item(paragraph, markdown, list_context)

        # Check if paragraph contains an inline image
        if self._contains_inline_object(paragraph):
            return self._process_inline_image(paragraph, markdown), list_context

        # Process text content
        text_content = self._process_text_run_elements(paragraph.get("elements", []))

        # Apply heading formatting
        if named_style == NamedStyles.HEADING1:
            return markdown + f"# {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING2:
            return markdown + f"## {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING3:
            return markdown + f"### {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING4:
            return markdown + f"#### {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING5:
            return markdown + f"##### {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING6:
            return markdown + f"###### {text_content}\n\n", list_context
        elif named_style == NamedStyles.TITLE:
            return markdown + f"# {text_content}\n\n", list_context
        elif named_style == NamedStyles.SUBTITLE:
            return markdown + f"## {text_content}\n\n", list_context
        else:
            # Regular paragraph
            if text_content.strip():  # Only add non-empty paragraphs
                return markdown + f"{text_content}\n\n", list_context
            return markdown, list_context

    def _process_text_run_elements(self, elements: List[Dict[str, Any]]) -> str:
        """Process a list of text elements and return combined content"""
        return "".join(
            self._process_text_run(element["textRun"])
            for element in elements
            if "textRun" in element
        )

    def _process_text_run(self, text_run: Dict[str, Any]) -> str:
        """Process a text run and apply formatting"""
        content = text_run.get("content", "")
        text_style = text_run.get("textStyle", {})

        # Apply text formatting by wrapping content with appropriate markers
        if text_style.get("link"):
            url = text_style["link"].get("url", "")
            content = f"[{content}]({url})"

        if text_style.get("strikethrough"):
            content = f"~~{content}~~"

        if text_style.get("italic"):
            content = f"*{content}*"

        if text_style.get("bold"):
            content = f"**{content}**"

        return content

    def _contains_inline_object(self, paragraph: Dict[str, Any]) -> bool:
        """Check if paragraph contains an inline object (like an image)"""
        for element in paragraph.get("elements", []):
            if "inlineObjectElement" in element:
                return True
        return False

    def _process_inline_image(self, paragraph: Dict[str, Any], markdown: str) -> str:
        """Process a paragraph containing an inline image and convert to Markdown"""
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

                    title = embedded_obj.get("title", f"Image {inline_obj_id}")
                    return markdown + f"![{title}]({url})\n\n"

        return markdown

    def _process_paragraph(
        self, paragraph: Dict[str, Any], markdown: str, list_context: ListContext
    ) -> Tuple[str, ListContext]:
        """Process a paragraph element"""
        paragraph_style = paragraph.get("paragraphStyle", {})
        named_style = paragraph_style.get("namedStyleType", NamedStyles.NORMAL)

        # Check if this is a list item
        if "bullet" in paragraph:
            return self._process_list_item(paragraph, markdown, list_context)

        # Check if paragraph contains an inline image
        if self._contains_inline_object(paragraph):
            return self._process_inline_image(paragraph, markdown), list_context

        # Process text content
        text_content = self._process_text_elements(paragraph.get("elements", []))

        # Skip empty paragraphs
        if not text_content.strip():
            return markdown, list_context

        # Apply heading formatting
        if named_style == NamedStyles.HEADING1:
            return markdown + f"# {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING2:
            return markdown + f"## {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING3:
            return markdown + f"### {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING4:
            return markdown + f"#### {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING5:
            return markdown + f"##### {text_content}\n\n", list_context
        elif named_style == NamedStyles.HEADING6:
            return markdown + f"###### {text_content}\n\n", list_context
        elif named_style == NamedStyles.TITLE:
            return markdown + f"# {text_content}\n\n", list_context
        elif named_style == NamedStyles.SUBTITLE:
            return markdown + f"## {text_content}\n\n", list_context
        else:
            # Regular paragraph
            if text_content.strip():  # Only add non-empty paragraphs
                return markdown + f"{text_content}\n\n", list_context
            return markdown, list_context

    def _contains_inline_object(self, paragraph: Dict[str, Any]) -> bool:
        """Check if paragraph contains an inline object (like an image)"""
        for element in paragraph.get("elements", []):
            if "inlineObjectElement" in element:
                return True
        return False

    def _process_text_elements(self, elements: List[Dict[str, Any]]) -> str:
        """Process a list of text elements and return combined content"""
        return "".join(
            self._process_text_run(element["textRun"])
            for element in elements
            if "textRun" in element
        )

    def _process_text_run(self, text_run: Dict[str, Any]) -> str:
        """Process a text run and apply formatting"""
        content = text_run.get("content", "")
        text_style = text_run.get("textStyle", {})

        # Apply text formatting by wrapping content with appropriate markers
        if text_style.get("link"):
            url = text_style["link"].get("url", "")
            content = f"[{content}]({url})"

        if text_style.get("strikethrough"):
            content = f"~~{content}~~"

        if text_style.get("italic"):
            content = f"*{content}*"

        if text_style.get("bold"):
            content = f"**{content}**"

        return content

    def _process_list_item(
        self, paragraph: Dict[str, Any], markdown: str, list_context: ListContext
    ) -> Tuple[str, ListContext]:
        """Process a list item paragraph"""
        bullet = paragraph.get("bullet", {})
        list_id = bullet.get("listId", "")
        nesting_level = bullet.get("nestingLevel", 0)

        # Process text content
        text_content = self._process_text_elements(paragraph.get("elements", []))

        # Determine list marker
        glyph_type = self._get_list_glyph_type(list_id, nesting_level)

        # Create a copy of list counters for modification
        updated_counters = dict(list_context.list_counters)

        # For ordered lists
        if glyph_type in ("DECIMAL", "UPPER_ALPHA", "LOWER_ALPHA"):
            counter_key = f"{list_id}_{nesting_level}"

            if (
                list_context.current_list_id != list_id
                or list_context.current_list_nesting != nesting_level
            ):
                updated_counters[counter_key] = 1
            else:
                updated_counters[counter_key] = updated_counters.get(counter_key, 0) + 1

            # Add indentation based on nesting level
            indent = "  " * nesting_level
            new_markdown = (
                markdown + f"{indent}{updated_counters[counter_key]}. {text_content}"
            )
        else:
            # Unordered list
            indent = "  " * nesting_level
            new_markdown = markdown + f"{indent}- {text_content}"

        # Create new list context
        new_list_context = ListContext(
            list_counters=updated_counters,
            current_list_id=list_id,
            current_list_nesting=nesting_level,
            in_list=True,
        )

        return new_markdown, new_list_context

    def _get_list_glyph_type(self, list_id: str, nesting_level: int) -> str:
        """Get the glyph type for a list item"""
        lists = self.docs_json.get("data", {}).get("lists", {})
        if list_id in lists:
            list_def = lists[list_id]
            nesting_levels = list_def.get("listProperties", {}).get("nestingLevels", [])
            if nesting_level < len(nesting_levels):
                return nesting_levels[nesting_level].get("glyphType", "BULLET")
        return "BULLET"

    def _process_table(self, table: Dict[str, Any], markdown: str) -> str:
        """Process a table element"""
        rows = table.get("tableRows", [])
        if not rows:
            return markdown

        result = markdown

        # Generate markdown table
        for row_idx, row in enumerate(rows):
            cells = row.get("tableCells", [])

            # Process each cell in the row
            cell_contents = []
            for cell in cells:
                cell_paragraphs = []
                for content_item in cell.get("content", []):
                    if "paragraph" in content_item:
                        text = self._process_text_elements(
                            content_item["paragraph"].get("elements", [])
                        ).strip()
                        if text:
                            cell_paragraphs.append(text)

                cell_contents.append(" ".join(cell_paragraphs))

            # Build the row markdown
            row_md = "| " + " | ".join(cell_contents) + " |"
            result += row_md + "\n"

            # Add separator row after header
            if row_idx == 0:
                separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                result += separator + "\n"

        return result
