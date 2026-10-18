import zlib
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from rest_framework import serializers

from utils.storage.constants import FILE_TYPES

from .constants import DOCX_MAX_ENTRIES, DOCX_MAX_EXPANDED_BYTES, FILE_MAX_BYTES
from .messages import FailureMessage


def validate_document(file):
    extension = _validate_file_details(file)

    try:
        if extension == '.pdf':
            _validate_pdf(file)
        elif extension == '.txt':
            _validate_text(file)
        else:
            _validate_docx(file)
    except (
        BadZipFile,
        UnicodeDecodeError,
        ElementTree.ParseError,
        RuntimeError,
        NotImplementedError,
        KeyError,
        EOFError,
        zlib.error,
    ):
        raise serializers.ValidationError(FailureMessage.FILE_INVALID)
    finally:
        file.seek(0)

    file.content_type = FILE_TYPES[extension]

    return file


def _validate_file_details(file):
    has_control_characters = any(ord(char) < 32 or ord(char) == 127 for char in file.name)

    if has_control_characters:
        raise serializers.ValidationError(FailureMessage.FILE_INVALID)

    extension = Path(file.name).suffix.lower()

    if extension not in FILE_TYPES:
        raise serializers.ValidationError(FailureMessage.FILE_TYPE)

    if file.size > FILE_MAX_BYTES:
        raise serializers.ValidationError(FailureMessage.FILE_SIZE)

    if not file.size:
        raise serializers.ValidationError(FailureMessage.FILE_EMPTY)

    return extension


def _validate_pdf(file):
    if file.read(5) != b'%PDF-':
        raise serializers.ValidationError(FailureMessage.FILE_INVALID)

    file.seek(max(0, file.size - 1024))

    if b'%%EOF' not in file.read():
        raise serializers.ValidationError(FailureMessage.FILE_INVALID)


def _validate_text(file):
    text = file.read().decode('utf-8-sig')

    if '\x00' in text or not text.strip():
        raise serializers.ValidationError(FailureMessage.FILE_INVALID)


def _validate_docx(file):
    with ZipFile(file) as archive:
        entries = archive.infolist()
        expanded_size = sum(entry.file_size for entry in entries)

        if len(entries) > DOCX_MAX_ENTRIES or expanded_size > DOCX_MAX_EXPANDED_BYTES:
            raise serializers.ValidationError(FailureMessage.FILE_INVALID)

        names = {entry.filename for entry in entries}
        required_files = {'[Content_Types].xml', 'word/document.xml'}

        if not required_files.issubset(names):
            raise serializers.ValidationError(FailureMessage.FILE_INVALID)

        for entry in entries:
            _validate_docx_entry(archive, entry)


def _validate_docx_entry(archive, entry):
    name = entry.filename.lower()
    is_encrypted = bool(entry.flag_bits & 1)
    has_embedded_code = 'vbaproject' in name or '/embeddings/' in name
    has_unsafe_path = name.startswith('/') or '\\' in name or '..' in name.split('/')

    if is_encrypted or has_embedded_code or has_unsafe_path:
        raise serializers.ValidationError(FailureMessage.FILE_INVALID)

    if name.endswith(('.xml', '.rels')):
        _validate_docx_xml(archive.read(entry))


def _validate_docx_xml(content):
    declaration = content.replace(b'\x00', b'').upper()

    if b'<!DOCTYPE' in declaration or b'<!ENTITY' in declaration:
        raise serializers.ValidationError(FailureMessage.FILE_INVALID)

    root = ElementTree.fromstring(content)

    for node in root.iter():
        is_embedded_content = node.tag.endswith('}altChunk')
        is_external = node.attrib.get('TargetMode') == 'External'
        is_hyperlink = node.attrib.get('Type', '').endswith('/hyperlink')

        if is_embedded_content or (is_external and not is_hyperlink):
            raise serializers.ValidationError(FailureMessage.FILE_EXTERNAL)
