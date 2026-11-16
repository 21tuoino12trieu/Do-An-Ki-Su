import re
import logging


def extract_nodes_from_markdown(markdown_content):
    header_pattern = r'^(#{1,6})\s+(.+)$'
    code_block_pattern = r'^```'
    node_list = []
    
    lines = markdown_content.split('\n')
    in_code_block = False
    
    for line_num, line in enumerate(lines, 1):
        stripped_line = line.strip()
        
        # Check for code block delimiters (triple backticks)
        if re.match(code_block_pattern, stripped_line):
            in_code_block = not in_code_block
            continue
        
        # Skip empty lines
        if not stripped_line:
            continue
        
        # Only look for headers when not inside a code block
        if not in_code_block:
            match = re.match(header_pattern, stripped_line)
            if match:
                title = match.group(2).strip()
                node_list.append({'node_title': title, 'line_num': line_num})

    return node_list, lines


def extract_node_text_content(node_list, markdown_lines):    
    all_nodes = []
    for node in node_list:
        line_content = markdown_lines[node['line_num'] - 1]
        header_match = re.match(r'^(#{1,6})', line_content)
        
        if header_match is None:
            logging.warning(f"Line {node['line_num']} does not contain a valid header: '{line_content}'")
            continue
            
        processed_node = {
            'title': node['node_title'],
            'line_num': node['line_num'],
            'level': len(header_match.group(1))
        }
        all_nodes.append(processed_node)
    
    for i, node in enumerate(all_nodes):
        start_line = node['line_num'] - 1 
        if i + 1 < len(all_nodes):
            end_line = all_nodes[i + 1]['line_num'] - 1 
        else:
            end_line = len(markdown_lines)
        
        node['text'] = '\n'.join(markdown_lines[start_line:end_line]).strip()    
    return all_nodes


def build_tree_from_nodes(node_list):
    if not node_list:
        return []
    
    stack = []
    root_nodes = []
    node_counter = 1
    
    for node in node_list:
        current_level = node['level']
        
        tree_node = {
            'title': node['title'],
            'node_id': str(node_counter).zfill(4),
            'text': node['text'],
            'line_num': node['line_num'],
            'nodes': []
        }
        node_counter += 1
        
        while stack and stack[-1][1] >= current_level:
            stack.pop()
        
        if not stack:
            root_nodes.append(tree_node)
        else:
            parent_node, parent_level = stack[-1]
            parent_node['nodes'].append(tree_node)
        
        stack.append((tree_node, current_level))
    
    return root_nodes


def count_tokens(text, model=None):
    if not text:
        return 0
    return len(text.split())


def build_node_summary_prompt(text: str, title_path: str = "") -> str:
    if title_path:
        title_context = f"""Phần nội dung này thuộc cây tiêu đề sau:
{title_path}

Hãy tích hợp tự nhiên ngữ cảnh tiêu đề (đặc biệt tiêu đề cấp cao nhất) vào mô tả (ví dụ: "...thuộc [tên phần/chương]"). KHÔNG liệt kê lại cây tiêu đề trong mô tả.

"""
    else:
        title_context = ""

    return f"""{title_context}Bạn là trợ lý phân tích tài liệu. Hãy tạo mô tả súc tích (2–4 câu) cho đoạn tài liệu dưới đây.

Mô tả cần đảm bảo:
- Nêu rõ mục đích hoặc phạm vi áp dụng của đoạn
- Tóm lược các nội dung và quy định cốt lõi được đề cập
- Làm nổi bật các trường hợp ngoại lệ hoặc điều kiện đặc biệt quan trọng (nếu có)
- Dùng văn xuôi mạch lạc, KHÔNG dùng bullet point hay danh sách

<document>
{text}
</document>

Chỉ trả về phần mô tả, không thêm nội dung nào khác.
"""


def should_summarize_text(text: str, summary_token_threshold: int, model=None) -> bool:
    return count_tokens(text, model=model) >= summary_token_threshold


def structure_to_list(structure, _ancestor_title_path: str = ""):
    """Flatten the tree into a list, attaching `title_path` (ancestor headings)
    to each node so downstream steps can use it for context."""
    if isinstance(structure, dict):
        nodes = []
        node_copy = dict(structure)
        node_copy["title_path"] = _ancestor_title_path
        nodes.append(node_copy)
        if "nodes" in structure:
            # The heading breadcrumb for children is the first line of this
            # node's text (which already has ancestor lines prepended).
            own_first_line = (structure.get("text") or "").split("\n")[0]
            child_path = own_first_line if not _ancestor_title_path else own_first_line
            nodes.extend(structure_to_list(structure["nodes"], child_path))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(structure_to_list(item, _ancestor_title_path))
        return nodes
    return []


def write_node_id(data, node_id=0):
    if isinstance(data, dict):
        data['node_id'] = str(node_id).zfill(4)
        node_id += 1
        for key in list(data.keys()):
            if 'nodes' in key:
                node_id = write_node_id(data[key], node_id)
    elif isinstance(data, list):
        for index in range(len(data)):
            node_id = write_node_id(data[index], node_id)
    return node_id


def reorder_dict(data, key_order):
    if not key_order:
        return data
    return {key: data[key] for key in key_order if key in data}


def format_structure(structure, order=None):
    if not order:
        return structure
    if isinstance(structure, dict):
        if 'nodes' in structure:
            structure['nodes'] = format_structure(structure['nodes'], order)
        if not structure.get('nodes'):
            structure.pop('nodes', None)
        structure = reorder_dict(structure, order)
    elif isinstance(structure, list):
        structure = [format_structure(item, order) for item in structure]
    return structure
