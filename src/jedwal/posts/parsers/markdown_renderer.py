from jedwal.posts.parsers import ast


class MarkdownRenderer:
    def render(self, node: ast.Node) -> str:
        """Convert an mdast node to markdown string"""

        # A little bit of poor-man's polymorphism.
        # It's a little implicit, but let's us call the correct
        # handler for every node type without any overhead.
        # Just make sure to define new handlers here if we ever
        # add to the underlying AST.
        method_name = f"render_{node.type}"
        method = getattr(self, method_name, self.render_unknown)
        return method(node)

    def render_root(self, node: ast.Root) -> str:
        return "\n\n".join(self.render(child) for child in node.children)

    def render_heading(self, node: ast.Heading) -> str:
        hashes = "#" * node.depth
        text = "".join(self.render(child) for child in node.children)
        return f"{hashes} {text}"

    def render_paragraph(self, node: ast.Paragraph) -> str:
        return "".join(self.render(child) for child in node.children)

    def render_code(self, node: ast.Code) -> str:
        lang = node.lang or ""
        return f"```{lang}\n{node.value}\n```"

    def render_text(self, node: ast.Text) -> str:
        return node.value

    def render_strong(self, node: ast.Strong) -> str:
        text = "".join(self.render(child) for child in node.children)
        return f"**{text}**"

    def render_emphasis(self, node: ast.Emphasis) -> str:
        text = "".join(self.render(child) for child in node.children)
        return f"*{text}*"

    def render_link(self, node: ast.Link):
        text = "".join(self.render(child) for child in node.children)
        return f"[{text}]({node.url})"

    def render_break(self, node: ast.Break) -> str:
        return "  \n"  # Two spaces + newline = markdown line break

    def render_image(self, node: ast.Image):
        # ![alt text](Isolated.png "Title")
        alt = node.alt or ""
        title = node.title or ""
        return f"![{alt}]({node.url} '{title}')"

    def render_table(self, node: ast.Table) -> str:
        if not node.children:
            return ""

        lines = []

        # Header row (first row)
        header = node.children[0]
        header_cells = [self.render(cell) for cell in header.children]
        lines.append("| " + " | ".join(header_cells) + " |")

        # Separator
        separators = ["---"] * len(header.children)
        lines.append("| " + " | ".join(separators) + " |")

        # Data rows
        for row in node.children[1:]:
            cells = [self.render(cell) for cell in row.children]
            lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)

    def render_table_row(self, node: ast.TableRow) -> str:
        return " | ".join(self.render(cell) for cell in node.children)

    def render_table_cell(self, node: ast.TableCell) -> str:
        return "".join(self.render(child) for child in node.children)

    def render_list(self, node: ast.List) -> str:
        lines = []
        counter_by_level = {}  # Track counters for each indent level

        for item in node.children:
            level = item.indent_level

            # Increment counter for this level
            if level not in counter_by_level:
                counter_by_level[level] = 1
            else:
                counter_by_level[level] += 1

            # Reset deeper level counters
            deeper_levels = [level for level in counter_by_level if level > level]
            for level in deeper_levels:
                del counter_by_level[level]

            # Render with proper number
            lines.append(
                self._render_list_item(item, counter_by_level[level], node.ordered)
            )

        return "\n".join(lines)

    def render_unknown(self, node: ast.Node) -> str:
        raise ValueError(f"Unknown node type: {node.type}")

    def _render_list_item(
        self, node: ast.ListItem, number: int, is_ordered: bool
    ) -> str:
        content = "".join(self.render(child) for child in node.children)
        indent = "    " * node.indent_level  # 4 spaces for indent level
        marker = f"{number}." if is_ordered else "-"
        return f"{indent}{marker} {content}"
