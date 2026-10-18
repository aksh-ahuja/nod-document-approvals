class FailureMessage:
    FILE_TYPE = 'Choose a PDF, DOCX, or TXT document.'
    FILE_SIZE = 'Your file must be 10 MB or smaller.'
    FILE_EMPTY = 'This file is empty. Choose a document with content.'
    FILE_INVALID = 'This document could not be read. Export a fresh PDF, DOCX, or UTF-8 TXT file.'
    FILE_EXTERNAL = (
        'Export this document as PDF before uploading. Linked external content is not supported.'
    )
    UPLOAD_NOT_FOUND = 'This upload is not available.'
    UPLOAD_EXPIRED = 'This upload expired. Please choose the file again.'
    UPLOAD_NOT_READY = 'Your document is still being checked. Try again shortly.'
    UPLOAD_USED = 'This document has already been submitted.'
    UPLOAD_MISSING = 'The upload has not finished. Please try uploading again.'
    UPLOAD_CHANGED = 'The uploaded file changed. Please upload it again.'
    UPLOAD_SIZE_MISMATCH = 'The uploaded size does not match the selected file.'
    UPLOAD_LIMIT = 'Too many uploads. Please wait before uploading another document.'
    UPLOAD_UNAVAILABLE = 'File storage is temporarily unavailable. Please try again.'
