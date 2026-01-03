from jedwal.posts.parsers import ast
from jedwal.posts.parsers.image_handler import ImageHandler


class GoogleDocsParser:
    def __init__(self, image_handler: ImageHandler | None = None):
        self.handlers = [
            (self.is_code_block, self.parse_code_block),
            (self.is_heading, self.parse_heading),
            (self.is_list_item, self.parse_list),
            (self.is_paragraph, self.parse_paragraph),
            (self.is_table, self.parse_table),
        ]
        self.image_handler = image_handler
        self.inline_objects: dict | None = None
        self.lists_metadata: dict | None = None
        # There are two ways to define code blocks: the "raw" markdown syntax
        # and the "official" Google Docs code building block. These are represented
        # differently in the Google Docs payload and must be handled separately.
        self.code_block_delimiters_map = {"md": "```", "google_docs": "\ue907"}

    @property
    def code_block_delimiters(self):
        return tuple(self.code_block_delimiters_map.values())

    def parse(self, doc_json) -> ast.Root:
        content = doc_json["body"]["content"]
        self.inline_objects = doc_json.get("inlineObjects")
        self.lists_metadata = doc_json.get("lists", {})  # Add this

        ast_children = []
        i = 0

        # Check for frontmatter first
        frontmatter, consumed = self._extract_frontmatter(content, i)
        if frontmatter:
            i = consumed  # skip past frontmatter lines

        # start parsing main content
        while i < len(content):
            item = content[i]
            for predicate, handler in self.handlers:
                if predicate(item):
                    result, consumed = handler(content, i)
                    if result:
                        ast_children.append(result)
                    i += consumed
                    break
            else:
                i += 1  # Skip element if no handler matched

        return ast.Root(children=ast_children, frontmatter=frontmatter)

    def is_code_block(self, item):
        if "paragraph" not in item:
            return False
        text = self._get_text(item["paragraph"])
        return text.startswith(self.code_block_delimiters)

    def is_heading(self, item):
        if "paragraph" not in item:
            return False
        style = item["paragraph"]["paragraphStyle"]["namedStyleType"]
        return style.startswith("HEADING_")

    def is_paragraph(self, item):
        if "paragraph" not in item:
            return False
        style = item["paragraph"]["paragraphStyle"]["namedStyleType"]

        if style != "NORMAL_TEXT":
            return False

        elements = item["paragraph"]["elements"]

        # Check if there's any meaningful content
        for element in elements:
            # Has text content?
            if "textRun" in element:
                text = element["textRun"]["content"].rstrip("\n")
                if text.strip():
                    return True
            # Has inline object (like image)?
            if "inlineObjectElement" in element:
                return True

        return False

    def is_table(self, item):
        return "table" in item

    def parse_code_block(self, content, start_idx):
        item = content[start_idx]
        text = self._get_text(item["paragraph"])

        code_lines = []

        # Google code block delimiter (\ue907) is treated as
        # one char since everything is UTF encoded.
        if text[0] == self.code_block_delimiters_map["google_docs"]:
            lang = None  # Google docs API has no way to determine lang AFAICT

            # Google doc style code blocks sometimes start content
            # immediately after the delim (not on a new line), so
            # we remove the delim but keep the rest of the line.
            # E.g., "\ue907const a = 'b'" --> "const a = b"
            code_lines.append(text[1:])
        elif text[:3] == self.code_block_delimiters_map["md"]:
            lang = text[3:].strip() or None  # grab lang from md e.g ```ts --> ts
        else:
            raise ValueError(f"code delimiter not supported for {text}")

        i = start_idx + 1
        while i < len(content):
            assert "paragraph" in content[i], "Non-paragraph item found in code block"
            line = self._get_text(content[i]["paragraph"])
            if line.startswith(self.code_block_delimiters):
                i += 1  # consume closing fence and exit
                break
            code_lines.append(line)
            i += 1

        consumed = i - start_idx
        return ast.Code(lang=lang, value="\n".join(code_lines)), consumed

    def parse_heading(self, content, start_idx):
        item = content[start_idx]
        style = item["paragraph"]["paragraphStyle"]["namedStyleType"]
        depth = int(style.split("_")[1])
        children = self._parse_inline_elements(item["paragraph"]["elements"])
        return ast.Heading(depth=depth, children=children), 1

    def parse_paragraph(self, content, start_idx):
        item = content[start_idx]
        children = self._parse_inline_elements(item["paragraph"]["elements"])

        return ast.Paragraph(children=children), 1

    def parse_table(self, content, start_idx):
        item = content[start_idx]
        table_data = item["table"]

        rows = []
        for table_row in table_data["tableRows"]:
            cells = []
            for table_cell in table_row["tableCells"]:
                # Each cell can have multiple paragraphs, but we'll merge them
                cell_children = []
                for cell_content in table_cell["content"]:
                    if "paragraph" in cell_content:
                        elements = self._parse_inline_elements(
                            cell_content["paragraph"]["elements"]
                        )
                        cell_children.extend(elements)

                cells.append(ast.TableCell(children=cell_children))

            rows.append(ast.TableRow(children=cells))

        return ast.Table(children=rows), 1

    def _get_text(self, paragraph):
        """Extract only text content from paragraph (for code blocks, etc)"""
        res = []
        for el in paragraph["elements"]:
            text = el.get("textRun", {})
            content = text.get("content")
            if content is None:
                continue
            res.append(content)
        return "".join(res).rstrip("\n")

    def _parse_inline_elements(self, elements):
        children = []

        for element in elements:
            if "inlineObjectElement" in element:
                inline_obj_elem = element["inlineObjectElement"]
                if self._is_image(inline_obj_elem):
                    image_node = self._parse_image(inline_obj_elem)
                    if image_node:
                        children.append(image_node)
                continue

            if "textRun" not in element:
                continue

            text_run = element["textRun"]
            content = text_run["content"].rstrip("\n")

            if not content:
                continue

            node = self._wrap_with_formatting(content, text_run.get("textStyle", {}))
            children.append(node)

        return children

    def _wrap_with_formatting(self, content, text_style):
        """Wrap text with formatting in consistent order: Link > Strong > Emphasis > Text"""
        node = ast.Text(value=content)

        # Apply formatting in reverse order (innermost to outermost)
        if text_style.get("italic", False):
            node = ast.Emphasis(children=[node])

        if text_style.get("bold", False):
            node = ast.Strong(children=[node])

        if "link" in text_style:
            url = text_style["link"]["url"]
            node = ast.Link(url=url, children=[node])

        return node

    def _is_image(self, inline_object_element):
        """Check if inline object is an image"""
        object_id = inline_object_element.get("inlineObjectId")
        if not object_id or object_id not in self.inline_objects:
            return False

        inline_object = self.inline_objects[object_id]

        try:
            inline_object["inlineObjectProperties"]["embeddedObject"]["imageProperties"]
            return True
        except KeyError:
            return False

    def _parse_image(self, inline_object_element):
        """Extract image from inline object (assumes _is_image returned True)"""
        object_id = inline_object_element["inlineObjectId"]
        inline_object = self.inline_objects[object_id]
        inline_object = inline_object["inlineObjectProperties"]["embeddedObject"]

        image_props = inline_object["imageProperties"]
        google_url = image_props.get("contentUri")
        if self.image_handler is not None:
            url = self.image_handler.upload(src=google_url)
        else:
            url = google_url

        alt = inline_object.get("description")
        title = inline_object.get("title")

        if not url:
            return None

        return ast.Image(url=url, alt=alt, title=title)

    def _extract_frontmatter(self, content, start_idx):
        """Extract frontmatter from start of document if present"""
        if start_idx != 0:
            return None, 0  # Frontmatter must be at beginning

        # Skip section breaks at the start
        while start_idx < len(content) and "sectionBreak" in content[start_idx]:
            start_idx += 1

        # Check if first paragraph starts with ---
        if start_idx >= len(content) or "paragraph" not in content[start_idx]:
            return None, 0

        first_text = self._get_text(content[start_idx]["paragraph"]).strip()
        if first_text != "---":
            return None, 0

        # Collect lines until closing ---
        yaml_lines = []
        i = start_idx + 1
        found_closing = False

        while i < len(content):
            if "paragraph" not in content[i]:
                i += 1
                continue

            text = self._get_text(content[i]["paragraph"])

            # Found closing delimiter
            if text.strip() == "---":
                i += 1  # Consume closing ---
                found_closing = True
                break

            yaml_lines.append(text)
            i += 1

        # No closing --- found, not valid frontmatter
        if not found_closing or not yaml_lines:
            return None, 0

        frontmatter = ast.Frontmatter.from_text(value="\n".join(yaml_lines))
        consumed = i  # Return absolute index, not relative
        return frontmatter, consumed

    def is_list_item(self, item):
        if "paragraph" not in item:
            return False
        return "bullet" in item["paragraph"]  # Remove .get("paragraphStyle", {})

    def parse_list(self, content, start_idx):
        """Parse a flat list with indent levels"""
        first_item = content[start_idx]["paragraph"]
        list_id = first_item["bullet"]["listId"]

        # Determine if ordered or unordered
        is_ordered = self._is_ordered_list(list_id)

        # Collect all consecutive items with same listId
        list_items = []
        i = start_idx

        while i < len(content):
            if not self.is_list_item(content[i]):
                break

            para = content[i]["paragraph"]
            bullet = para.get("bullet", {})

            # Different listId = different list
            if bullet.get("listId") != list_id:
                break

            nesting_level = bullet.get("nestingLevel", 0)
            children = self._parse_inline_elements(para["elements"])

            # Create list item with paragraph child
            list_item = ast.ListItem(
                indent_level=nesting_level, children=[ast.Paragraph(children=children)]
            )
            list_items.append(list_item)

            i += 1

        list_node = ast.List(ordered=is_ordered, children=list_items)
        consumed = i - start_idx

        return list_node, consumed

    def _is_ordered_list(self, list_id):
        """Check if list is ordered based on glyphType"""
        if not self.lists_metadata or list_id not in self.lists_metadata:
            return False

        first_level = self.lists_metadata[list_id]["listProperties"]["nestingLevels"][0]
        # If it has glyphType (DECIMAL, ALPHA, ROMAN), it's ordered
        # If it has glyphSymbol (bullets), it's unordered
        return "glyphType" in first_level
