import re
from typing import List
from jedwal.posts.parsers.doc_ast import DocumentNode, ElementType, Node


INDENTATION = "  "


class MarkdownRenderer:
    """Renders an AST to Markdown format with consistent, opinionated spacing"""

    def render(self, ast: DocumentNode) -> str:
        """Convert AST to Markdown with standardized spacing"""
        result = []
        self._render_node(ast, result)
        content = "".join(result)

        # Normalize multiple consecutive newlines down to at most two (one blank line)
        return re.sub(r"\n{3,}", "\n\n", content)

    def _render_node(self, node: Node, result: List[str]) -> None:
        """Render a node to Markdown"""
        if node.node_type == ElementType.DOCUMENT:
            for i, child in enumerate(node.children):
                # No need for spacing before the first element
                if i > 0 and self._is_block_element(child):
                    # Make sure there's exactly one blank line before each block element
                    self._ensure_blank_line(result)

                self._render_node(child, result)

        elif node.node_type == ElementType.PARAGRAPH:
            # Render paragraph content
            for child in node.children:
                self._render_node(child, result)

            # Ensure paragraph ends with a newline
            self._ensure_single_newline(result)

        elif node.node_type == ElementType.HEADING:
            heading = node
            result.append("#" * heading.level + " ")
            for child in node.children:
                self._render_node(child, result)

            # Ensure heading ends with a newline
            self._ensure_single_newline(result)

        elif node.node_type == ElementType.TEXT:
            text = node.text
            # Remove all trailing newlines for consistency
            text_content = text.rstrip("\n")

            if node.strikethrough:
                text_content = f"~~{text_content}~~"
            if node.bold:
                text_content = f"**{text_content}**"
            if node.italic:
                text_content = f"*{text_content}*"

            result.append(text_content)

        elif node.node_type == ElementType.LINK:
            link_text = []
            for child in node.children:
                if child.node_type == ElementType.TEXT:
                    # Remove trailing newlines from link text
                    link_text.append(child.text.rstrip("\n"))

            link_str = f"[{''.join(link_text)}]({node.url})"
            result.append(link_str)

        elif node.node_type == ElementType.IMAGE:
            result.append(f"![{node.alt}]({node.src})")
            self._ensure_single_newline(result)

        elif node.node_type == ElementType.LIST_ITEM:
            indent = INDENTATION * node.nesting_level
            if node.ordered and node.number is not None:
                result.append(f"{indent}{node.number}. ")
            else:
                result.append(f"{indent}- ")

            for child in node.children:
                self._render_node(child, result)

            # Ensure list items end with a single newline
            self._ensure_single_newline(result)

        elif node.node_type == ElementType.TABLE:
            if not node.rows:
                return

            for row_idx, row in enumerate(node.rows):
                cell_contents = []

                for cell in row.cells:
                    cell_md = []
                    for child in cell.children:
                        temp_result = []
                        self._render_node(child, temp_result)
                        # Remove trailing newlines in table cells
                        cell_content = "".join(temp_result).rstrip("\n")
                        if cell_content:
                            cell_md.append(cell_content)

                    # Join all content in the cell
                    cell_contents.append(" ".join(cell_md) if cell_md else " ")

                # Add table row with a newline
                result.append("| " + " | ".join(cell_contents) + " |\n")

                # Add separator row after header
                if row_idx == 0:
                    result.append("| " + " | ".join(["---"] * len(row.cells)) + " |\n")

    def _is_block_element(self, node: Node) -> bool:
        """Check if a node is a block element that should have spacing around it"""
        return node.node_type in (
            ElementType.PARAGRAPH,
            ElementType.HEADING,
            ElementType.TABLE,
            ElementType.IMAGE,
        )

    def _ensure_single_newline(self, result: List[str]) -> None:
        """Ensure the output ends with exactly one newline"""
        if not result:
            return

        last_str = result[-1]
        if not last_str.endswith("\n"):
            result.append("\n")
        elif last_str.endswith("\n\n"):
            # Remove extra newlines
            result[-1] = last_str.rstrip("\n") + "\n"

    def _ensure_blank_line(self, result: List[str]) -> None:
        """Ensure there's a blank line (two consecutive newlines) at the end"""
        if not result:
            return

        # First ensure there's at least one newline
        self._ensure_single_newline(result)

        # Then add another newline to create a blank line
        last_str = result[-1]
        if not last_str.endswith("\n\n"):
            result.append("\n")
