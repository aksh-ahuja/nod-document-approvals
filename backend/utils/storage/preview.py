import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.base import ContentFile


class PreviewUnavailable(Exception):
    pass


def convert_docx(file):
    with TemporaryDirectory(prefix='nod-preview-') as directory:
        root = Path(directory)
        source = root / 'document.docx'
        source.write_bytes(file.read())
        profile = root / 'profile'
        user = profile / 'user'
        user.mkdir(parents=True)
        (user / 'registrymodifications.xcu').write_text(
            '<?xml version="1.0" encoding="UTF-8"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item></oor:items>'
        )

        try:
            subprocess.run(
                [
                    settings.NOD_LIBREOFFICE_BINARY,
                    f'-env:UserInstallation={profile.as_uri()}',
                    '--headless',
                    '--nologo',
                    '--nodefault',
                    '--norestore',
                    '--convert-to',
                    'pdf:writer_pdf_Export',
                    '--outdir',
                    str(root),
                    str(source),
                ],
                check=True,
                timeout=settings.NOD_PREVIEW_TIMEOUT,
                capture_output=True,
                env={**os.environ, 'SAL_USE_VCLPLUGIN': 'svp'},
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PreviewUnavailable('Could not generate the document preview.') from error

        output = root / 'document.pdf'

        if not output.is_file() or not 0 < output.stat().st_size <= settings.NOD_PREVIEW_MAX_BYTES:
            raise PreviewUnavailable('Could not generate the document preview.')

        content = output.read_bytes()

        if not content.startswith(b'%PDF-'):
            raise PreviewUnavailable('Could not generate the document preview.')

        return ContentFile(content)
