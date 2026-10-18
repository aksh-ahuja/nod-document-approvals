from enum import Enum

TITLE_MAX_LENGTH = 200
CONTENT_MAX_LENGTH = 50000
NOTE_MAX_LENGTH = 2000
STATUS_MAX_LENGTH = 16
HASH_MAX_LENGTH = 64
SEARCH_MAX_LENGTH = 200
FILE_LINK_TTL = 300
FILE_LINK_SALT = 'nod-document-link'


class SubmissionStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'

    @classmethod
    def choices(cls):
        return [(member.value, member.value.title()) for member in cls]
