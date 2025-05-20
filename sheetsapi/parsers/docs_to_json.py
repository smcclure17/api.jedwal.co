from typing import Any, Dict, List, Tuple
from sheetsapi.parsers.doc_ast import DocumentNode, ElementType, ListItemNode, Node


class CustomJsonRenderer:
    """Renders an AST to a custom JSON schema"""

    def render(self, ast: DocumentNode) -> Dict[str, Any]:
        """Convert AST to custom JSON format"""
        blocks = []
        self._process_node_to_blocks(ast, blocks)

        result = {"blocks": blocks}

        # Add metadata if available
        if ast.metadata:
            result["metadata"] = ast.metadata

        return result

    def _process_node_to_blocks(self, node: Node, blocks: List[Dict[str, Any]]) -> None:
        """Process a node to JSON blocks"""
        if node.node_type == ElementType.DOCUMENT:
            # Track the current list state
            current_list_id = None
            current_list_type = None
            current_list_block = None

            for child in node.children:
                # Special handling for list items to group them
                if child.node_type == ElementType.LIST_ITEM:
                    list_item = child  # It's a ListItemNode

                    # Determine list type
                    list_type = "ordered" if list_item.ordered else "unordered"
                    list_id = list_item.list_id

                    # Check if we need to create a new list or continue an existing one
                    if current_list_id != list_id or current_list_type != list_type:
                        # Create a new list block
                        current_list_block = {
                            "id": list_item.node_id,  # Use the first item's ID for the list
                            "type": "list",
                            "style": list_type,
                            "items": [],
                        }
                        blocks.append(current_list_block)

                        # Update current list tracking
                        current_list_id = list_id
                        current_list_type = list_type

                    # Process the list item
                    text_content, formatting = self._extract_text_and_formatting(
                        list_item.children
                    )

                    item_obj = {"content": text_content}

                    # Add formatting if present
                    if formatting:
                        item_obj["formatting"] = formatting

                    # Add nesting level if needed
                    if list_item.nesting_level > 0:
                        item_obj["nesting_level"] = list_item.nesting_level

                    # Add to the current list
                    current_list_block["items"].append(item_obj)

                else:
                    # For non-list items, reset list tracking
                    current_list_id = None
                    current_list_type = None
                    current_list_block = None

                    # Process normally
                    self._process_node_to_blocks(child, blocks)

        elif node.node_type == ElementType.PARAGRAPH:
            # Create paragraph block
            text_content, formatting = self._extract_text_and_formatting(node.children)

            if text_content.strip():  # Skip empty paragraphs
                block = {
                    "id": node.node_id,
                    "type": "paragraph",
                    "content": text_content,
                }

                # Add formatting if present
                if formatting:
                    block["formatting"] = formatting

                blocks.append(block)

        elif node.node_type == ElementType.HEADING:
            # Create heading block
            text_content, formatting = self._extract_text_and_formatting(node.children)

            if text_content.strip():  # Skip empty headings
                block = {
                    "id": node.node_id,
                    "type": "heading",
                    "level": node.level,
                    "content": text_content,
                }

                # Add formatting if present
                if formatting:
                    block["formatting"] = formatting

                blocks.append(block)

        elif node.node_type == ElementType.IMAGE:
            # Create image block
            image_block = {
                "id": node.node_id,
                "type": "image",
                "url": node.src,
                "alt": node.alt,
            }

            # Add caption if available
            if node.title:
                image_block["caption"] = node.title

            # Add dimensions if available
            if node.width:
                image_block["width"] = node.width
            if node.height:
                image_block["height"] = node.height

            blocks.append(image_block)

        elif node.node_type == ElementType.TABLE:
            # Create table block
            table_rows = []

            for row in node.rows:
                row_cells = []

                for cell in row.cells:
                    cell_content, cell_formatting = self._extract_text_and_formatting(
                        cell.children
                    )

                    cell_obj = {"content": cell_content.strip()}
                    if cell_formatting:
                        cell_obj["formatting"] = cell_formatting

                    row_cells.append(cell_obj)

                table_rows.append(row_cells)

            if table_rows:  # Skip empty tables
                blocks.append({"id": node.node_id, "type": "table", "rows": table_rows})

    def _extract_text_and_formatting(
        self, nodes: List[Node]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Extract text content and formatting information from nodes"""
        content = ""
        formatting = []

        for node in nodes:
            if node.node_type == ElementType.TEXT:
                start_pos = len(content)
                content += node.text
                end_pos = len(content)

                # Collect formatting information
                if node.bold:
                    formatting.append({"type": "bold", "range": [start_pos, end_pos]})

                if node.italic:
                    formatting.append({"type": "italic", "range": [start_pos, end_pos]})

                if node.strikethrough:
                    formatting.append(
                        {"type": "strikethrough", "range": [start_pos, end_pos]}
                    )

            elif node.node_type == ElementType.LINK:
                start_pos = len(content)

                # Extract text from link
                link_text = ""
                for child in node.children:
                    if child.node_type == ElementType.TEXT:
                        link_text += child.text

                content += link_text
                end_pos = len(content)

                # Add link formatting
                formatting.append(
                    {"type": "link", "url": node.url, "range": [start_pos, end_pos]}
                )

            elif node.node_type == ElementType.PARAGRAPH:
                # For nested paragraphs (e.g., in table cells)
                nested_content, nested_formatting = self._extract_text_and_formatting(
                    node.children
                )

                start_pos = len(content)
                content += nested_content
                end_pos = len(content)

                # Adjust ranges for nested formatting
                for fmt in nested_formatting:
                    fmt["range"][0] += start_pos
                    fmt["range"][1] += start_pos
                    formatting.append(fmt)

                # Add a space after nested paragraphs if not at the end
                if content and not content.endswith("\n"):
                    content += " "

        return content, formatting
