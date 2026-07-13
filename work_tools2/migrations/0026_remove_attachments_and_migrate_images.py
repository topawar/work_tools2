# Generated manually for removing attachments and migrating images to base64

import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import migrations


def migrate_images_and_remove_attachments(apps, schema_editor):
    import base64
    from work_tools2.views.document_library_views import editorjs_to_html

    DocumentLibrary = apps.get_model('work_tools2', 'DocumentLibrary')
    DocumentAttachment = apps.get_model('work_tools2', 'DocumentAttachment')

    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    media_root = Path(getattr(settings, 'MEDIA_ROOT', ''))

    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
    }

    for doc in DocumentLibrary.objects.all():
        content_json = doc.content_json or {}
        if not isinstance(content_json, dict):
            content_json = {}
        blocks = content_json.get('blocks', [])
        if not isinstance(blocks, list):
            blocks = []

        new_blocks = []
        changed = False

        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get('type')

            # 完全移除附件块
            if block_type == 'file':
                changed = True
                continue

            # 将图片 URL 转为 base64 data URL
            if block_type == 'image':
                data = block.get('data', {}) or {}
                file_data = data.get('file', {}) or {}
                if isinstance(file_data, str):
                    file_data = {'url': file_data}
                url = file_data.get('url', '')

                if url.startswith(media_url):
                    relative_path = url[len(media_url):]
                    try:
                        if default_storage.exists(relative_path):
                            with default_storage.open(relative_path, 'rb') as f:
                                image_data = f.read()
                            ext = os.path.splitext(relative_path)[1].lower()
                            mime = mime_map.get(ext, 'image/png')
                            b64 = base64.b64encode(image_data).decode('utf-8')
                            file_data['url'] = f"data:{mime};base64,{b64}"
                            data['file'] = file_data
                            block['data'] = data
                            changed = True
                        else:
                            # 原文件已缺失，移除该图片块
                            changed = True
                            continue
                    except Exception:
                        # 转换失败，移除该图片块避免后续显示异常
                        changed = True
                        continue

            new_blocks.append(block)

        if changed:
            content_json['blocks'] = new_blocks
            doc.content_json = content_json
            doc.content = editorjs_to_html(content_json)
            doc.save(update_fields=['content_json', 'content'])

    # 删除所有附件记录及文件
    for att in DocumentAttachment.objects.all():
        try:
            if att.file and default_storage.exists(att.file.name):
                default_storage.delete(att.file.name)
        except Exception:
            pass
        att.delete()

    # 清理 media/document_library 目录
    doc_lib_dir = media_root / 'document_library'
    if doc_lib_dir.exists():
        shutil.rmtree(doc_lib_dir, ignore_errors=True)


class Migration(migrations.Migration):
    dependencies = [
        ('work_tools2', '0025_remove_documentlibrary_category'),
    ]

    operations = [
        migrations.RunPython(migrate_images_and_remove_attachments, migrations.RunPython.noop),
        migrations.DeleteModel(
            name='DocumentAttachment',
        ),
    ]
