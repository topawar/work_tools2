import base64
import json
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q

from work_tools2.models import DocumentLibrary, FormConfig


def _escape_html(text):
    """转义 HTML 特殊字符"""
    if text is None:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


def _render_list_items(items, style='unordered'):
    """递归渲染 Editor.js 列表项"""
    if not items:
        return ''

    tag = 'ul' if style == 'unordered' else 'ol'
    if style == 'checklist':
        tag = 'ul'

    html_parts = [f'<{tag}>']
    for item in items:
        if isinstance(item, dict):
            content = item.get('content', '')
            nested = item.get('items', [])
            meta = item.get('meta', {})
            checked = meta.get('checked', False) if isinstance(meta, dict) else False

            if style == 'checklist':
                cls = 'checked' if checked else ''
                html_parts.append(f'<li class="{cls}"><input type="checkbox" disabled {"checked" if checked else ""}> {content}</li>')
            else:
                html_parts.append(f'<li>{content}')

            if nested:
                html_parts.append(_render_list_items(nested, style))

            if style != 'checklist':
                html_parts.append('</li>')
        elif isinstance(item, str):
            html_parts.append(f'<li>{item}</li>')
    html_parts.append(f'</{tag}>')
    return ''.join(html_parts)


def editorjs_to_html(content_json):
    """将 Editor.js 的 JSON 输出转换为 HTML 字符串"""
    if not content_json or not isinstance(content_json, dict):
        return ''

    blocks = content_json.get('blocks', [])


    if not blocks:
        return ''

    html_parts = []
    for block in blocks:
        block_type = block.get('type', '')
        data = block.get('data', {})

        if block_type == 'paragraph':
            text = data.get('text', '')
            if text:
                html_parts.append(f'<p>{text}</p>')

        elif block_type == 'header':
            text = data.get('text', '')
            level = data.get('level', 2)
            level = max(1, min(6, int(level) if str(level).isdigit() else 2))
            if text:
                html_parts.append(f'<h{level}>{text}</h{level}>')

        elif block_type == 'list':
            style = data.get('style', 'unordered')
            items = data.get('items', [])
            if items:
                html_parts.append(_render_list_items(items, style))

        elif block_type == 'code':
            code = data.get('code', '')
            language = data.get('language', '')
            lang_class = f'language-{language}' if language else ''
            html_parts.append(f'<pre class="{lang_class}"><code>{_escape_html(code)}</code></pre>')

        elif block_type == 'image':
            file_data = data.get('file', {}) or {}
            url = file_data.get('url', '') if isinstance(file_data, dict) else str(file_data)
            caption = data.get('caption', '')
            with_background = data.get('withBackground', False)
            stretched = data.get('stretched', False)
            with_border = data.get('withBorder', False)

            classes = ['editorjs-image']
            if with_background:
                classes.append('with-background')
            if stretched:
                classes.append('stretched')
            if with_border:
                classes.append('with-border')

            figure_html = f'<figure class="{" ".join(classes)}">'
            if url:
                figure_html += f'<img src="{_escape_html(url)}" alt="{_escape_html(caption)}">'
            if caption:
                figure_html += f'<figcaption>{caption}</figcaption>'
            figure_html += '</figure>'
            html_parts.append(figure_html)

        elif block_type == 'table':
            rows = data.get('content', [])
            if rows:
                table_html = '<table class="editorjs-table"><tbody>'
                for row in rows:
                    table_html += '<tr>'
                    for cell in row:
                        table_html += f'<td>{cell}</td>'
                    table_html += '</tr>'
                table_html += '</tbody></table>'
                html_parts.append(table_html)

        elif block_type == 'quote':
            text = data.get('text', '')
            caption = data.get('caption', '')
            alignment = data.get('alignment', 'left')
            if text:
                html_parts.append(f'<blockquote class="align-{alignment}"><p>{text}</p>{f"<cite>{caption}</cite>" if caption else ""}</blockquote>')

        elif block_type == 'warning':
            title = data.get('title', '')
            message = data.get('message', '')
            html_parts.append(f'<div class="editorjs-warning"><strong>{title}</strong><p>{message}</p></div>')

        elif block_type == 'delimiter':
            html_parts.append('<hr>')

        elif block_type == 'linkTool':
            link = data.get('link', '')
            meta = data.get('meta', {}) or {}
            title = meta.get('title', '') if isinstance(meta, dict) else ''
            desc = meta.get('description', '') if isinstance(meta, dict) else ''
            html_parts.append(f'<a href="{_escape_html(link)}" target="_blank" rel="noopener" class="editorjs-link">{title or link}</a>')

    return '\n'.join(html_parts)


def extract_title_from_content_json(content_json):
    """从 Editor.js JSON 中提取文档标题（仅取第一个 heading 块文本）"""
    if not content_json or not isinstance(content_json, dict):
        return ''

    blocks = content_json.get('blocks', [])
    if not blocks:
        return ''

    first_block = blocks[0]
    if first_block.get('type') == 'header':
        text = first_block.get('data', {}).get('text', '')
        if text:
            import re
            plain = re.sub(r'<[^>]+>', '', text).strip()
            if plain:
                return plain

    return ''


def document_library_list(request):
    """文档库列表页"""
    return render(request, "document_library_list.html", {"active_page": "document_library"})


def document_library_edit(request, doc_id=None):
    """文档编辑/预览页"""
    doc = None
    if doc_id:
        try:
            doc = DocumentLibrary.objects.get(id=doc_id)
        except DocumentLibrary.DoesNotExist:
            pass

    # 新建文档默认进入编辑模式；已有文档默认进入预览模式，只有 ?edit=1 才允许编辑
    is_edit_mode = request.GET.get('edit') == '1'
    readonly = (doc is not None) and not is_edit_mode

    return render(request, "document_library_edit.html", {
        "active_page": "document_library",
        "doc_id": doc.id if doc else None,
        "doc_content_json": doc.content_json if doc else {},
        "readonly": readonly,
    })


@csrf_exempt
def get_documents(request):
    """获取文档列表"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)

    try:
        keyword = request.GET.get('keyword', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))

        queryset = DocumentLibrary.objects.all()
        if keyword:
            queryset = queryset.filter(
                Q(title__icontains=keyword) | Q(content__icontains=keyword)
            )

        total = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        docs = queryset.order_by('-updated_at')[start:end]

        data = []
        for doc in docs:
            linked_count = doc.linked_forms.count()
            data.append({
                'id': doc.id,
                'title': doc.title,
                'is_active': doc.is_active,
                'linked_count': linked_count,
                'updated_at': doc.updated_at.strftime('%Y-%m-%d %H:%M:%S') if doc.updated_at else '-',
            })

        return JsonResponse({
            'success': True,
            'data': data,
            'total': total,
            'page': page,
            'page_size': page_size,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'获取失败：{str(e)}'}, status=500)


@csrf_exempt
def get_document_detail(request, doc_id):
    """获取文档详情"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)

    try:
        doc = DocumentLibrary.objects.get(id=doc_id)
        return JsonResponse({
            'success': True,
            'data': {
                'id': doc.id,
                'title': doc.title,
                'content': doc.content,
                'content_json': doc.content_json,
                'is_active': doc.is_active,
                'linked_count': doc.linked_forms.count(),
                'created_at': doc.created_at.strftime('%Y-%m-%d %H:%M:%S') if doc.created_at else '-',
                'updated_at': doc.updated_at.strftime('%Y-%m-%d %H:%M:%S') if doc.updated_at else '-',
            }
        })
    except DocumentLibrary.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文档不存在'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'获取失败：{str(e)}'}, status=500)


@csrf_exempt
def save_document(request):
    """保存文档（新增或更新）"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    try:
        data = json.loads(request.body)
        doc_id = data.get('id')
        content_json = data.get('content_json', {})
        is_active = data.get('is_active', True)

        # 校验：首块必须是标题且标题不能为空
        blocks = content_json.get('blocks', []) if isinstance(content_json, dict) else []
        if not blocks:
            return JsonResponse({'success': False, 'message': '文档标题必填，请先在首行输入标题'}, status=400)
        first_block = blocks[0]
        if first_block.get('type') != 'header':
            return JsonResponse({'success': False, 'message': '文档标题必填，请将第一行设置为标题块'}, status=400)
        title = extract_title_from_content_json(content_json)
        if not title:
            return JsonResponse({'success': False, 'message': '文档标题不能为空'}, status=400)

        # 后端将 Editor.js JSON 渲染为 HTML，确保阅读视图一致
        rendered_html = editorjs_to_html(content_json)

        if doc_id:
            try:
                doc = DocumentLibrary.objects.get(id=doc_id)
                doc.title = title
                doc.content_json = content_json
                doc.content = rendered_html
                doc.is_active = bool(is_active)
                doc.save()
            except DocumentLibrary.DoesNotExist:
                return JsonResponse({'success': False, 'message': '文档不存在'}, status=404)
        else:
            doc = DocumentLibrary.objects.create(
                title=title,
                content_json=content_json,
                content=rendered_html,
                is_active=bool(is_active),
            )

        return JsonResponse({
            'success': True,
            'data': {'id': doc.id, 'title': doc.title},
            'message': '保存成功'
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON 解析失败'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'保存失败：{str(e)}'}, status=500)


@csrf_exempt
def delete_document(request, doc_id):
    """删除文档"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    try:
        doc = DocumentLibrary.objects.get(id=doc_id)
        doc.delete()
        return JsonResponse({'success': True, 'message': '删除成功'})
    except DocumentLibrary.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文档不存在'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'删除失败：{str(e)}'}, status=500)


@csrf_exempt
def batch_delete_documents(request):
    """批量删除文档"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return JsonResponse({'success': False, 'message': '请选择要删除的文档'}, status=400)

        # 过滤掉非数字ID
        ids = [int(i) for i in ids if str(i).isdigit()]
        if not ids:
            return JsonResponse({'success': False, 'message': '请选择要删除的文档'}, status=400)

        docs = DocumentLibrary.objects.filter(id__in=ids)
        deleted_count = 0
        for doc in docs:
            try:
                doc.delete()
                deleted_count += 1
            except Exception:
                pass

        return JsonResponse({
            'success': True,
            'message': f'成功删除 {deleted_count} 个文档',
            'data': {'deleted_count': deleted_count}
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON 解析失败'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'删除失败：{str(e)}'}, status=500)


@csrf_exempt
def upload_image(request):
    """上传图片（供富文本编辑器调用），以 base64 data URL 形式存入文档内容"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    try:
        image = request.FILES.get('image')
        if not image:
            return JsonResponse({'success': False, 'message': '未找到图片文件'}, status=400)

        ext = Path(image.name).suffix.lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
            return JsonResponse({'success': False, 'message': '不支持的图片格式'}, status=400)

        content_type = image.content_type or 'image/png'
        data = image.read()
        max_size = 5 * 1024 * 1024
        if len(data) > max_size:
            return JsonResponse({'success': False, 'message': '图片大小不能超过 5MB'}, status=400)

        b64 = base64.b64encode(data).decode('utf-8')
        url = f"data:{content_type};base64,{b64}"

        return JsonResponse({'success': True, 'data': {'url': url, 'path': ''}})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'上传失败：{str(e)}'}, status=500)


@csrf_exempt
def get_document_options(request):
    """获取文档下拉选项（供表单配置页选择关联文档）"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)

    try:
        keyword = request.GET.get('keyword', '').strip()
        queryset = DocumentLibrary.objects.filter(is_active=True)
        if keyword:
            queryset = queryset.filter(title__icontains=keyword)

        options = []
        for doc in queryset.order_by('-updated_at')[:200]:
            options.append({
                'id': doc.id,
                'title': doc.title,
                'updated_at': doc.updated_at.strftime('%Y-%m-%d %H:%M') if doc.updated_at else '-',
            })

        return JsonResponse({'success': True, 'data': options})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'获取失败：{str(e)}'}, status=500)


@csrf_exempt
def get_document_linked_forms(request, doc_id):
    """获取文档关联的动态表单列表"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)

    try:
        doc = DocumentLibrary.objects.get(id=doc_id)
        forms = []
        for form in doc.linked_forms.filter(is_active=True).order_by('-updated_at'):
            forms.append({
                'id': form.id,
                'form_name': form.form_name,
                'query_mode': form.query_mode,
                'call_count': form.call_count,
                'updated_at': form.updated_at.strftime('%Y-%m-%d %H:%M:%S') if form.updated_at else '-',
            })

        return JsonResponse({
            'success': True,
            'data': forms,
            'total': len(forms)
        })
    except DocumentLibrary.DoesNotExist:
        return JsonResponse({'success': False, 'message': '文档不存在'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'获取失败：{str(e)}'}, status=500)


@csrf_exempt
def create_document_quick(request):
    """快速创建说明文档（用于表单配置页一键创建）"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        content_json = data.get('content_json')

        if not title:
            return JsonResponse({'success': False, 'message': '文档标题不能为空'}, status=400)

        # 若前端未传内容，默认生成一个以标题为一级标题的文档
        if not content_json:
            content_json = {
                'blocks': [
                    {'type': 'header', 'data': {'text': title, 'level': 1}}
                ]
            }

        rendered_html = editorjs_to_html(content_json)

        doc = DocumentLibrary.objects.create(
            title=title,
            content_json=content_json,
            content=rendered_html,
            is_active=True,
        )

        return JsonResponse({
            'success': True,
            'data': {
                'id': doc.id,
                'title': doc.title,
                'updated_at': doc.updated_at.strftime('%Y-%m-%d %H:%M') if doc.updated_at else '-',
            },
            'message': '文档创建成功'
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON 解析失败'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'创建失败：{str(e)}'}, status=500)
